"""Fibo Assistant: users. Two routers in one file because both manage the same table:
- /users      web users (dashboard key);
- /bot/...    registration and lookup for the Telegram bot (bot token only).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_session, require_bot_token, require_dashboard_key
from app.models.user import User
from app.schemas.auth import BotLink
from app.schemas.machine import MachineRead
from app.schemas.user import BotRegister, BotUserRead, UserCreate, UserRead, UserUpdate
from app.schemas.workshop import WorkshopRead
from app.services import accounts
from app.services import machines as machines_service
from app.services import users as users_service
from app.services import workshops as workshops_service

router = APIRouter(prefix="/users", tags=["Fibo Assistant"], dependencies=[Depends(require_dashboard_key)])
bot_router = APIRouter(prefix="/bot", tags=["Fibo Assistant"], dependencies=[Depends(require_bot_token)])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Create web user")
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)) -> User:
    return await users_service.create_user(session, payload)


@router.get("", response_model=list[UserRead], summary="List users of a workshop")
async def list_users(
    workshop_id: int, page: Pagination = Depends(), session: AsyncSession = Depends(get_session)
) -> list[User]:
    stmt = (
        select(User)
        .where(User.workshop_id == workshop_id)
        .order_by(User.id)
        .limit(page.limit)
        .offset(page.offset)
    )
    return list((await session.scalars(stmt)).all())


@router.get("/{user_id}", response_model=UserRead, summary="Get user")
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)) -> User:
    return await users_service.get_or_404(session, user_id)


@router.patch("/{user_id}", response_model=UserRead, summary="Update user")
async def update_user(
    user_id: int, payload: UserUpdate, session: AsyncSession = Depends(get_session)
) -> User:
    user = await users_service.get_or_404(session, user_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return user


@bot_router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Register bot user"
)
async def register(payload: BotRegister, session: AsyncSession = Depends(get_session)) -> User:
    """404 if the invite code is unknown, 409 if this Telegram account is already registered."""
    return await users_service.register_bot_user(session, payload)


@bot_router.post("/link", response_model=BotUserRead, summary="Attach Telegram to a web account")
async def link(payload: BotLink, session: AsyncSession = Depends(get_session)) -> BotUserRead:
    """From the bot after /start own…: 422 link expired/invalid, 409 Telegram used by another user."""
    user = await accounts.link_telegram(session, payload.token, payload.telegram_id)
    return await _bot_user(session, user)


@bot_router.get(
    "/users/{telegram_id}", response_model=BotUserRead, summary="Bot user with workshop and machines"
)
async def get_bot_user(telegram_id: int, session: AsyncSession = Depends(get_session)) -> BotUserRead:
    user = await users_service.get_by_telegram_id_or_404(session, telegram_id)
    return await _bot_user(session, user)


async def _bot_user(session: AsyncSession, user) -> BotUserRead:
    workshop = await workshops_service.get_or_404(session, user.workshop_id)
    machines = await machines_service.list_for_workshop(session, workshop.id)
    return BotUserRead(
        user=UserRead.model_validate(user),
        workshop=WorkshopRead.model_validate(workshop),
        machines=[MachineRead.model_validate(m) for m in machines],
    )
