"""Investigation workflow routes. Canonical collections stay read-only."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from soc_platform.agents.drafts import decide_draft
from soc_platform.agents.network import NetworkDenied
from soc_platform.agents.present import present_draft, present_run
from soc_platform.agents.workflow import start_run
from soc_platform.api.agent_schemas import (
    DecisionCreate,
    DraftList,
    DraftListQuery,
    DraftRead,
    RunCreate,
    RunList,
    RunListQuery,
    RunRead,
)
from soc_platform.api.workspace_queries import list_drafts, list_runs
from soc_platform.api.agent_session import agent_session
from soc_platform.api.errors import ApiError
from soc_platform.api.reader import ReadContext, reader_session
from soc_platform.api.routes import allow_query
from soc_platform.api.schemas import ErrorResponse
from soc_platform.agents.context import RunContext

router = APIRouter(prefix="/agent")

_ERRORS = {
    404: {"model": ErrorResponse, "description": "The tenant or workspace record is not visible."},
    409: {"model": ErrorResponse, "description": "The draft cannot be decided in its current state."},
    422: {"model": ErrorResponse, "description": "The request is not valid."},
    500: {"model": ErrorResponse, "description": "The request could not be completed."},
}


@router.post(
    "/runs",
    operation_id="start_investigation_run",
    tags=["Agents"],
    status_code=201,
    summary="Start an investigation workflow",
    description=(
        "The supervisor routes a triage agent, an entity agent, a threat agent, and a reporting agent. "
        "Tools are local database reads. The workflow writes a cited draft and workspace memory. "
        "It does not change alerts, events, findings, cases, investigations, or evidence."
    ),
    response_model=RunRead,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def start_investigation_run(
    request: Request,
    body: RunCreate,
    context: Annotated[RunContext, Depends(agent_session)],
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request.")],
) -> RunRead:
    _same_tenant(context.tenant_id, tenant)
    try:
        run = start_run(
            context.session,
            tenant_id=context.tenant_id,
            requested_by=body.requested_by,
            alert_id=body.alert_id,
            question=body.question,
            cursor_secret=request.app.state.settings.api_cursor_secret,
        )
    except NetworkDenied as exc:
        raise ApiError(
            422,
            "network_denied",
            "Investigation workflows cannot fetch a URL.",
            [{"loc": ["question"], "message": str(exc)}],
        ) from exc
    return present_run(context.session, context.tenant_id, run.id)


@router.get(
    "/runs",
    operation_id="list_investigation_runs",
    tags=["Agents"],
    summary="List investigation runs",
    description="Newest workspace runs first. A draft summary is included when reporting stored one.",
    response_model=RunList,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(RunListQuery))],
)
def list_investigation_runs(
    request: Request,
    query: Annotated[RunListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> RunList:
    _same_tenant(ctx.tenant_id, query.tenant)
    return list_runs(ctx, query, request.app.state.settings.api_cursor_secret)


@router.get(
    "/runs/{run_id}",
    operation_id="get_investigation_run",
    tags=["Agents"],
    summary="Get an investigation run",
    description="Returns workspace memory and the draft. Canonical records are not included as truth beyond their citations.",
    response_model=RunRead,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_investigation_run(
    run_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> RunRead:
    _same_tenant(ctx.tenant_id, tenant)
    return present_run(ctx.session, ctx.tenant_id, run_id)


@router.get(
    "/drafts",
    operation_id="list_investigation_drafts",
    tags=["Agents"],
    summary="List investigation drafts",
    description="Newest drafts first. Approval is included when a person has decided the draft.",
    response_model=DraftList,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(DraftListQuery))],
)
def list_investigation_drafts(
    request: Request,
    query: Annotated[DraftListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> DraftList:
    _same_tenant(ctx.tenant_id, query.tenant)
    return list_drafts(ctx, query, request.app.state.settings.api_cursor_secret)


@router.get(
    "/drafts/{draft_id}",
    operation_id="get_investigation_draft",
    tags=["Agents"],
    summary="Get an investigation draft",
    response_model=DraftRead,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_investigation_draft(
    draft_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> DraftRead:
    _same_tenant(ctx.tenant_id, tenant)
    return present_draft(ctx.session, ctx.tenant_id, draft_id)


@router.post(
    "/drafts/{draft_id}/decisions",
    operation_id="decide_investigation_draft",
    tags=["Agents"],
    summary="Approve or reject a draft",
    description=(
        "A person decides a draft that is pending approval. Agent names are rejected. "
        "The decision updates the draft only."
    ),
    response_model=DraftRead,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def decide_investigation_draft(
    draft_id: UUID,
    body: DecisionCreate,
    context: Annotated[RunContext, Depends(agent_session)],
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request.")],
) -> DraftRead:
    _same_tenant(context.tenant_id, tenant)
    draft = decide_draft(
        context.session,
        tenant_id=context.tenant_id,
        draft_id=draft_id,
        decision=body.decision,
        actor=body.actor,
        note=body.note,
    )
    return present_draft(context.session, context.tenant_id, draft.id)


def _same_tenant(bound: UUID, requested: UUID) -> None:
    if bound != requested:
        raise RuntimeError("tenant scope did not match the request")
