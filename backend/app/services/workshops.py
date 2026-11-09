"""Workshops: creation with a unique invite code, lookups."""

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models.workshop import Workshop
from app.schemas.workshop import WorkshopCreate

# No 0/O and 1/I/L, so a code read aloud or typed from a printout is not misread.
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 6


def generate_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


def normalize_invite_code(code: str) -> str:
    """Users type codes in any case and with stray spaces."""
    return code.strip().upper()


async def get_or_404(session: AsyncSession, workshop_id: int) -> Workshop:
    workshop = await session.get(Workshop, workshop_id)
    if workshop is None:
        raise NotFoundError(f"Workshop {workshop_id} not found", details={"workshop_id": workshop_id})
    return workshop


async def get_by_invite_code_or_404(session: AsyncSession, code: str) -> Workshop:
    stmt = select(Workshop).where(Workshop.invite_code == normalize_invite_code(code))
    workshop = await session.scalar(stmt)
    if workshop is None:
        raise NotFoundError("Invite code not found", details={"invite_code": code})
    return workshop


async def create_workshop(session: AsyncSession, payload: WorkshopCreate) -> Workshop:
    """Create a workshop with a fresh invite code (retry on the rare collision)."""
    for _ in range(5):
        code = generate_invite_code()
        taken = await session.scalar(select(Workshop.id).where(Workshop.invite_code == code))
        if taken is None:
            workshop = Workshop(**payload.model_dump(), invite_code=code)
            session.add(workshop)
            await session.commit()
            await session.refresh(workshop)
            return workshop
    raise ConflictError("Could not generate a unique invite code, try again")
