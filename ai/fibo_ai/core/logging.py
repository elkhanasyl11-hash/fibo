import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="system")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
