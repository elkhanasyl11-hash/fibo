"""Fibo Vision end-to-end (mock mode): photo incidents and the panel-photo confirmation rule."""

import pytest
from sqlalchemy import func, select

from app.models import Reading
from app.modules.assistant import mock_fixtures, safety
from tests.conftest import BOT_HEADERS
from tests.image_samples import blurred, damaged, jpeg, tool_image


@pytest.fixture
async def operator(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    telegram_id = 660000 + machine["id"]
    body = {
        "telegram_id": telegram_id,
        "full_name": "Айбек",
        "invite_code": workshop["invite_code"],
        "role": "operator",
    }
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 201
    return telegram_id, machine


async def send_photo(client, telegram_id, machine_id, image, caption=None) -> dict:
    form = {"telegram_id": str(telegram_id), "machine_id": str(machine_id)}
    if caption:
        form["caption"] = caption
    files = {"file": ("photo.jpg", jpeg(image), "image/jpeg")}
    response = await client.post("/api/v1/ingest/photo", data=form, files=files, headers=BOT_HEADERS)
    assert response.status_code == 202, response.text
    return (await client.get(f"/api/v1/incidents/{response.json()['incident_id']}")).json()


async def add_reference(client, machine_id):
    files = {"file": ("ref.jpg", jpeg(tool_image()), "image/jpeg")}
    response = await client.post(f"/api/v1/machines/{machine_id}/baselines/photo", files=files)
    assert response.status_code == 201 and response.json()["kind"] == "photo"


async def test_blurry_photo_is_rejected(client, operator):
    telegram_id, machine = operator
    incident = await send_photo(client, telegram_id, machine["id"], blurred(tool_image()))
    assert incident["status"] == "open" and incident["level"] == "normal"
    assert "размытое" in incident["verdict"] and "Переснимите" in incident["card_text"]


async def test_missing_reference_photo(client, operator):
    telegram_id, machine = operator
    incident = await send_photo(client, telegram_id, machine["id"], tool_image())
    assert incident["verdict"] == "Нет эталонного фото" and "Эталонное фото" in incident["card_text"]


async def test_same_as_reference_is_normal(client, operator):
    telegram_id, machine = operator
    await add_reference(client, machine["id"])
    incident = await send_photo(client, telegram_id, machine["id"], tool_image())
    assert incident["level"] == "normal" and incident["verdict"] == "Видимых дефектов не обнаружено"


async def test_damaged_tool_is_critical_and_no_invented_pages(client, operator):
    telegram_id, machine = operator
    await add_reference(client, machine["id"])
    incident = await send_photo(client, telegram_id, machine["id"], damaged(tool_image(), 0.3))
    assert incident["level"] == "critical"  # vision said critical; the mock card said normal
    assert "скол" in incident["card_text"] and incident["manual_pages"] == []
    assert "%" not in incident["verdict"]  # no wear percentages


async def test_safety_caption_on_a_photo(client, operator):
    telegram_id, machine = operator
    await add_reference(client, machine["id"])
    incident = await send_photo(client, telegram_id, machine["id"], tool_image(), caption="из шпинделя искры")
    assert incident["safety_triggered"] and incident["level"] == "critical"
    assert incident["card_text"].startswith(safety.STOP_HEADER)


async def _readings(session, machine_id) -> int:
    return await session.scalar(
        select(func.count()).select_from(Reading).where(Reading.machine_id == machine_id)
    )


async def _panel(client, machine_id, image):
    files = {"file": ("panel.jpg", jpeg(image), "image/jpeg")}
    return await client.post(
        "/api/v1/readings/panel-photo", data={"machine_id": str(machine_id)}, files=files, headers=BOT_HEADERS
    )


async def test_panel_values_are_never_saved_without_confirmation(client, session, operator):
    _, machine = operator
    response = await _panel(client, machine["id"], tool_image())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["saved"] is False
    assert {v["field"]: v["value"] for v in result["values"]} == {
        "spindle_rpm": 2800,
        "load_pct": 64,
        "temperature_c": 41,
    }
    assert [r["field"] for r in result["rejected"]] == ["operating_hours"]
    assert await _readings(session, machine["id"]) == 0  # suggestion only

    body = {
        "machine_id": machine["id"],
        "source": "panel",
        "spindle_rpm": 2800,
        "load_pct": 70,
        "temperature_c": 41,
    }
    assert (await client.post("/api/v1/readings", json=body, headers=BOT_HEADERS)).status_code == 201
    assert await _readings(session, machine["id"]) == 1  # saved only after the person confirmed


async def test_blurry_panel_photo_is_422(client, session, operator):
    _, machine = operator
    response = await _panel(client, machine["id"], blurred(tool_image()))
    assert response.status_code == 422 and response.json()["error"]["details"]["reasons"] == ["blurry"]
    assert await _readings(session, machine["id"]) == 0


async def test_out_of_range_panel_value_is_rejected(client, operator, monkeypatch):
    _, machine = operator
    monkeypatch.setitem(mock_fixtures.PANEL_VALUES, "metalworking", [("load_pct", 300, 0.9, "LOAD 300%")])
    result = (await _panel(client, machine["id"], tool_image())).json()
    assert result["values"] == [] and result["rejected"][0]["reason"].startswith("outside valid range")
