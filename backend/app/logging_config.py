"""Structured (JSON-lines) logging.

Each log record is one JSON object, which makes logs easy to grep, ship to a log
aggregator, or load into pandas. Callers pass structured fields via `extra={"fields": {...}}`.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

# Anything that looks like an API key is masked before it reaches the log output.
_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|ghp_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,})")


def redact(value: str) -> str:
    return _SECRET_PATTERN.sub("[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update({k: redact(v) if isinstance(v, str) else v for k, v in fields.items()})
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
