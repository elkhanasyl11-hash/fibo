"""Masters upload a machine's PDF manual from Telegram; the bot reports when it is searchable."""

import asyncio
import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards
from bot.api_client import FiboApi
from bot.states import Flow
from bot.texts import t

router = Router(name="manuals")
POLL_SECONDS, MAX_POLLS = 3, 40  # up to 2 minutes


async def wait_until_indexed(api: FiboApi, manual_id: int, sleep=asyncio.sleep) -> dict | None:
    for _ in range(MAX_POLLS):
        manual = await api.get_manual(manual_id)
        if manual["index_status"] in {"ready", "failed"}:
            return manual
        await sleep(POLL_SECONDS)
    return None


@router.message(Flow.awaiting_manual, F.document)
async def on_manual(message: Message, state: FSMContext, api: FiboApi) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    document = message.document
    if document.mime_type != "application/pdf" and not (document.file_name or "").lower().endswith(".pdf"):
        await message.answer(t(lang, "not_pdf"))
        return
    content = (await message.bot.download(document)).read()
    manual = await api.upload_manual(data["machine_id"], content, document.file_name or "manual.pdf")
    await state.set_state(None)
    status_msg = await message.answer(t(lang, "manual_indexing"))
    result = await wait_until_indexed(api, manual["id"])
    if result is None:
        await status_msg.edit_text(t(lang, "manual_slow"))
    elif result["index_status"] == "ready":
        await status_msg.edit_text(t(lang, "manual_ready", pages=result["page_count"]))
    else:
        await status_msg.edit_text(
            t(lang, "manual_failed", reason=html.escape(result["error_message"] or ""))
        )
    await message.answer(t(lang, "menu"), reply_markup=keyboards.main_menu(lang))
