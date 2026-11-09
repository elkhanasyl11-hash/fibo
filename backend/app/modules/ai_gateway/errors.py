"""What an AI service error means for the backend (integration contract section 4.3).

classify(error) -> one of
  unavailable  transport failure, 5xx, LLM_UNAVAILABLE (after the client's retries) -> builtin fallback
  input        the operator's input cannot be analysed (blurry photo, silent/short audio, ASR failed,
               no baseline) -> an explanatory card, no fallback (the builtin module would fail the same way)
  recoverable  BASELINE_VERSION_MISMATCH -> rebuild the baseline once and retry, else fallback
  soft         MANUAL_NOT_INDEXED -> builtin fallback, the card says the manual is not available
  bug          anything else, e.g. MACHINE_AMBIGUOUS (the backend always sends machine_id) -> log + fallback
fails_incident(error): VALIDATION_ERROR / UNSUPPORTED_MEDIA / FILE_TOO_LARGE are rejected requests: the
incident is marked FAILED with error_message "ai: <code>" instead of silently answering something else.
ContractError: the AI answered 2xx but not in the expected shape (adapters.py) -> treated as a bug.
"""

from typing import Literal

from app.modules.ai_gateway.client import FiboAIError

Kind = Literal["unavailable", "input", "recoverable", "soft", "bug"]

UNAVAILABLE_CODES = {"UNREACHABLE", "LLM_UNAVAILABLE"}
INPUT_CODES = {
    "PHOTO_QUALITY_LOW",
    "ASR_LOW_CONFIDENCE",
    "AUDIO_TOO_SHORT",
    "AUDIO_SILENT",
    "BASELINE_MISSING",
}
FAIL_CODES = {"VALIDATION_ERROR", "UNSUPPORTED_MEDIA", "FILE_TOO_LARGE"}


class ContractError(Exception):
    """The AI service answered successfully but not in the shape the backend expects."""


class AIRequestRejected(Exception):
    """The AI service rejected the request itself (400/413/415): the incident is marked FAILED."""

    def __init__(self, error: FiboAIError) -> None:
        super().__init__(f"ai: {error.code}")
        self.error = error


def classify(error: FiboAIError) -> Kind:
    if error.code in UNAVAILABLE_CODES or error.status == 0 or error.status >= 500:
        return "unavailable"
    if error.code in INPUT_CODES:
        return "input"
    if error.code == "BASELINE_VERSION_MISMATCH":
        return "recoverable"
    if error.code == "MANUAL_NOT_INDEXED":
        return "soft"
    return "bug"


def fails_incident(error: FiboAIError) -> bool:
    return error.code in FAIL_CODES
