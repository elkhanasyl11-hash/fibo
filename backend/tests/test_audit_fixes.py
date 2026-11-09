"""Fixes from the spec audit: paging on every list, risk-history offset, Vision tag, demo label on scores."""

from sqlalchemy import select

from app.db.base import IndexStatus
from app.db.seed import seed
from app.main import app
from app.models import Machine, Manual
from tests.image_samples import jpeg, tool_image


async def test_baselines_and_manuals_lists_page(client, session, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    for _ in range(3):
        files = {"file": ("ref.jpg", jpeg(tool_image()), "image/jpeg")}
        assert (
            await client.post(f"/api/v1/machines/{machine['id']}/baselines/photo", files=files)
        ).status_code == 201
        session.add(
            Manual(
                machine_id=machine["id"],
                file_path="manual/x.pdf",
                original_filename="x.pdf",
                index_status=IndexStatus.READY,
            )
        )
    await session.commit()
    for resource in ("baselines", "manuals"):
        url = f"/api/v1/machines/{machine['id']}/{resource}"
        everything = (await client.get(url)).json()
        first_two = (await client.get(url, params={"limit": 2})).json()
        rest = (await client.get(url, params={"limit": 2, "offset": 2})).json()
        assert len(everything) == 3 and [i["id"] for i in first_two + rest] == [i["id"] for i in everything]
        assert (await client.get(url, params={"limit": 500})).status_code == 422


async def test_risk_history_offset_is_used(client, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    for _ in range(3):
        await client.post("/api/v1/risk-scores/recompute", json={"machine_id": machine["id"]})
    url = f"/api/v1/machines/{machine['id']}/risk-history"
    everything = (await client.get(url)).json()
    second = (await client.get(url, params={"limit": 1, "offset": 1})).json()
    assert len(everything) == 3 and [s["id"] for s in second] == [everything[1]["id"]]


def test_vision_endpoints_are_tagged_fibo_vision():
    spec = app.openapi()["paths"]
    for path in (
        "/api/v1/readings/panel-photo",
        "/api/v1/machines/{machine_id}/baselines/photo",
        "/api/v1/ingest/photo",
    ):
        assert spec[path]["post"]["tags"] == ["Fibo Vision"], path
    assert spec["/api/v1/readings"]["post"]["tags"] == ["Fibo Machine"]  # neighbours unchanged


async def test_risk_scores_say_whether_they_are_demo_data(client, session, make_workshop, make_machine):
    await seed(session, reset=True, risk_history_days=0)
    demo = await session.scalar(select(Machine).where(Machine.is_demo, Machine.name == "ЧПУ-1 фрезерный"))
    real = await make_machine((await make_workshop())["id"])

    history = (await client.get(f"/api/v1/machines/{demo.id}/risk-history")).json()
    assert history and all(score["is_demo"] is True for score in history)
    summary = (await client.get(f"/api/v1/machines/{demo.id}/summary")).json()
    assert summary["latest_risk"]["is_demo"] is True
    what_if = (
        await client.post(
            "/api/v1/risk-scores/what-if",
            json={"machine_id": demo.id, "overrides": {"maintenance_done": True}},
        )
    ).json()
    assert what_if["current"]["is_demo"] is True and what_if["scenario"]["is_demo"] is True

    recomputed = (await client.post("/api/v1/risk-scores/recompute", json={"machine_id": real["id"]})).json()
    assert recomputed[0]["is_demo"] is False
