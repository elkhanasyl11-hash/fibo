"""Typed messages outside any dialogue step: a problem description, or the answer to the
clarifying question of the last card (submit.py adds the previous description to it).
Included last, so menu buttons, registration and the other text steps are matched first."""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards
from bot.api_client import FiboApi
from bot.handlers.common import load_user
from bot.submit import ask_machine, pick_machine, submit
from bot.texts import t

router = Router(name="text")
MIN_LETTERS = 3


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def on_text(message: Message, state: FSMContext, api: FiboApi) -> None:
    info = await load_user(api, state, message.from_user.id)
    if info is None:
        await message.answer(t("ru", "not_registered"))
        return
    lang = info["user"]["language"]
    text = message.text.strip()
    if sum(ch.isalpha() for ch in text) < MIN_LETTERS:
        await message.answer(t(lang, "how_to"), reply_markup=keyboards.main_menu(lang))
        return
    if not info["machines"]:
        await message.answer(t(lang, "no_machines"))
        return
    item = {"kind": "text", "text": text}
    machine = pick_machine(await state.get_data(), info["machines"])
    if machine is None:
        await ask_machine(message, state, info, lang, item)
        return
    await submit(message, state, api, message.from_user.id, lang, machine, item)
