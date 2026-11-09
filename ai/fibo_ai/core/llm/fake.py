import hashlib
from typing import Any, TypeVar

from pydantic import BaseModel

from fibo_ai.core.llm.base import LLMClient
from fibo_ai.schemas.common import Usage

T = TypeVar("T", bound=BaseModel)


class FakeLLM(LLMClient):
    """Deterministic Fake LLM returning schema-valid fixtures."""

    def __init__(self, fixtures: dict[str, dict[str, Any]] | None = None) -> None:
        self.fixtures = fixtures or {}

    async def generate_json(
        self,
        prompt: str,
        schema: type[T],
        images: list[bytes] | None = None,
        temperature: float = 0.0,
        timeout_s: float = 15.0,
    ) -> tuple[T, Usage]:
        prompt_hash = hashlib.md5(prompt.encode("utf-8")).hexdigest()
        usage = Usage(
            llm_input_tokens=len(prompt.split()) * 2,
            llm_output_tokens=64,
            vision_calls=len(images) if images else 0,
            est_cost_usd=0.0001,
        )

        if prompt_hash in self.fixtures:
            instance = schema.model_validate(self.fixtures[prompt_hash])
            return instance, usage

        # Fallback to schema's json_schema_extra example if present
        extra = getattr(schema, "model_config", {}).get("json_schema_extra", {})
        if isinstance(extra, dict) and "example" in extra:
            return schema.model_validate(extra["example"]), usage

        # Fallback to constructing with defaults
        try:
            return schema.model_validate({}), usage
        except Exception:
            # Construct empty dummy instance using fields
            data: dict[str, Any] = {}
            for name, field in schema.model_fields.items():
                if field.is_required():
                    if field.annotation is str:
                        data[name] = "stub"
                    elif field.annotation is int:
                        data[name] = 0
                    elif field.annotation is float:
                        data[name] = 0.0
                    elif field.annotation is bool:
                        data[name] = False
                    elif getattr(field.annotation, "__origin__", None) is list:
                        data[name] = []
                    elif getattr(field.annotation, "__origin__", None) is dict:
                        data[name] = {}
                    else:
                        data[name] = None
            return schema.model_validate(data), usage
