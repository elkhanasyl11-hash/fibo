"""Registration, workshop boundaries, real chart data, and read-only assistant diagnostics."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core import passwords
from app.core.config import settings
from app.db.base import utcnow
from app.models.reading import Reading
from app.models.risk_score import RiskScore
from app.modules.assistant.tools import run_tool


def signup():
    return {
        "email": f"qa-{uuid.uuid4().hex[:12]}@example.test",
        "password": "test-password-2026",
        "full_name": "Тестовый владелец",
        "workshop": {"name": "Тест регистрации", "city": "Шымкент", "profile": "metalworking"},
    }


async def test_cookie_session_and_logout(client):
    response = await client.post("/api/v1/auth/register", json=signup())
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_identity_normalization_and_whitespace_validation(client):
    body = signup()
    body["email"] = f"  {body['email'].upper()}  "
    response = await client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201
    assert response.json()["user"]["email"] == body["email"].strip().lower()
    bad = signup()
    bad["workshop"]["name"] = "   "
    assert (await client.post("/api/v1/auth/register", json=bad)).status_code == 422


async def test_browser_cannot_read_or_modify_another_workshop(client, make_workshop, make_machine):
    other = await make_workshop()
    machine = await make_machine(other["id"])
    own = (await client.post("/api/v1/auth/register", json=signup())).json()
    headers = {"Authorization": f"Bearer {own['token']}"}
    assert (await client.get(f"/api/v1/machines/{machine['id']}", headers=headers)).status_code == 404
    assert (
        await client.post(
            "/api/v1/readings", headers=headers, json={"machine_id": machine["id"], "temperature_c": 45}
        )
    ).status_code == 404
    assert (
        await client.get("/api/v1/reports/activity", headers=headers, params={"workshop_id": other["id"]})
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/ai/assistant/chat",
            headers=headers,
            json={"workshop_id": other["id"], "messages": [{"role": "user", "content": "Рейтинг риска"}]},
        )
    ).status_code == 404
    assert (
        await client.get("/api/v1/machines", headers=headers, params={"workshop_id": own["workshop"]["id"]})
    ).status_code == 200


async def test_protected_api_requires_sign_in_in_development(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    assert (await client.get("/api/v1/machines", params={"workshop_id": 1})).status_code == 401
    assert (await client.get("/api/v1/profiles")).status_code == 200


def test_local_signing_key_survives_process_secret_change(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "web_session_secret", None)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    token = passwords.issue_token(42)
    monkeypatch.setattr(passwords, "_DEV_SECRET", "a-new-process-secret")
    assert passwords.read_token(token) == 42
    assert (tmp_path / "web-session.key").stat().st_mode & 0o777 == 0o600


async def test_daily_activity_uses_local_day_and_excludes_other_workshops(
    client, session, make_workshop, make_machine, monkeypatch
):
    from app.api.v1 import activity

    workshop = await make_workshop()
    other = await make_workshop()
    machine = await make_machine(workshop["id"])
    foreign = await make_machine(other["id"])
    monkeypatch.setattr(activity, "utcnow", lambda: datetime(2026, 11, 9, 21, 30, tzinfo=UTC))
    for target, stamp in [
        (machine, datetime(2026, 11, 9, 20, tzinfo=UTC)),
        (machine, datetime(2026, 11, 9, 18, tzinfo=UTC)),
        (foreign, datetime(2026, 11, 9, 20, tzinfo=UTC)),
    ]:
        session.add(Reading(machine_id=target["id"], recorded_at=stamp, source="form", temperature_c=40))
    await session.commit()
    response = await client.get(
        "/api/v1/reports/activity",
        params={"workshop_id": workshop["id"], "days": 7, "utc_offset_minutes": 300},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["to"] == "2026-11-10" and len(data["days"]) == 7
    assert data["days"][-1]["readings"] == 1 and data["days"][-2]["readings"] == 1
    assert sum(day["readings"] for day in data["days"]) == 2


async def test_reading_trends_and_maintenance_scenario_do_not_write(session, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    for temp in (40, 52):
        session.add(
            Reading(machine_id=machine["id"], recorded_at=utcnow(), source="form", temperature_c=temp)
        )
    await session.commit()
    result = await run_tool(
        session, workshop["id"], "get_reading_trends", {"machine_name_or_id": str(machine["id"]), "days": 7}
    )
    assert result.data["fields"]["temperature_c"]["change"] == 12
    before = await session.scalar(select(func.count()).select_from(RiskScore))
    scenario = await run_tool(
        session, workshop["id"], "compare_maintenance", {"machine_name_or_id": str(machine["id"])}
    )
    assert scenario.data["saved"] is False
    assert await session.scalar(select(func.count()).select_from(RiskScore)) == before
    bad = await run_tool(
        session,
        workshop["id"],
        "get_reading_trends",
        {"machine_name_or_id": str(machine["id"]), "days": 1000},
    )
    assert "error" in bad.data


async def test_chat_knows_trends_and_labels_builtin_mode(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"], name="ЧПУ-22")
    await client.post("/api/v1/readings", json={"machine_id": machine["id"], "temperature_c": 40})
    response = await client.post(
        "/api/v1/ai/assistant/chat",
        json={
            "workshop_id": workshop["id"],
            "mode": "offline",
            "messages": [{"role": "user", "content": "Как менялась температура ЧПУ-22 за неделю?"}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "builtin"
    assert response.json()["tools_used"] == ["get_reading_trends"]
    assert "40" in response.json()["answer"]


async def test_registration_works_without_exposing_integration_key(client, monkeypatch):
    monkeypatch.setattr(settings, "dashboard_api_key", "integration-key-kept-on-server")
    response = await client.post("/api/v1/auth/register", json=signup())
    assert response.status_code == 201
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    client.cookies.clear()
    assert (
        await client.get("/api/v1/machines", params={"workshop_id": response.json()["workshop"]["id"]})
    ).status_code == 401
