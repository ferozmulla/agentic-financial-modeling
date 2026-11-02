"""Structured JSON logging with Cloud Logging compatibility and PII/secret redaction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON compatible with Google Cloud Logging."""

    _SENSITIVE_KEYS = frozenset({"authorization", "token", "password", "secret", "cookie", "api_key"})

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "structured_data", None)
        if isinstance(extra_fields, dict):
            for key, value in extra_fields.items():
                if key.lower() in self._SENSITIVE_KEYS:
                    payload[key] = "[REDACTED]"
                else:
                    payload[key] = value
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Configure and return a structured JSON logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
