"""OpenTelemetry traces. Export is optional and never blocks a request on startup."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span, Tracer

from soc_platform.config import Settings

logger = logging.getLogger(__name__)

_PROVIDER: TracerProvider | None = None


def setup_tracing(settings: Settings) -> TracerProvider:
    """Install one tracer provider per process. A second call keeps the first."""
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.service_name,
                "service.namespace": "asap",
                "deployment.environment": settings.environment,
            }
        )
    )
    endpoint = settings.otlp_endpoint.strip()
    if endpoint:
        _add_otlp_exporter(provider, endpoint)
    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    return provider


def shutdown_tracing() -> None:
    global _PROVIDER
    provider = _PROVIDER
    _PROVIDER = None
    if provider is None:
        return
    try:
        provider.shutdown()
    except Exception:
        logger.debug("trace provider shutdown failed", exc_info=True)


def get_tracer() -> Tracer:
    return trace.get_tracer("soc_platform")


def current_trace_id() -> str:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return ""
    return format(context.trace_id, "032x")


def current_span_id() -> str:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return ""
    return format(context.span_id, "016x")


@contextmanager
def span(name: str, **attributes: str) -> Iterator[Span | None]:
    """Start a span. Failures in the tracer still run the wrapped body."""
    try:
        context_manager = get_tracer().start_as_current_span(name)
    except Exception:
        logger.debug("span %s was not started", name, exc_info=True)
        yield None
        return
    with context_manager as current:
        for key, value in attributes.items():
            try:
                current.set_attribute(key, value)
            except Exception:
                logger.debug("span attribute %s was not set", key, exc_info=True)
        yield current


def _add_otlp_exporter(provider: TracerProvider, endpoint: str) -> None:
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        insecure = not endpoint.startswith("https://")
        target = endpoint.removeprefix("http://").removeprefix("https://")
        exporter = OTLPSpanExporter(endpoint=target, insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("otlp trace export enabled endpoint=%s", target)
    except Exception:
        logger.warning("otlp trace export was not enabled", exc_info=True)


_F = TypeVar("_F", bound=Callable[..., Any])


def traced(name: str) -> Callable[[_F], _F]:
    def decorator(func: _F) -> _F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(name):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def span_attributes(current: Span | None, **attributes: Any) -> None:
    if current is None or not current.is_recording():
        return
    for key, value in attributes.items():
        try:
            current.set_attribute(key, value)
        except Exception:
            logger.debug("span attribute %s was not set", key, exc_info=True)
