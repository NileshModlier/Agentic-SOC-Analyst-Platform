"""Read-only intake operations. Replay stays on the operator CLI."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from soc_platform.api.operations import connector_health, list_dead_letters, list_publications
from soc_platform.api.operations_schemas import (
    ConnectorHealthList,
    DeadLetterList,
    DeadLetterQuery,
    PublicationList,
    PublicationQuery,
)
from soc_platform.api.reader import ReadContext, reader_session
from soc_platform.api.routes import allow_query
from soc_platform.api.schemas import ErrorResponse

router = APIRouter(prefix="/operations")

_ERRORS = {
    400: {"model": ErrorResponse, "description": "The cursor is invalid for this query."},
    404: {"model": ErrorResponse, "description": "The tenant is not visible."},
    422: {"model": ErrorResponse, "description": "The query parameters are not valid."},
    500: {"model": ErrorResponse, "description": "The request could not be completed."},
}


def _same(ctx: ReadContext, tenant: UUID) -> ReadContext:
    if tenant != ctx.tenant_id:
        raise RuntimeError("tenant scope did not match the request")
    return ctx


@router.get(
    "/connectors",
    operation_id="list_connector_health",
    tags=["Operations"],
    summary="Connector intake health",
    description="Counts projected and dead-lettered receipts for each intake source. Raw payloads are not returned.",
    response_model=ConnectorHealthList,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def list_connector_health(
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> ConnectorHealthList:
    return connector_health(_same(ctx, tenant))


@router.get(
    "/dead-letters",
    operation_id="list_dead_letters",
    tags=["Operations"],
    summary="List dead letters",
    description="Failure metadata for parse, publish, and replay. Payload bytes are not returned.",
    response_model=DeadLetterList,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(DeadLetterQuery))],
)
def list_dead_letters_route(
    request: Request,
    query: Annotated[DeadLetterQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> DeadLetterList:
    return list_dead_letters(_same(ctx, query.tenant), query, request.app.state.settings.api_cursor_secret)


@router.get(
    "/publications",
    operation_id="list_publications",
    tags=["Operations"],
    summary="List publication records",
    description="Outbox delivery status. Event payloads are not returned.",
    response_model=PublicationList,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(PublicationQuery))],
)
def list_publications_route(
    request: Request,
    query: Annotated[PublicationQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> PublicationList:
    return list_publications(_same(ctx, query.tenant), query, request.app.state.settings.api_cursor_secret)
