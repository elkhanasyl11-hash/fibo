"""Periodic risk recompute, Telegram alerts to owners/masters, and linking an owner's Telegram.

No network: Telegram is an httpx.MockTransport injected into app.modules.notify.
"""

import json
import uuid
from datetime import timedelta

import httpx
import pytest

from app.core import passwords
from app.core.config import settings
from app.db.base import utcnow
from app.modules import notify
from app.modules.machine import scheduler
from tests.conftest import BOT_HEADERS


async def _owner(client, profile="metalworking") -> dict:
    body = {
        "email": f"o-{uuid.uuid4().hex[:8]}@example.kz",
        "password": "correct horse 42",
        "full_name": "Гульнара",
        "workshop": {"name": "Цех", "profile": profile},
    }
    return (await client.post("/api/v1/auth/register", json=body)).json()


def _auth(owner: dict) -> dict:
    return {"Authorization": f"Bearer {owner['token']}"}


async def _join(client, invite_code: str, telegram_id: int, role="operator", language="ru") -> None:
    body = {
        "telegram_id": telegram_id,
        "full_name": "Айбек",
        "invite_code": invite_code,
        "role": role,
        "language": language,
    }
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 201


def _tg_id() -> int:
    return 700_000_000 + uuid.uuid4().int % 100_000_000


# ---------- linking the owner's Telegram ----------


def test_link_token_round_trip_and_tamper():
    token, expires = passwords.issue_link_token(12, now=1_000_000)
    assert token.startswith("own12x") and len(token) <= 64 and token.isalnum()
    assert passwords.read_link_token(token, now=1_000_001) == 12
    assert passwords.read_link_token(token, now=expires + 1) is None
    assert passwords.read_link_token(token.replace("own12x", "own13x"), now=1_000_001) is None
    assert passwords.read_link_token(passwords.issue_token(12), now=1_000_001) is None  # session token


async def test_owner_links_telegram_through_the_bot(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_username", "FiboTestBot")
    owner = await _owner(client)
    issued = (await client.post("/api/v1/auth/telegram-link", headers=_auth(owner))).json()
    assert issued["linked"] is False and issued["link"].startswith("https://t.me/FiboTestBot?start=own")
    token, telegram_id = issued["link"].split("start=")[1], _tg_id()

    body = {"telegram_id": telegram_id, "token": token}
    linked = await client.post("/api/v1/bot/link", json=body, headers=BOT_HEADERS)
    assert linked.status_code == 200, linked.text
    assert linked.json()["user"]["role"] == "owner"
    assert linked.json()["workshop"]["id"] == owner["workshop"]["id"]
    me = (await client.get("/api/v1/auth/me", headers=_auth(owner))).json()
    assert me["user"]["telegram_id"] == telegram_id
    assert (await client.post("/api/v1/auth/telegram-link", headers=_auth(owner))).json()["linked"] is True


async def test_link_moves_a_bot_only_registration_but_never_another_web_account(client):
    owner, other_owner = await _owner(client), await _owner(client)
    telegram_id = _tg_id()
    await _join(client, owner["workshop"]["invite_code"], telegram_id, role="master")  # same person, bot-only
    token, _ = passwords.issue_link_token(owner["user"]["id"])
    body = {"telegram_id": telegram_id, "token": token}
    assert (await client.post("/api/v1/bot/link", json=body, headers=BOT_HEADERS)).status_code == 200
    bot_user = (await client.get(f"/api/v1/bot/users/{telegram_id}", headers=BOT_HEADERS)).json()
    assert bot_user["user"]["id"] == owner["user"]["id"]  # the Telegram now opens the owner account

    stolen, _ = passwords.issue_link_token(other_owner["user"]["id"])
    body = {"telegram_id": telegram_id, "token": stolen}
    assert (await client.post("/api/v1/bot/link", json=body, headers=BOT_HEADERS)).status_code == 409


async def test_link_rejects_bad_tokens_and_needs_the_bot(client):
    owner = await _owner(client)
    expired, _ = passwords.issue_link_token(owner["user"]["id"], now=1_000)
    body = {"telegram_id": _tg_id(), "token": expired}
    assert (await client.post("/api/v1/bot/link", json=body, headers=BOT_HEADERS)).status_code == 422
    assert (await client.post("/api/v1/bot/link", json=body)).status_code == 401
    client.cookies.clear()  # Registration now authenticates the browser with a session cookie.
    assert (await client.post("/api/v1/auth/telegram-link")).status_code == 401


# ---------- alerts ----------


class TelegramStub:
    def __init__(self, status=200):
        self.sent, self.status = [], status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sendMessage") and "test-token" in request.url.path
        self.sent.append(json.loads(request.content))
        return httpx.Response(self.status, json={"ok": self.status == 200})


@pytest.fixture
def telegram(monkeypatch):
    stub = TelegramStub()
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(notify, "_transport", httpx.MockTransport(stub))
    return stub


async def _workshop_with_people(client, make_machine):
    owner = await _owner(client)
    machine = await make_machine(owner["workshop"]["id"])
    owner_tg, master_tg, operator_tg = _tg_id(), _tg_id(), _tg_id()
    token, _ = passwords.issue_link_token(owner["user"]["id"])
    body = {"telegram_id": owner_tg, "token": token}
    assert (await client.post("/api/v1/bot/link", json=body, headers=BOT_HEADERS)).status_code == 200
    await _join(client, owner["workshop"]["invite_code"], master_tg, role="master", language="kk")
    await _join(client, owner["workshop"]["invite_code"], operator_tg)
    return machine, owner_tg, master_tg, operator_tg


async def _report(client, telegram_id, machine_id, text) -> dict:
    body = {"telegram_id": telegram_id, "machine_id": machine_id, "text": text}
    response = await client.post("/api/v1/ingest/text", json=body, headers=BOT_HEADERS)
    return (await client.get(f"/api/v1/incidents/{response.json()['incident_id']}")).json()


async def test_stop_the_machine_alert_reaches_owner_and_master(client, make_machine, telegram):
    machine, owner_tg, master_tg, operator_tg = await _workshop_with_people(client, make_machine)
    incident = await _report(client, operator_tg, machine["id"], "Из двигателя пошёл дым")
    assert incident["safety_triggered"] is True
    by_chat = {m["chat_id"]: m["text"] for m in telegram.sent}
    assert set(by_chat) == {owner_tg, master_tg}  # not the operator who reported it
    assert by_chat[owner_tg].startswith("⛔ <b>Остановите станок") and "Сообщил: Айбек" in by_chat[owner_tg]
    assert by_chat[master_tg].startswith("⛔ <b>Станокты тоқтатыңыз")  # the master's language
    assert f"/app/machines/{machine['id']}" in by_chat[owner_tg]


async def test_no_alert_for_a_normal_card(client, make_machine, telegram):
    machine, *_, operator_tg = await _workshop_with_people(client, make_machine)
    incident = await _report(client, operator_tg, machine["id"], "Шпиндель гудит на высоких оборотах")
    assert incident["level"] in {"normal", "warning"} and telegram.sent == []


async def test_alerts_off_without_token_and_failures_never_break_the_pipeline(
    client, make_machine, monkeypatch
):
    stub = TelegramStub(status=403)
    monkeypatch.setattr(notify, "_transport", httpx.MockTransport(stub))
    machine, *_, operator_tg = await _workshop_with_people(client, make_machine)
    incident = await _report(client, operator_tg, machine["id"], "Из двигателя пошёл дым")
    assert incident["status"] == "open" and stub.sent == []  # no token configured in tests
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    assert await notify.notify_incident(incident["id"]) == 0 and len(stub.sent) == 2  # 403s: none delivered


# ---------- periodic recompute ----------


async def test_scheduler_scores_unscored_and_stale_machines_only(client, make_workshop, make_machine):
    workshop = await make_workshop()
    fresh = await make_machine(
        workshop["id"],
        last_maintenance_at=(utcnow() - timedelta(days=40)).isoformat(),
        maintenance_interval_hours=200,
    )
    never = await make_machine(workshop["id"], name="ЧПУ-2")
    recompute = await client.post("/api/v1/risk-scores/recompute", json={"machine_id": fresh["id"]})
    assert recompute.status_code == 200

    due = await scheduler.due_machine_ids(timedelta(minutes=30))
    assert never["id"] in due and fresh["id"] not in due
    assert fresh["id"] in await scheduler.due_machine_ids(timedelta(seconds=0))

    assert await scheduler.recompute_due(timedelta(minutes=30)) >= 1
    history = (await client.get(f"/api/v1/machines/{never['id']}/risk-history")).json()
    assert len(history) == 1
    assert never["id"] not in await scheduler.due_machine_ids(timedelta(minutes=30))


async def test_scheduler_is_off_with_zero_minutes():
    assert settings.risk_recompute_minutes == 0
    assert await scheduler.run_forever() is None  # returns at once instead of looping


async def test_daily_history_keeps_the_last_score_of_each_day(client, session, make_workshop, make_machine):
    from app.models import RiskScore

    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    base = utcnow().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=3)
    for hours, risk in [(0, 0.1), (5, 0.2), (24, 0.3), (25, 0.4), (49, 0.5)]:
        session.add(
            RiskScore(
                machine_id=machine["id"],
                computed_at=base + timedelta(hours=hours),
                failure_probability=None,
                risk_index=risk,
                priority_kzt=1000,
                is_anomaly=False,
                inputs_used=[],
                model_version="none",
                shap_factors=[],
            )
        )
    await session.commit()
    url = f"/api/v1/machines/{machine['id']}/risk-history"
    daily = (await client.get(url, params={"daily": "true"})).json()
    assert [s["risk_index"] for s in daily] == [0.2, 0.4, 0.5]
    assert len((await client.get(url, params={"limit": 2})).json()) == 2  # paging still works without daily
