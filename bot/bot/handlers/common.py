"""Helpers shared by handlers: who is this Telegram user (from FSM cache or the backend)."""

from aiogram.fsm.context import FSMContext

from bot.api_client import FiboApi


async def load_user(api: FiboApi, state: FSMContext, telegram_id: int) -> dict | None:
    """{user, workshop, machines} from the backend; caches language and role in FSM data."""
    info = await api.get_user(telegram_id)
    if info is not None:
        await state.update_data(
            lang=info["user"]["language"],
            role=info["user"]["role"],
            user_id=info["user"]["id"],
            workshop_id=info["workshop"]["id"],
            profile=info["workshop"]["profile"],
        )
    return info


async def language(state: FSMContext) -> str:
    return (await state.get_data()).get("lang", "ru")
