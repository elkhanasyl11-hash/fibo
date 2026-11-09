"""Voice messages: a problem description (mode=auto) or, after "🔊 Записать звук станка",
a machine-sound recording (mode=machine_sound). Reference recordings go to the baseline instead.
Sending goes through submit.py: no machine chosen yet -> the recording waits for the machine tap."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards
from bot.api_client import FiboApi, FiboApiError
from bot.handlers.common import load_user
from bot.states import Flow
from bot.submit import ask_machine, pick_machine, submit
from bot.texts import t

router = Router(name="voice")


@router.message(F.voice | F.audio)
async def on_voice(message: Message, state: FSMContext, api: FiboApi) -> None:
    """Operator sent a voice message: upload it and wait for the incident card."""
    info = await load_user(api, state, message.from_user.id)
    if info is None:
        await message.answer(t("ru", "not_registered"))
        return
    lang = info["user"]["language"]
    if not info["machines"]:
        await message.answer(t(lang, "no_machines"))
        return
    data, current = await state.get_data(), await state.get_state()
    media = message.voice or message.audio
    filename = "voice.ogg" if message.voice else (message.audio.file_name or "audio.mp3")
    content_type = media.mime_type or "audio/ogg"
    if current == Flow.awaiting_baseline.state and data.get("machine_id"):
        downloaded = (await message.bot.download(media)).read()
        await _save_baseline(
            message, state, api, lang, data["machine_id"], downloaded, filename, content_type
        )
        return
    item = {
        "kind": "voice",
        "file_id": media.file_id,
        "filename": filename,
        "content_type": content_type,
        "mode": "machine_sound" if current == Flow.awaiting_machine_sound.state else "auto",
    }
    machine = pick_machine(data, info["machines"])
    if machine is None:
        await ask_machine(message, state, info, lang, item)
        return
    await submit(message, state, api, message.from_user.id, lang, machine, item)


async def _save_baseline(
    message: Message,
    state: FSMContext,
    api: FiboApi,
    lang: str,
    machine_id: int,
    data: bytes,
    filename: str,
    content_type: str,
) -> None:
    """Master is recording reference sounds: stay in this mode until the baseline is ready."""
    try:
        result = await api.upload_audio_baseline(machine_id, data, filename, content_type)
    except FiboApiError as exc:
        if exc.status != 422:
            raise
        await message.answer(t(lang, "baseline_too_short"))
        return
    text = t(lang, "baseline_saved", count=result["recordings"], recommended=result["recommended"])
    if result["ready"]:
        await state.set_state(None)
        await message.answer(f"{text}\n{t(lang, 'baseline_ready')}", reply_markup=keyboards.main_menu(lang))
    else:
        await message.answer(f"{text}\n{t(lang, 'baseline_more')}")
