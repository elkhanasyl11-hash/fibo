"""Users: web users and Telegram bot registration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.base import Role
from app.models.user import User
from app.schemas.user import BotRegister, UserCreate
from app.services import workshops as workshops_service


async def get_or_404(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found", details={"user_id": user_id})
    return user


async def get_by_telegram_id_or_404(session: AsyncSession, telegram_id: int) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise NotFoundError("Telegram user is not registered", details={"telegram_id": telegram_id})
    return user


async def _ensure_telegram_id_free(session: AsyncSession, telegram_id: int | None) -> None:
    if telegram_id is None:
        return
    existing = await session.scalar(select(User.id).where(User.telegram_id == telegram_id))
    if existing is not None:
        raise ConflictError("Telegram user is already registered", details={"telegram_id": telegram_id})


async def create_user(session: AsyncSession, payload: UserCreate) -> User:
    await workshops_service.get_or_404(session, payload.workshop_id)
    await _ensure_telegram_id_free(session, payload.telegram_id)
    user = User(**payload.model_dump())
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def register_bot_user(session: AsyncSession, payload: BotRegister) -> User:
    """Join a workshop by invite code. A Telegram account can belong to one workshop only."""
    workshop = await workshops_service.get_by_invite_code_or_404(session, payload.invite_code)
    await _ensure_telegram_id_free(session, payload.telegram_id)
    user = User(
        telegram_id=payload.telegram_id,
        full_name=payload.full_name,
        role=Role(payload.role),
        workshop_id=workshop.id,
        language=payload.language,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def list_masters(session: AsyncSession, workshop_id: int) -> list[User]:
    """Mechanics of a workshop (used later by "Call mechanic")."""
    stmt = select(User).where(User.workshop_id == workshop_id, User.role == Role.MASTER).order_by(User.id)
    return list((await session.scalars(stmt)).all())
