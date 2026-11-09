"""submit.py: which machine, the message that waits for a machine, answers to clarifying questions."""

import json
from types import SimpleNamespace

import httpx
import pytest

from bot import delivery, keyboards, submit
from bot.api_client import FiboApi
from bot.texts import reason_text

MACHINES = [{"id": 1, "name": "ЧПУ-1"}, {"id": 2, "name": "Токарный-1"}]


def test_pick_machine_prefers_the_chosen_one_then_the_only_one():
    assert submit.pick_machine({"machine_id": 2}, MACHINES)["id"] == 2
    assert submit.pick_machine({}, MACHINES) is None
    assert submit.pick_machine({"machine_id": 99}, MACHINES[:1])["id"] == 1  # deleted machine -> the only one
    assert submit.pick_machine({}, MACHINES[:1])["id"] == 1


def test_clarifying_question_is_read_from_the_card():
    card = "🟡 ЧПУ-1: внимание\nГул\n\n❓ Шум постоянный или только при резании?\n\nУверенность: 58%"
    assert submit.clarifying_question(card) == "Шум постоянный или только при резании?"
    assert submit.clarifying_question("без вопроса") is None and submit.clarifying_question(None) is None


def test_followup_answer_carries_the_story():
    data = {
        "followup": {
            "machine_id": 1,
            "question": "Шум постоянный?",
            "description": "Станок гудит",
            "at": 1000,
        }
    }
    text = submit.with_followup("Только при резании", data, 1, now=1060)
    assert (
        text.startswith("Станок гудит") and "Шум постоянный?" in text and text.endswith("Только при резании")
    )
    assert (
        submit.with_followup("Только при резании", data, 2, now=1060) == "Только при резании"
    )  # other machine
    stale = 1000 + submit.FOLLOWUP_TTL_S + 1
    assert submit.with_followup("Только при резании", data, 1, now=stale) == "Только при резании"


def test_panel_rejection_reasons_are_translated():
    assert reason_text("outside valid range 0..150", "ru") == "вне допустимого диапазона 0–150"
    assert reason_text("not readable", "kk") == "оқылмайды"
    assert reason_text("something new", "ru") == "something new"


def test_card_buttons_and_answer_hint_follow_the_language():
    incident = {"id": 5, "status": "open", "manual_pages": [3], "card_text": "Гул\n❓ Когда?"}
    texts = [b.text for row in keyboards.card(incident, "kk").inline_keyboard for b in row]
    assert texts == ["✅ Шешілді", "🧰 Механикті шақыру", "📖 Төлқұжат беті"]
    assert "Ответьте на вопрос" in delivery.result_text(incident, "ru")
    assert "Ответьте" not in delivery.result_text({**incident, "card_text": "Гул"}, "ru")


async def test_ingest_text_body():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        return httpx.Response(202, json={"incident_id": 7})

    api = FiboApi("http://b/api/v1", "s", transport=httpx.MockTransport(handler))
    assert await api.ingest_text(42, 1, "шум") == 7
    assert seen == {
        "path": "/api/v1/ingest/text",
        "body": {"telegram_id": 42, "machine_id": 1, "text": "шум"},
    }


# ---------- the whole submit path with fakes ----------


class FakeState:
    def __init__(self, data=None):
        self.data, self.state = dict(data or {}), "Flow:awaiting_photo"

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **values):
        self.data.update(values)

    async def set_state(self, value):
        self.state = value

    async def get_state(self):
        return self.state


class FakeMessage:
    def __init__(self, sent):
        self.sent = sent
        self.chat = SimpleNamespace(id=100)
        self.bot = SimpleNamespace(id=1, send_chat_action=self._noop, download=self._download)

    async def _noop(self, **kwargs):
        return True

    async def _download(self, file_id):
        import io

        return io.BytesIO(b"audio-bytes")

    async def answer(self, text, reply_markup=None):
        self.sent.append(text)
        return self

    async def delete(self):
        return True

    async def edit_text(self, text):
        self.sent.append(text)


class FakeApi:
    def __init__(self, card_text):
        self.calls, self.card_text = [], card_text

    async def ingest_text(self, telegram_id, machine_id, text):
        self.calls.append(("text", machine_id, text))
        return 9

    async def ingest_voice(self, telegram_id, machine_id, data, filename, mode, content_type):
        self.calls.append(("voice", machine_id, data, mode))
        return 9

    async def get_incident(self, incident_id):
        return {
            "id": 9,
            "status": "open",
            "card_text": self.card_text,
            "transcript": "Станок гудит",
            "manual_pages": [],
        }


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch):
    monkeypatch.setattr(delivery, "poll_delays", lambda: iter([0, 0, 0]))


async def test_waiting_voice_is_sent_after_the_machine_tap_and_question_is_remembered():
    sent, state = (
        [],
        FakeState(
            {
                "pending": {
                    "kind": "voice",
                    "file_id": "f1",
                    "filename": "v.ogg",
                    "content_type": "audio/ogg",
                    "mode": "auto",
                }
            }
        ),
    )
    api = FakeApi("Гул\n❓ Шум постоянный?")
    item = (await state.get_data())["pending"]
    await submit.submit(FakeMessage(sent), state, api, 42, "ru", MACHINES[1], item)
    assert api.calls == [("voice", 2, b"audio-bytes", "auto")]
    assert sent[0] == "⏳ Анализирую · Токарный-1…" and "Ответьте на вопрос" in sent[-1]
    assert state.data["pending"] is None and state.data["machine_id"] == 2 and state.state is None
    assert state.data["followup"]["question"] == "Шум постоянный?"

    await submit.submit(
        FakeMessage(sent), state, api, 42, "ru", MACHINES[1], {"kind": "text", "text": "Да, всегда"}
    )
    kind, machine_id, text = api.calls[-1]
    assert kind == "text" and "Станок гудит" in text and text.endswith("Да, всегда")
    assert state.data["followup"]["question"] == "Шум постоянный?"  # the new card asked again


async def test_link_account_body():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        return httpx.Response(200, json={"user": {}, "workshop": {}, "machines": []})

    api = FiboApi("http://b/api/v1", "s", transport=httpx.MockTransport(handler))
    await api.link_account(42, "own7x1999999999xabc")
    assert seen == {"path": "/api/v1/bot/link", "body": {"telegram_id": 42, "token": "own7x1999999999xabc"}}


def test_double_taps_and_late_answers_are_harmless():
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import AnswerCallbackQuery

    from bot.safe import is_harmless

    method = AnswerCallbackQuery(callback_query_id="1")
    assert is_harmless(TelegramBadRequest(method, "Bad Request: message is not modified: same content"))
    assert is_harmless(
        TelegramBadRequest(method, "Bad Request: query is too old and response timeout expired")
    )
    assert not is_harmless(TelegramBadRequest(method, "Bad Request: chat not found"))
    assert not is_harmless(ValueError("message is not modified"))
