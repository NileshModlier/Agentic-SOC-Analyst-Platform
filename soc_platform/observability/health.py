"""Liveness and readiness. These routes are not part of the security API contract."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

logger = logging.getLogger(__name__)


def health_router() -> APIRouter:
    router = APIRouter(include_in_schema=False)

    @router.get("/health", response_model=None)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready", response_model=None)
    def ready(request: Request) -> JSONResponse | dict[str, str]:
        postgres_ok = _postgres(getattr(request.app.state, "engine", None))
        redis_ok = _redis(getattr(request.app.state, "redis", None))
        body = {
            "status": "ok" if postgres_ok and redis_ok else "unavailable",
            "postgres": "ok" if postgres_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
        }
        if postgres_ok and redis_ok:
            return body
        return JSONResponse(status_code=503, content=body)

    @router.get("/metrics", response_model=None)
    def metrics(request: Request) -> Response:
        settings = getattr(request.app.state, "settings", None)
        if settings is not None and not settings.metrics_enabled:
            return Response(status_code=404)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router


def _postgres(engine: object) -> bool:
    if engine is None:
        return False
    try:
        with engine.connect() as connection:  # type: ignore[attr-defined]
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("postgres readiness failed error=%s", type(exc).__name__)
        return False


def _redis(client: object) -> bool:
    if client is None:
        return False
    try:
        return bool(client.ping())  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("redis readiness failed error=%s", type(exc).__name__)
        return False
