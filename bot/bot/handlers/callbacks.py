"""Card buttons: res:<id> Resolved, esc:<id> Call mechanic, pg:<id> manual pages."""

import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.api_client import FiboApi, FiboApiError
from bot.handlers.common import language
from bot.texts import t

router = Router(name="callbacks")
logger = logging.getLogger("fibo.bot.callbacks")


def _incident_id(callback: CallbackQuery) -> int:
    return int(callback.data.split(":", 1)[1])


@router.callback_query(F.data.startswith("res:"))
async def on_resolved(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    lang = await language(state)
    try:
        incident = await api.resolve(_incident_id(callback))
    except FiboApiError as exc:
        if exc.status != 409:
            raise
        await callback.answer(t(lang, "already_resolved"), show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        t(lang, "resolved", hours=round(incident["downtime_hours"], 1), loss=incident["loss_kzt"])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("esc:"))
async def on_escalate(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    lang = await language(state)
    target = await api.escalate(_incident_id(callback))
    text = t(
        lang,
        "master_alert",
        machine=html.escape(target["machine_name"]),
        card=html.escape(target["card_text"] or ""),
    )
    sent = 0
    for telegram_id in target["master_telegram_ids"]:
        if telegram_id == callback.from_user.id:
            continue
        try:
            await callback.bot.send_message(telegram_id, text)
            sent += 1
        except TelegramAPIError:  # e.g. this master never opened the bot; notify the others anyway
            logger.warning("could not notify master", extra={"telegram_id": telegram_id})
    await callback.answer(
        t(lang, "escalated", count=sent) if sent else t(lang, "no_masters"), show_alert=True
    )


@router.callback_query(F.data.startswith("pg:"))
async def on_pages(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    """Send the stored text of every manual page cited on the card."""
    lang = await language(state)
    excerpts = await api.manual_excerpts(_incident_id(callback))
    if not excerpts:
        await callback.message.answer(t(lang, "no_pages"))
    for excerpt in excerpts:
        text = t(lang, "page_excerpt", page=excerpt["page"], text=html.escape(excerpt["text"]))
        await callback.message.answer(text)
    await callback.answer()
