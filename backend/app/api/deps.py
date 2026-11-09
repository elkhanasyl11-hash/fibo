"""Common FastAPI dependencies: DB session, pagination, auth checks.

Routers import everything they need from here, so there is one obvious place to look.
"""

from fastapi import Query, Request

from app.core.security import require_bot_token, require_dashboard_key
from app.db.base import Profile
from app.db.session import get_session
from app.profiles.loader import ProfileConfig

__all__ = ["Pagination", "get_profiles", "get_session", "require_bot_token", "require_dashboard_key"]


def get_profiles(request: Request) -> dict[Profile, ProfileConfig]:
    """The industry profiles loaded at startup (app.state.profiles)."""
    return request.app.state.profiles


class Pagination:
    """`limit` / `offset` query parameters shared by every list endpoint.

    Use as `page: Pagination = Depends()`.
    """

    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200, description="Max items to return (1-200)"),
        offset: int = Query(0, ge=0, description="Items to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset
