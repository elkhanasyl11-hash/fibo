"""Main-menu buttons, choosing a machine, and adding a machine (masters only).

Every action first asks which machine; the choice is remembered in FSM data (machine_id).
"""

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.api_client import FiboApi
from bot.handlers.common import language, load_user
from bot.safe import answer_callback, edit_text
from bot.states import AddMachine, Flow
from bot.submit import submit
from bot.texts import MENU_ACTIONS, t

router = Router(name="machines")

# action -> (state that waits for the next voice/photo, prompt text)
PHOTO_ACTIONS = {
    "baseline": (Flow.awaiting_baseline, "send_baseline"),
    "photo": (Flow.awaiting_photo, "send_photo"),
    "panel": (Flow.awaiting_panel, "send_panel"),
    "refphoto": (Flow.awaiting_reference_photo, "send_ref_photo"),
    "manual": (Flow.awaiting_manual, "send_manual"),
}
# master-tools button -> machine action
MASTER_ACTIONS = {"baseline": "baseline", "ref_photo": "refphoto", "manual": "manual"}


@router.message(F.text.in_(MENU_ACTIONS.keys()))
async def on_menu(message: Message, state: FSMContext, api: FiboApi) -> None:
    info = await load_user(api, state, message.from_user.id)
    if info is None:
        await message.answer(t("ru", "not_registered"))
        return
    lang, action = info["user"]["language"], MENU_ACTIONS[message.text]
    await state.set_state(None)
    if not info["machines"] and action != "machines":
        await message.answer(t(lang, "no_machines"))
        return
    if action == "machines":
        titles = await _type_titles(api, info["workshop"]["profile"], lang)
        items = (
            "\n".join(
                f"• {html.escape(m['name'])} — {html.escape(titles.get(m['type'], m['type']))}"
                for m in info["machines"]
            )
            or "—"
        )
        markup = keyboards.master_tools(lang) if info["user"]["role"] in {"master", "owner"} else None
        await message.answer(t(lang, "machines_list", items=items), reply_markup=markup)
        return
    await message.answer(t(lang, "choose_machine"), reply_markup=keyboards.machines(info["machines"], action))


async def _type_titles(api: FiboApi, profile_id: str, lang: str) -> dict[str, str]:
    """Machine type code -> human title from the workshop profile's equipment catalog."""
    profile = next((p for p in await api.profiles() if p["id"] == profile_id), None)
    catalog = profile["equipment_catalog"] if profile else []
    return {i["type"]: (lang == "kk" and i.get("title_kk")) or i["title_ru"] for i in catalog}


@router.callback_query(F.data.startswith("m:"))
async def on_machine_chosen(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    await answer_callback(callback)  # at once: the button stops spinning even if the backend is slow
    _, action, machine_id = callback.data.split(":")
    info = await load_user(api, state, callback.from_user.id)
    lang = info["user"]["language"]
    machine = next((m for m in info["machines"] if m["id"] == int(machine_id)), None)
    if machine is None:
        await callback.message.answer(t(lang, "error"))
        return
    if action == "go":  # a message was waiting for the machine: send it now
        pending = (await state.get_data()).get("pending")
        await state.update_data(pending=None)  # a second tap on the same button sends nothing twice
        await edit_text(callback.message, t(lang, "machine_selected", machine=html.escape(machine["name"])))
        if pending:
            await submit(callback.message, state, api, callback.from_user.id, lang, machine, pending)
        return
    await state.update_data(machine_id=machine["id"], machine_name=machine["name"])
    if action == "sound":
        await state.set_state(Flow.awaiting_machine_sound)
        await edit_text(callback.message, t(lang, "send_sound", machine=html.escape(machine["name"])))
    elif action in PHOTO_ACTIONS:
        next_state, prompt = PHOTO_ACTIONS[action]
        await state.set_state(next_state)
        await edit_text(callback.message, t(lang, prompt, machine=html.escape(machine["name"])))
    else:
        await state.set_state(None)
        await edit_text(callback.message, t(lang, "send_voice", machine=html.escape(machine["name"])))


@router.callback_query(F.data.in_(MASTER_ACTIONS.keys()))
async def on_master_tool(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    """Masters: reference sound, reference photo or PDF manual -> first choose the machine."""
    info = await load_user(api, state, callback.from_user.id)
    lang = info["user"]["language"]
    if info["user"]["role"] not in {"master", "owner"}:
        await callback.answer(t(lang, "only_masters"), show_alert=True)
        return
    action = MASTER_ACTIONS[callback.data]
    await callback.message.answer(
        t(lang, "choose_machine"), reply_markup=keyboards.machines(info["machines"], action)
    )
    await callback.answer()


@router.callback_query(F.data == "add_machine")
async def on_add_machine(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    info = await load_user(api, state, callback.from_user.id)
    lang = info["user"]["language"]
    if info["user"]["role"] not in {"master", "owner"}:
        await callback.answer(t(lang, "only_masters"), show_alert=True)
        return
    profile = next(p for p in await api.profiles() if p["id"] == info["workshop"]["profile"])
    await state.set_state(AddMachine.machine_type)
    await callback.message.answer(
        t(lang, "choose_type"), reply_markup=keyboards.machine_types(profile["equipment_catalog"], lang)
    )
    await callback.answer()


@router.callback_query(AddMachine.machine_type, F.data.startswith("type:"))
async def on_machine_type(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    machine_type = callback.data.split(":", 1)[1]
    data = await state.get_data()
    profile = next(p for p in await api.profiles() if p["id"] == data["profile"])
    item = next(i for i in profile["equipment_catalog"] if i["type"] == machine_type)
    await state.update_data(new_type=machine_type, new_criticality=item["default_criticality"])
    await state.set_state(AddMachine.name)
    await callback.message.edit_text(t(await language(state), "ask_machine_name"))
    await callback.answer()


@router.message(AddMachine.name, F.text)
async def on_machine_name(message: Message, state: FSMContext, api: FiboApi) -> None:
    data = await state.get_data()
    name = message.text.strip()[:100]
    await api.create_machine(data["workshop_id"], name, data["new_type"], data["new_criticality"])
    await state.set_state(None)
    await message.answer(
        t(data.get("lang"), "machine_added", name=html.escape(name)),
        reply_markup=keyboards.main_menu(data.get("lang", "ru")),
    )
