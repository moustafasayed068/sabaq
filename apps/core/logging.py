"""Structured JSON logs with the request id.

Rule (docs/architecture.md): never log phone numbers, health answers, tokens or card data.
Only the fields listed in SAFE_EXTRA are copied from `extra=`, so a stray value is dropped.
"""

import json
import logging
from datetime import UTC, datetime

from apps.core.request_context import get_request_id

SAFE_EXTRA = frozenset(
    {"event", "status_code", "method", "path", "duration_ms", "task", "user_id", "count"}
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "") or get_request_id(),
        }
        for key in SAFE_EXTRA:
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
