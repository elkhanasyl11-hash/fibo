"""Waiting for the backend to finish an incident, then sending the card.

After an ingest returns 202 the bot polls GET /incidents/{id} with growing pauses
(1, 2, 3, 5, 5, 5 … s). Within 60 s: the card (OPEN) or the failure message (FAILED) is sent.
After 60 s the user is told it takes longer, and a background task keeps polling up to 3 min.
All dynamic text is HTML-escaped because messages use parse_mode=HTML.
"""

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable

from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from bot import keyboards
from bot.api_client import FiboApi, FiboApiError
from bot.texts import t

logger = logging.getLogger("fibo.bot.delivery")

FINAL_STATUSES = {"open", "failed", "resolved"}
MAX_POLL_ERRORS = 3  # one network hiccup must not abort the wait; three in a row is a real problem
FIRST_WAIT_S = 60
TOTAL_WAIT_S = 180
_background: set[asyncio.Task] = set()  # keep references so running tasks are not garbage-collected


def poll_delays():
    """1, 2, 3, then 5 s forever."""
    yield from (1, 2, 3)
    while True:
        yield 5


async def wait_for_incident(
    api: FiboApi, incident_id: int, budget_s: float, sleep: Callable[[float], Awaitable] = asyncio.sleep
) -> dict | None:
    """Poll until the incident is final or the time budget is used up (then None).

    Up to MAX_POLL_ERRORS failed polls in a row are tolerated (logged); after that the error is raised.
    """
    waited, errors_in_a_row = 0.0, 0
    for delay in poll_delays():
        if waited + delay > budget_s:
            return None
        await sleep(delay)
        waited += delay
        try:
            incident = await api.get_incident(incident_id)
        except FiboApiError:
            errors_in_a_row += 1
            logger.warning(
                "poll failed", extra={"incident_id": incident_id, "errors_in_a_row": errors_in_a_row}
            )
            if errors_in_a_row >= MAX_POLL_ERRORS:
                raise
            continue
        errors_in_a_row = 0
        if incident["status"] in FINAL_STATUSES:
            return incident
    return None


def result_text(incident: dict, lang: str) -> str:
    """Card text for an OPEN incident; safety header (if any) + failure note for a FAILED one.
    A card that asks a clarifying question (❓) tells the operator they can simply answer."""
    card = html.escape(incident.get("card_text") or "")
    if incident["status"] == "failed":
        prefix = f"{card}\n\n" if incident.get("safety_triggered") and card else ""
        return prefix + t(lang, "failed")
    if incident["status"] == "open" and "❓" in card:
        return f"{card}\n\n{t(lang, 'answer_hint')}"
    return card


async def send_result(message: Message, incident: dict, lang: str) -> None:
    markup = keyboards.card(incident, lang) if incident["status"] == "open" else None
    await message.answer(result_text(incident, lang), reply_markup=markup)


async def _tell_user(message: Message, text: str, incident_id: int) -> None:
    """Last-resort notice; if Telegram itself fails here, log it (nothing else can reach the user)."""
    try:
        await message.answer(text)
    except Exception:  # logged with traceback: the user cannot be reached through Telegram right now
        logger.exception("could not notify user", extra={"incident_id": incident_id})


async def _keep_waiting(message: Message, api: FiboApi, incident_id: int, lang: str) -> None:
    """Background continuation (outside aiogram's error handler), so it must tell the user itself."""
    try:
        incident = await wait_for_incident(api, incident_id, TOTAL_WAIT_S - FIRST_WAIT_S)
        if incident is None:
            await _tell_user(message, t(lang, "still_pending"), incident_id)
            return
        await send_result(message, incident, lang)
    except Exception:  # API down, Telegram error, ...: logged, and the user is told instead of silence
        logger.exception("delivering the card failed", extra={"incident_id": incident_id})
        await _tell_user(message, t(lang, "delivery_failed"), incident_id)


async def deliver_card_when_ready(
    message: Message, api: FiboApi, incident_id: int, status_msg: Message, lang: str
) -> dict | None:
    """Send the card; returns the incident when it arrived within FIRST_WAIT_S, else None (a
    background task keeps waiting). "typing…" is shown in the chat while the backend works."""
    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        incident = await wait_for_incident(api, incident_id, FIRST_WAIT_S)
    if incident is not None:
        await status_msg.delete()
        await send_result(message, incident, lang)
        return incident
    await status_msg.edit_text(t(lang, "taking_longer"))
    task = asyncio.create_task(_keep_waiting(message, api, incident_id, lang))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return None
