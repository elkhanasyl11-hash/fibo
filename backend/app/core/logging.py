"""Structured logging: every log line is one JSON object.

Why: during the demo and in Docker logs we want to grep by request_id or incident_id. Each line
carries the current request id, taken from a context variable that RequestIDMiddleware sets.

Usage: logger.info("incident processed", extra={"incident_id": 5, "duration_ms": 812})
Keys passed in `extra` are copied into the JSON object.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by app.core.middleware.RequestIDMiddleware for the duration of one HTTP request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes every LogRecord has. Anything else on the record came from `extra=` and is logged.
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Format a LogRecord as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str) -> None:
    """Send all logs (ours and libraries') to stderr as JSON lines."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
