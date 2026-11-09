"""Request/response schemas for the AI assistant chat."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    """Only user/assistant turns come from the client; system and tool messages are built server-side."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(BaseModel):
    workshop_id: int
    mode: Literal["live", "offline"] = "live"
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    language: Literal["ru", "kk"] = "ru"

    @model_validator(mode="after")
    def last_message_is_from_user(self) -> "AssistantRequest":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return self


class AssistantStatus(BaseModel):
    configured: bool
    model: str | None
    missing: list[str]


class AssistantResponse(BaseModel):
    source: Literal["ai", "builtin"] = "builtin"
    degraded: list[str] = Field(default_factory=list)
    answer: str
    referenced_machine_ids: list[int] = Field(
        description="Machines the answer is based on (for links in the UI)"
    )
    referenced_incident_ids: list[int]
    tools_used: list[str] = Field(description="Which data tools the assistant called, in order")
    is_demo: bool = Field(description="True = the workshop holds synthetic demo data")
