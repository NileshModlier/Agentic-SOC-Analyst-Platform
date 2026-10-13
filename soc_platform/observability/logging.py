"""JSON logs for Loki. Existing loggers keep their handlers during tests."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from soc_platform.config import Settings
from soc_platform.observability.context import get_correlation_id
from soc_platform.observability.tracing import current_span_id, current_trace_id


class ContextFilter(logging.Filter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service  # type: ignore[attr-defined]
        record.correlation_id = get_correlation_id() or getattr(record, "correlation_id", "") or ""  # type: ignore[attr-defined]
        record.trace_id = current_trace_id() or getattr(record, "trace_id", "") or ""  # type: ignore[attr-defined]
        record.span_id = current_span_id() or getattr(record, "span_id", "") or ""  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", ""),
            "correlation_id": getattr(record, "correlation_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
            "span_id": getattr(record, "span_id", ""),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    _ensure_filter(root, settings.service_name)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        if settings.log_format.lower() == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    for handler in root.handlers:
        _ensure_filter(handler, settings.service_name)


def _ensure_filter(owner: logging.Logger | logging.Handler, service: str) -> None:
    current = [item for item in owner.filters if isinstance(item, ContextFilter)]
    if not current:
        owner.addFilter(ContextFilter(service))
    for item in current:
        item.service = service
