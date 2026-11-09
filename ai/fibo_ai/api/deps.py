from typing import Annotated

from fastapi import Header, HTTPException, status

from fibo_ai.facade import FiboAI
from fibo_ai.settings import get_settings

_AI_INSTANCE: FiboAI | None = None


def get_ai() -> FiboAI:
    global _AI_INSTANCE
    if _AI_INSTANCE is None:
        _AI_INSTANCE = FiboAI.from_env()
    return _AI_INSTANCE


def verify_auth_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    if settings.ai_service_token:
        expected = f"Bearer {settings.ai_service_token}"
        if authorization != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing service token",
            )
