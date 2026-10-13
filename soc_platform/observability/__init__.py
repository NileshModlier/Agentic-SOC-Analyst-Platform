"""Metrics, logs, traces, and health for the Agentic SOC Analyst Platform."""

from soc_platform.observability.runtime import (
    configure_observability,
    install_http_observability,
    instrument_redis_client,
    instrument_sqlalchemy,
    register_api_collectors,
    service_settings,
    shutdown_tracing,
    start_relay_metrics,
    unregister_api_collectors,
)

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
