"""System: GET /profiles — the industry profiles with their equipment catalogs.

Profiles are loaded and validated once at startup (app.state.profiles). This endpoint is open
(no API key) because it holds no workshop data and both the bot and the dashboard need it.
"""

from fastapi import APIRouter, Request

from app.profiles.loader import ProfileConfig

router = APIRouter(prefix="/profiles", tags=["System"])


@router.get("", response_model=list[ProfileConfig], summary="List industry profiles")
async def list_profiles(request: Request) -> list[ProfileConfig]:
    return list(request.app.state.profiles.values())
