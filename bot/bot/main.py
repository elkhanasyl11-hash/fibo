"""Fibo Telegram bot entry point (long polling, no webhook / public HTTPS needed).

Run from bot/:  python -m bot.main
The FiboApi client is created once and passed to every handler as the `api` argument.
A global error handler logs every exception and answers with a short apology, so one failing
update never stops the polling loop.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.api_client import FiboApi, FiboApiError
from bot.config import settings
from bot.handlers import callbacks, machines, manuals, photo, start, text, voice
from bot.safe import is_harmless
from bot.texts import t

logger = logging.getLogger("fibo.bot")


async def on_error(event: ErrorEvent) -> bool:
    if is_harmless(event.exception):  # double tap / late answer: nothing went wrong for the user
        logger.info("harmless Telegram reply ignored: %s", event.exception)
        return True
    logger.exception("update failed", exc_info=event.exception)
    unreachable = isinstance(event.exception, FiboApiError) and event.exception.code == "unreachable"
    text = t("ru", "api_unreachable" if unreachable else "error")
    update = event.update
    try:
        if update.message:
            await update.message.answer(text)
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
    except TelegramAPIError:  # the apology itself failed (blocked bot, expired query): log, keep polling
        logger.exception("could not send the error reply")
    return True  # handled: polling continues


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_routers(
        start.router,
        machines.router,
        voice.router,
        photo.router,
        manuals.router,
        callbacks.router,
        text.router,
    )  # text last: it catches any typed message the other steps did not take
    dispatcher.errors.register(on_error)
    return dispatcher


async def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not settings.telegram_bot_token:
        raise SystemExit("FIBO_TELEGRAM_BOT_TOKEN is not set (get one from @BotFather)")
    if settings.bot_shared_secret == "change-me":
        logger.warning(
            "FIBO_BOT_SHARED_SECRET is the default 'change-me': fine locally, change it before deploying"
        )
    api = FiboApi(settings.api_url, settings.bot_shared_secret, settings.api_timeout_s)
    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await build_dispatcher().start_polling(bot, api=api)
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
