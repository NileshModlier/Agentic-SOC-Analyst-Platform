"""Stable error envelope for the read API."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class InvalidCursor(ApiError):
    def __init__(self) -> None:
        super().__init__(400, "invalid_cursor", "Cursor is invalid for this query.")


class InvalidFilter(ApiError):
    def __init__(self, names: list[str]) -> None:
        joined = ", ".join(names)
        super().__init__(422, "invalid_filter", f"Unknown query parameter: {joined}.")


class TenantNotFound(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "tenant_not_found", "Tenant was not found.")


class ResourceNotFound(ApiError):
    def __init__(self, resource: str) -> None:
        super().__init__(404, "not_found", f"{resource} was not found.")


class Conflict(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(409, "conflict", message)


def _body(code: str, message: str, details: list[dict] | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for item in exc.errors():
            loc = [str(part) for part in item.get("loc", ()) if part not in {"query", "path", "body"}]
            details.append({"loc": loc, "message": str(item.get("msg", "Invalid value."))})
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Request parameters are invalid.", details),
        )

    @app.exception_handler(HTTPException)
    async def handle_http(_request, exc: HTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(codes.get(exc.status_code, "http_error"), message),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request, exc: Exception) -> JSONResponse:
        logger.exception("read API request failed")
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "The request could not be completed."),
        )
