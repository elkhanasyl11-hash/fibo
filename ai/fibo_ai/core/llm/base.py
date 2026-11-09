from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from fibo_ai.schemas.common import Usage

T = TypeVar("T", bound=BaseModel)


class LLMClient(ABC):
    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        schema: type[T],
        images: list[bytes] | None = None,
        temperature: float = 0.0,
        timeout_s: float = 15.0,
    ) -> tuple[T, Usage]:
        """Generate structured JSON response conforming to given schema."""
        pass
