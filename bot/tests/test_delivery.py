"""Polling with backoff, and safe (HTML-escaped) result text."""

import pytest

from bot import delivery
from bot.api_client import FiboApiError
from bot.delivery import poll_delays, result_text, wait_for_incident
from bot.texts import t


class FakeApi:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses, self.calls = statuses, 0

    async def get_incident(self, incident_id: int) -> dict:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return {"id": incident_id, "status": status, "card_text": "ok"}


def test_backoff_sequence():
    delays = poll_delays()
    assert [next(delays) for _ in range(6)] == [1, 2, 3, 5, 5, 5]


async def test_stops_when_open():
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    api = FakeApi(["received", "processing", "open"])
    incident = await wait_for_incident(api, 1, budget_s=60, sleep=sleep)
    assert incident["status"] == "open" and slept == [1, 2, 3]


async def test_gives_up_after_budget():
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    assert await wait_for_incident(FakeApi(["processing"]), 1, budget_s=60, sleep=sleep) is None
    assert sum(slept) <= 60 and slept[:4] == [1, 2, 3, 5]


def test_result_text_escapes_html_and_keeps_safety_header_on_failure():
    opened = {"status": "open", "card_text": "<b>ЧПУ</b> & Co"}
    assert result_text(opened, "ru") == "&lt;b&gt;ЧПУ&lt;/b&gt; &amp; Co"
    failed = {"status": "failed", "safety_triggered": True, "card_text": "⛔ НЕМЕДЛЕННО ОСТАНОВИТЕ СТАНОК"}
    text = result_text(failed, "ru")
    assert text.startswith("⛔ НЕМЕДЛЕННО") and "не удалось" in text.lower()
    assert result_text({"status": "failed", "safety_triggered": False, "card_text": None}, "kk").startswith(
        "Талдау"
    )


class FlakyApi:
    """Fails `failures` times in a row, then reports the incident as open."""

    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    async def get_incident(self, incident_id: int) -> dict:
        self.calls += 1
        if self.calls <= self.failures:
            raise FiboApiError(0, "unreachable")
        return {"id": incident_id, "status": "open", "card_text": "ok"}


async def _no_sleep(_seconds):
    return None


async def test_poll_survives_short_outages_but_not_long_ones():
    assert (await wait_for_incident(FlakyApi(2), 1, budget_s=60, sleep=_no_sleep))["status"] == "open"
    with pytest.raises(FiboApiError):
        await wait_for_incident(FlakyApi(3), 1, budget_s=60, sleep=_no_sleep)


class FakeMessage:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def answer(self, text, reply_markup=None):
        self.sent.append(text)


async def test_background_wait_tells_user_instead_of_going_silent(monkeypatch):
    message = FakeMessage()

    async def timeout(*args, **kwargs):
        return None

    monkeypatch.setattr(delivery, "wait_for_incident", timeout)
    await delivery._keep_waiting(message, None, 1, "ru")
    assert message.sent == [t("ru", "still_pending")]

    async def broken(*args, **kwargs):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(delivery, "wait_for_incident", broken)
    await delivery._keep_waiting(message, None, 1, "ru")
    assert message.sent[-1] == t("ru", "delivery_failed")
