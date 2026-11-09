"""Photos: tool/part photo -> incident card; controller display -> values to CONFIRM; reference photo.

Panel flow (values are never saved without a person confirming them):
  photo -> POST /readings/panel-photo (backend only suggests) -> list with ✅ Confirm / ✏️ Edit
  ✏️ -> the user sends "field=number" lines -> list again -> ✅ -> POST /readings (source=panel)
Which flow a photo belongs to is decided by the state set when the machine was chosen; a photo
without such a state is treated as a tool/part photo and sent through submit.py (asks the machine
if none is known and keeps the photo meanwhile).
"""

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.api_client import FiboApi, FiboApiError
from bot.handlers.common import load_user
from bot.states import Flow
from bot.submit import ask_machine, pick_machine, submit
from bot.texts import FIELD_TITLES, reason_text, t

router = Router(name="photo")


def format_values(values: dict[str, float]) -> str:
    return "\n".join(f"• {html.escape(FIELD_TITLES.get(k, k))}: {v:g}" for k, v in values.items())


def parse_corrections(text: str, values: dict[str, float]) -> tuple[dict[str, float], str | None]:
    """Apply "field=number" lines. Returns (new values, first bad line or None)."""
    updated = dict(values)
    for line in filter(None, (raw.strip() for raw in text.splitlines())):
        name, sep, number = line.partition("=")
        try:
            if not sep:
                raise ValueError
            updated[name.strip()] = float(number.strip().replace(",", "."))
        except ValueError:
            return values, line
    return updated, None


def _rejected_line(item: dict, lang: str) -> str:
    field = FIELD_TITLES.get(item["field"], item["field"])
    return f"• {html.escape(field)}: {html.escape(reason_text(item['reason'], lang))}"


async def _download_photo(message: Message) -> bytes:
    largest = message.photo[-1]  # Telegram sends several sizes; the last one is the biggest
    return (await message.bot.download(largest)).read()


async def _show_panel_values(message: Message, lang: str, values: dict[str, float]) -> None:
    await message.answer(
        t(lang, "panel_values", values=format_values(values)), reply_markup=keyboards.panel_confirm(lang)
    )


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext, api: FiboApi) -> None:
    info = await load_user(api, state, message.from_user.id)
    if info is None:
        await message.answer(t("ru", "not_registered"))
        return
    data, lang = await state.get_data(), info["user"]["language"]
    if not info["machines"]:
        await message.answer(t(lang, "no_machines"))
        return
    current = await state.get_state()
    machine_id = data.get("machine_id")
    special = current in {Flow.awaiting_reference_photo.state, Flow.awaiting_panel.state}
    if not special or machine_id is None:  # a tool/part photo -> incident card
        item = {"kind": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption}
        machine = pick_machine(data, info["machines"])
        if machine is None:
            await ask_machine(message, state, info, lang, item)
            return
        await submit(message, state, api, message.from_user.id, lang, machine, item)
        return
    photo = await _download_photo(message)

    if current == Flow.awaiting_reference_photo.state:
        await api.upload_photo_baseline(machine_id, photo)
        await state.set_state(None)
        await message.answer(t(lang, "ref_photo_saved"), reply_markup=keyboards.main_menu(lang))
        return

    if current == Flow.awaiting_panel.state:
        try:
            result = await api.read_panel(machine_id, photo)
        except FiboApiError as exc:
            if exc.status != 422:
                raise
            await message.answer(t(lang, "panel_retake", reasons=html.escape(exc.message)))
            return
        values = {item["field"]: item["value"] for item in result["values"]}
        if result["rejected"]:
            rejected = "\n".join(_rejected_line(r, lang) for r in result["rejected"])
            await message.answer(t(lang, "panel_rejected", values=rejected))
        if not values:
            await message.answer(t(lang, "panel_nothing"))
            return
        await state.update_data(panel_values=values, panel_extra=result["extra_fields"])
        await _show_panel_values(message, lang, values)
        return


@router.callback_query(F.data == "panel_ok")
async def on_panel_confirm(callback: CallbackQuery, state: FSMContext, api: FiboApi) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    values = data.get("panel_values")
    if not values:
        await callback.answer(t(lang, "error"), show_alert=True)
        return
    try:
        await api.create_reading(data["machine_id"], values, data.get("panel_extra", []), data.get("user_id"))
    except FiboApiError as exc:
        if exc.status != 422:
            raise
        await callback.message.answer(t(lang, "panel_edit_bad", line=html.escape(exc.message)))
        await callback.answer()
        return
    await state.update_data(panel_values=None)
    await state.set_state(None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(t(lang, "panel_saved"), reply_markup=keyboards.main_menu(lang))
    await callback.answer()


@router.callback_query(F.data == "panel_edit")
async def on_panel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Flow.awaiting_panel_edit)
    await callback.message.answer(t((await state.get_data()).get("lang"), "panel_edit_help"))
    await callback.answer()


@router.message(Flow.awaiting_panel_edit, F.text)
async def on_panel_corrections(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    values, bad_line = parse_corrections(message.text, data.get("panel_values") or {})
    if bad_line is not None:
        await message.answer(t(lang, "panel_edit_bad", line=html.escape(bad_line)))
        return
    await state.update_data(panel_values=values)
    await state.set_state(Flow.awaiting_panel)
    await _show_panel_values(message, lang, values)
