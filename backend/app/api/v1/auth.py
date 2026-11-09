"""Web sign-up, sign-in and the current user. Tokens: app/core/passwords.py.

The dashboard data endpoints are still protected by the shared X-Fibo-Api-Key (the web server adds
it); the sign-in token tells the web app WHICH workshop it shows and guards the owner-only survey.
"""

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_dashboard_key
from app.core.config import settings
from app.core.errors import AuthError, ForbiddenError
from app.core.passwords import issue_link_token, issue_token, read_token
from app.models.user import User
from app.models.workshop import Workshop
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TelegramLinkResponse, WorkshopSurvey
from app.schemas.workshop import WorkshopRead
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["Web accounts"], dependencies=[Depends(require_dashboard_key)])


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    scheme, _, token = (authorization or "").partition(" ")
    user_id = read_token(token if scheme.lower() == "bearer" else request.cookies.get("fibo_session", ""))
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise AuthError("Sign in again")
    return user


def _response(user: User, workshop: Workshop) -> AuthResponse:
    return AuthResponse(
        token=issue_token(user.id),
        user=user,
        workshop=workshop,
        telegram_link=accounts.telegram_link(workshop.invite_code),
    )


def _set_cookie(response: Response, auth: AuthResponse) -> AuthResponse:
    response.set_cookie(
        "fibo_session",
        auth.token,
        httponly=True,
        secure=settings.env == "prod",
        samesite="lax",
        path="/api",
        max_age=settings.web_session_hours * 3600,
    )
    return auth


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie("fibo_session", path="/api")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, response: Response, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    """Create a workshop and its owner account, return a sign-in token."""
    user, workshop = await accounts.register(session, payload)
    return _set_cookie(response, _response(user, workshop))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    user, workshop = await accounts.login(session, payload.email, payload.password)
    return _set_cookie(response, _response(user, workshop))


@router.get("/me", response_model=AuthResponse)
async def me(
    response: Response, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    """Who is signed in; also refreshes the token."""
    return _set_cookie(response, _response(user, await session.get(Workshop, user.workshop_id)))


@router.post("/telegram-link", response_model=TelegramLinkResponse)
async def telegram_link(user: User = Depends(current_user)) -> TelegramLinkResponse:
    """A one-hour t.me link that attaches the signed-in user's Telegram to their account, so owners
    get alerts about critical incidents in the bot. Operators join with the invite code instead."""
    token, expires = issue_link_token(user.id)
    return TelegramLinkResponse(
        link=accounts.bot_start_link(token), expires_at=expires, linked=user.telegram_id is not None
    )


@router.put("/survey", response_model=WorkshopRead)
async def save_survey(
    payload: WorkshopSurvey, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Workshop:
    """Replace the onboarding answers of the signed-in owner's workshop."""
    if user.role != "owner":
        raise ForbiddenError("Only the workshop owner can change the survey")
    workshop = await session.get(Workshop, user.workshop_id)
    workshop.survey = payload.model_dump()
    await session.commit()
    await session.refresh(workshop)
    return workshop
