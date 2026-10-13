"""Correlate every HTTP request and record API metrics outside the probe paths."""

from __future__ import annotations

import logging
import re
import time

from opentelemetry import trace
from opentelemetry.propagate import extract
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from soc_platform.observability.context import normalize_correlation_id, reset_correlation_id, set_correlation_id
from soc_platform.observability.metrics import record_api
from soc_platform.observability.tracing import current_span_id, current_trace_id, get_tracer, span_attributes

logger = logging.getLogger(__name__)

_UNMEASURED = {"/health", "/ready", "/metrics"}


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        correlation_id = normalize_correlation_id(
            _header(scope, "x-correlation-id") or _header(scope, "x-request-id")
        )
        token = set_correlation_id(correlation_id)
        started = time.perf_counter()
        status = 500
        captured = {"trace_id": "", "span_id": ""}

        def remember() -> None:
            captured["trace_id"] = current_trace_id() or captured["trace_id"]
            captured["span_id"] = current_span_id() or captured["span_id"]

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                span_attributes(trace.get_current_span(), **{"http.route": _route(scope)})
                remember()
                headers = MutableHeaders(scope=message)
                headers["X-Correlation-ID"] = correlation_id
                headers["X-Trace-Id"] = captured["trace_id"]
                headers["X-Span-Id"] = captured["span_id"]
            await send(message)

        try:
            with _request_span(scope, correlation_id):
                try:
                    await self.app(scope, receive, send_wrapper)
                finally:
                    remember()
        finally:
            duration = time.perf_counter() - started
            route = _route(scope)
            measured = path not in _UNMEASURED and not path.startswith("/metrics/")
            if measured:
                record_api(str(scope.get("method", "GET")), route, status, duration)
            _access_log(measured, str(scope.get("method", "GET")), route, status, duration, correlation_id, captured)
            reset_correlation_id(token)


def _request_span(scope: Scope, correlation_id: str):
    method = str(scope.get("method", ""))
    try:
        current = trace.get_current_span()
        if current.get_span_context().is_valid:
            span_attributes(current, correlation_id=correlation_id, **{"http.method": method})
            return _existing_span(current)
        return get_tracer().start_as_current_span(
            "http.request",
            context=extract(_carrier(scope)),
            attributes={"correlation_id": correlation_id, "http.method": method},
        )
    except Exception:
        logger.debug("request span was not started", exc_info=True)
        return _existing_span(None)


class _existing_span:
    def __init__(self, current) -> None:
        self._current = current

    def __enter__(self):
        return self._current

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


def _carrier(scope: Scope) -> dict[str, str]:
    carrier: dict[str, str] = {}
    for key, value in scope.get("headers", []):
        carrier[key.decode("latin-1")] = value.decode("latin-1")
    return carrier


def _header(scope: Scope, name: str) -> str | None:
    target = name.encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == target:
            return value.decode("latin-1")
    return None


def _route(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not isinstance(path, str) or not path:
        return "unmatched"
    request_path = scope.get("path")
    if not isinstance(request_path, str):
        return path
    pattern = "".join(
        "[^/]+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in re.split(r"(\{[^/}]+\})", path)
    )
    matched = re.search(pattern + "$", request_path)
    if matched is None:
        return path
    return request_path[: matched.start()] + path


def _access_log(
    measured: bool,
    method: str,
    route: str,
    status: int,
    duration: float,
    correlation_id: str,
    captured: dict[str, str],
) -> None:
    logger.log(
        logging.INFO if measured else logging.DEBUG,
        "request method=%s route=%s status=%s duration_ms=%.1f",
        method,
        route,
        status,
        duration * 1000,
        extra={
            "correlation_id": correlation_id,
            "trace_id": captured["trace_id"],
            "span_id": captured["span_id"],
        },
    )
