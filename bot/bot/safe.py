"""Telegram calls whose "failures" are harmless and must not reach the user as an error.

- "message is not modified": the person tapped the same button twice; the text is already right.
- "query is too old": a button tap was answered late (slow network, a busy backend); the spinner on
  the button has already gone, there is nothing left to answer.
"""

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger("fibo.bot.safe")
HARMLESS = ("message is not modified", "query is too old", "query id is invalid")


def is_harmless(exc: BaseException) -> bool:
    return isinstance(exc, TelegramBadRequest) and any(text in str(exc).lower() for text in HARMLESS)


async def answer_callback(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        if not is_harmless(exc):
            raise
        logger.info("late button answer skipped")


async def edit_text(message: Message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if not is_harmless(exc):
            raise
