"""One path for everything an operator reports: voice, machine sound, tool photo, typed text.

1. Which machine: the one chosen earlier, or the only machine of the workshop. Otherwise the
   message is kept in FSM data ("pending", Telegram file_id or text) and the bot asks which machine;
   after the tap it is sent without asking the operator to record it again.
2. Upload to the backend, "⏳ Analysing · <machine>" plus the "typing…" indicator, then the card.
3. A card that ends with a clarifying question (❓) remembers the question for FOLLOWUP_TTL_S: a typed
   answer is sent together with the original description, so the new card knows the whole story.
"""

import html
import time

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards
from bot.api_client import FiboApi
from bot.delivery import deliver_card_when_ready
from bot.texts import t

FOLLOWUP_TTL_S = 30 * 60
QUESTION_MARK = "❓"


def pick_machine(data: dict, machines: list[dict]) -> dict | None:
    """The machine chosen earlier (if it still exists), else the only machine, else None."""
    chosen = next((m for m in machines if m["id"] == data.get("machine_id")), None)
    if chosen is not None:
        return chosen
    return machines[0] if len(machines) == 1 else None


async def ask_machine(message: Message, state: FSMContext, info: dict, lang: str, pending: dict) -> None:
    await state.update_data(pending=pending)
    await message.answer(t(lang, "which_machine"), reply_markup=keyboards.machines(info["machines"], "go"))


def clarifying_question(card_text: str | None) -> str | None:
    for line in (card_text or "").splitlines():
        if line.startswith(QUESTION_MARK):
            return line.removeprefix(QUESTION_MARK).strip() or None
    return None


def with_followup(text: str, data: dict, machine_id: int, now: float | None = None) -> str:
    """Prefix a typed answer with the previous description and question (same machine, recent)."""
    followup = data.get("followup") or {}
    fresh = (now or time.time()) - followup.get("at", 0) <= FOLLOWUP_TTL_S
    if not fresh or followup.get("machine_id") != machine_id or not followup.get("question"):
        return text
    before = followup.get("description") or ""
    return f"{before}\n\nУточняющий вопрос Fibo: {followup['question']}\nОтвет оператора: {text}".strip()


async def _ingest(
    bot: Bot, api: FiboApi, telegram_id: int, machine_id: int, item: dict, text: str | None
) -> int:
    if item["kind"] == "text":
        return await api.ingest_text(telegram_id, machine_id, text or item["text"])
    data = (await bot.download(item["file_id"])).read()
    if item["kind"] == "photo":
        return await api.ingest_photo(telegram_id, machine_id, data, item.get("caption"))
    return await api.ingest_voice(
        telegram_id, machine_id, data, item["filename"], mode=item["mode"], content_type=item["content_type"]
    )


async def submit(
    message: Message, state: FSMContext, api: FiboApi, telegram_id: int, lang: str, machine: dict, item: dict
) -> None:
    """Send one report for `machine` and deliver its card. `message` is where the bot answers."""
    data = await state.get_data()
    text = with_followup(item["text"], data, machine["id"]) if item["kind"] == "text" else None
    await state.update_data(
        machine_id=machine["id"], machine_name=machine["name"], pending=None, followup=None
    )
    await state.set_state(None)
    incident_id = await _ingest(message.bot, api, telegram_id, machine["id"], item, text)
    status_msg = await message.answer(t(lang, "analyzing_machine", machine=html.escape(machine["name"])))
    incident = await deliver_card_when_ready(message, api, incident_id, status_msg, lang)
    question = clarifying_question(incident.get("card_text")) if incident else None
    if question and incident["status"] == "open":
        description = incident.get("transcript") or incident.get("verdict") or ""
        await state.update_data(
            followup={
                "machine_id": machine["id"],
                "question": question,
                "description": description,
                "at": time.time(),
            }
        )
