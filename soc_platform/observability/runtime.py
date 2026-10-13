"""Process wiring for the API, the outbox relay, and the intake command."""

from __future__ import annotations

import logging
import os

from prometheus_client import REGISTRY
from prometheus_client.registry import Collector
from sqlalchemy.engine import Engine

from soc_platform.config import Settings
from soc_platform.observability.database import install_sql_metrics, instrument_sqlalchemy
from soc_platform.observability.health import health_router
from soc_platform.observability.inventory import InventoryCollector, PoolCollector
from soc_platform.observability.logging import setup_logging
from soc_platform.observability.middleware import ObservabilityMiddleware
from soc_platform.observability.redis import instrument_redis_client
from soc_platform.observability.tracing import setup_tracing, shutdown_tracing

logger = logging.getLogger(__name__)

_ACTIVE: list[Collector] = []


def configure_observability(settings: Settings) -> None:
    setup_logging(settings)
    setup_tracing(settings)
    install_sql_metrics()


def service_settings(settings: Settings, service_name: str) -> Settings:
    if "SOC_SERVICE_NAME" in os.environ:
        return settings
    return settings.model_copy(update={"service_name": service_name})


def register_api_collectors(engine: Engine, redis_client: object) -> list[Collector]:
    unregister_api_collectors(list(_ACTIVE))
    collectors: list[Collector] = [InventoryCollector(engine, redis_client), PoolCollector(engine)]
    for collector in collectors:
        REGISTRY.register(collector)
    _ACTIVE[:] = collectors
    return collectors


def unregister_api_collectors(collectors: list[Collector]) -> None:
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            logger.debug("collector unregister failed", exc_info=True)
        if collector in _ACTIVE:
            _ACTIVE.remove(collector)


def install_http_observability(app: object) -> None:
    app.add_middleware(ObservabilityMiddleware)  # type: ignore[attr-defined]
    app.include_router(health_router())  # type: ignore[attr-defined]
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,  # type: ignore[arg-type]
            excluded_urls=r"/health,/ready,/metrics,/docs,/redoc,/openapi\.json",
        )
    except Exception:
        logger.warning("fastapi tracing was not attached", exc_info=True)


def start_relay_metrics(settings: Settings) -> None:
    if not settings.metrics_enabled:
        return
    from prometheus_client import start_http_server

    try:
        start_http_server(settings.metrics_port, addr="0.0.0.0")
    except OSError:
        logger.warning("metrics server was not started port=%s", settings.metrics_port)


__all__ = [
    "configure_observability",
    "install_http_observability",
    "instrument_redis_client",
    "instrument_sqlalchemy",
    "register_api_collectors",
    "service_settings",
    "shutdown_tracing",
    "start_relay_metrics",
    "unregister_api_collectors",
]
