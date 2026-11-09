"""Web accounts: sign-up creates the workshop and its owner in one transaction; sign-in checks the
password. Failed sign-ins are throttled per email in memory (one backend process is enough for the
MVP; with several processes this would move to Redis)."""

import asyncio
import time
from collections import defaultdict, deque

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthError, ConflictError, DomainValidationError, TooManyRequestsError
from app.core.passwords import hash_password, read_link_token, verify_password
from app.db.base import Role
from app.models.user import User
from app.models.workshop import Workshop
from app.schemas.auth import RegisterRequest
from app.services.workshops import generate_invite_code

MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW_S = 15 * 60
_failed: dict[str, deque[float]] = defaultdict(deque)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def bot_start_link(payload: str) -> str | None:
    if not settings.telegram_bot_username:
        return None
    return f"https://t.me/{settings.telegram_bot_username.lstrip('@')}?start={payload}"


async def link_telegram(session: AsyncSession, token: str, telegram_id: int) -> User:
    """Attach a Telegram account to the web user the link token was issued for (owners, masters).

    The token proves the web account, Telegram itself proves the Telegram id, so the same person holds
    both. One Telegram account = one Fibo user: a bot-only registration of it (operator/master, no
    email) is detached; another web account's Telegram is never taken (409)."""
    user_id = read_link_token(token)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise DomainValidationError("The link is invalid or expired", details={"reason": "link_expired"})
    other = await session.scalar(select(User).where(User.telegram_id == telegram_id, User.id != user.id))
    if other is not None and other.email is not None:  # another web account: never taken over
        raise ConflictError(
            "This Telegram account already belongs to another Fibo web account",
            details={"reason": "telegram_taken"},
        )
    if other is not None:  # a bot-only registration of the same person (they hold both): move it
        other.telegram_id = None
        await session.flush()
    user.telegram_id = telegram_id
    await session.commit()
    await session.refresh(user)
    return user


def telegram_link(invite_code: str) -> str | None:
    """https://t.me/<bot>?start=<code>: the bot then skips asking for the invite code."""
    if not settings.telegram_bot_username:
        return None
    return f"https://t.me/{settings.telegram_bot_username.lstrip('@')}?start={invite_code}"


async def _unique_invite_code(session: AsyncSession) -> str:
    for _ in range(5):
        code = generate_invite_code()
        if await session.scalar(select(Workshop.id).where(Workshop.invite_code == code)) is None:
            return code
    raise ConflictError("Could not generate a unique invite code, try again")


async def register(session: AsyncSession, payload: RegisterRequest) -> tuple[User, Workshop]:
    email = normalize_email(payload.email)
    if await session.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise ConflictError("This email is already registered", details={"field": "email"})
    workshop = Workshop(
        **payload.workshop.model_dump(),
        invite_code=await _unique_invite_code(session),
        survey=payload.survey.model_dump() if payload.survey else None,
    )
    session.add(workshop)
    await session.flush()
    user = User(
        full_name=payload.full_name,
        role=Role.OWNER,
        workshop_id=workshop.id,
        language=payload.language,
        email=email,
        password_hash=await asyncio.to_thread(hash_password, payload.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("This email is already registered", details={"field": "email"}) from exc
    await session.refresh(user)
    await session.refresh(workshop)
    return user, workshop


def _check_throttle(email: str, now: float) -> None:
    attempts = _failed[email]
    while attempts and now - attempts[0] > FAILED_LOGIN_WINDOW_S:
        attempts.popleft()
    if len(attempts) >= MAX_FAILED_LOGINS:
        raise TooManyRequestsError("Too many failed sign-ins, try again in 15 minutes")


async def login(session: AsyncSession, email: str, password: str) -> tuple[User, Workshop]:
    email = normalize_email(email)
    now = time.monotonic()
    _check_throttle(email, now)
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not await asyncio.to_thread(verify_password, password, user.password_hash):
        _failed[email].append(now)
        raise AuthError("Wrong email or password")
    _failed.pop(email, None)
    return user, await session.get(Workshop, user.workshop_id)
