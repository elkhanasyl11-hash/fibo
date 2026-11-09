"""/start and registration: invite code -> role -> language -> POST /bot/register.

Deep links from the website:
  t.me/<bot>?start=<invite code>  operators/masters join the workshop without typing the code;
  t.me/<bot>?start=own<token>     the owner (or a master) attaches Telegram to their web account and
                                  from then on gets alerts about critical incidents ("stop the machine").
A payload that looks like neither is ignored.
"""

import html
import re

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.api_client import FiboApi, FiboApiError
from bot.handlers.common import load_user
from bot.states import Registration
from bot.texts import t

router = Router(name="start")
INVITE_PAYLOAD = re.compile(r"^[A-Za-z0-9]{4,16}$")
LINK_PREFIX = "own"


@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext, api: FiboApi, command: CommandObject) -> None:
    payload = (command.args or "").strip()
    if payload.startswith(LINK_PREFIX) and len(payload) > len(LINK_PREFIX) + 8:
        await _link_account(message, state, api, payload)
        return
    info = await load_user(api, state, message.from_user.id)
    if info is not None:
        lang = info["user"]["language"]
        await message.answer(
            f"{t(lang, 'already_registered')}\n\n{t(lang, 'how_to')}", reply_markup=keyboards.main_menu(lang)
        )
        return
    if INVITE_PAYLOAD.match(payload):
        await state.update_data(invite_code=payload)
        await state.set_state(Registration.role)
        await message.answer(
            t("ru", "invite_from_link", code=html.escape(payload.upper())), reply_markup=keyboards.roles("ru")
        )
        return
    await state.set_state(Registration.invite_code)
    await message.answer(t("ru", "ask_invite_code"))


@router.message(Registration.invite_code, F.text)
async def on_invite_code(message: Message, state: FSMContext) -> None:
    await state.update_data(invite_code=message.text.strip())
    await state.set_state(Registration.role)
    await message.answer(t("ru", "choose_role"), reply_markup=keyboards.roles("ru"))


@router.callback_query(Registration.role, F.data.startswith("role:"))
async def on_role(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(role=callback.data.split(":", 1)[1])
    await state.set_state(Registration.language)
    await callback.message.edit_text(t("ru", "choose_language"), reply_markup=keyboards.languages())
    await callback.answer()


@router.callback_query(Registration.language, F.data.startswith("lang:"))
async def on_language(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    lang = callback.data.split(":", 1)[1]
    data = await state.get_data()
    user = callback.from_user
    try:
        await api.register(user.id, user.full_name, data["invite_code"], data["role"], lang)
    except FiboApiError as exc:
        if exc.status != 404:
            raise
        await state.set_state(Registration.invite_code)
        await callback.message.edit_text(t(lang, "invite_not_found"))
        await callback.answer()
        return
    await state.clear()
    info = await load_user(api, state, user.id)
    await callback.message.edit_text(
        t(
            lang,
            "registered",
            name=html.escape(user.full_name),
            workshop=html.escape(info["workshop"]["name"]),
        )
    )
    await callback.message.answer(t(lang, "how_to"), reply_markup=keyboards.main_menu(lang))
    await callback.answer()


async def _link_account(message: Message, state: FSMContext, api: FiboApi, token: str) -> None:
    try:
        await api.link_account(message.from_user.id, token)
    except FiboApiError as exc:
        if exc.status not in {409, 422}:
            raise
        await message.answer(t("ru", "link_taken" if exc.status == 409 else "link_expired"))
        return
    await state.clear()
    info = await load_user(api, state, message.from_user.id)
    lang = info["user"]["language"]
    await message.answer(
        t(
            lang,
            "linked",
            name=html.escape(info["user"]["full_name"]),
            workshop=html.escape(info["workshop"]["name"]),
        ),
        reply_markup=keyboards.main_menu(lang),
    )
