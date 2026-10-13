"""Read-only HTTP routes. There are no create, update, or delete operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from soc_platform.api.errors import InvalidFilter
from soc_platform.api.queries import (
    get_alert,
    get_case,
    get_event,
    get_evidence,
    get_finding,
    get_investigation,
    list_alerts,
    list_cases,
    list_events,
    list_evidence,
    list_findings,
    list_investigations,
)
from soc_platform.api.reader import ReadContext, reader_session
from soc_platform.api.schemas import (
    AlertList,
    AlertListQuery,
    AlertRead,
    CaseDetail,
    CaseList,
    CaseListQuery,
    ErrorResponse,
    EventDetail,
    EventList,
    EventListQuery,
    EvidenceDetail,
    EvidenceList,
    EvidenceListQuery,
    FindingDetail,
    FindingList,
    FindingListQuery,
    InvestigationDetail,
    InvestigationList,
    InvestigationListQuery,
)

router = APIRouter()

_LIST_ERRORS = {
    400: {"model": ErrorResponse, "description": "The cursor is invalid for this query."},
    404: {"model": ErrorResponse, "description": "The tenant is not visible."},
    422: {"model": ErrorResponse, "description": "The query parameters are not valid."},
    500: {"model": ErrorResponse, "description": "The request could not be completed."},
}
_DETAIL_ERRORS = {
    404: {"model": ErrorResponse, "description": "The tenant or resource is not visible in this tenant scope."},
    422: {"model": ErrorResponse, "description": "The query parameters are not valid."},
    500: {"model": ErrorResponse, "description": "The request could not be completed."},
}


def allow_query(model: type[BaseModel]):
    allowed = set(model.model_fields) | {"tenant"}

    def _check(request: Request) -> None:
        unknown = sorted(set(request.query_params) - allowed)
        if unknown:
            raise InvalidFilter(unknown)

    return _check


def _secret(request: Request) -> str:
    return request.app.state.settings.api_cursor_secret


def _scoped(ctx: ReadContext, tenant: UUID) -> ReadContext:
    if tenant != ctx.tenant_id:
        raise RuntimeError("tenant scope did not match the request")
    return ctx


@router.get(
    "/events",
    operation_id="list_events",
    tags=["Events"],
    summary="List canonical security events",
    description="Events are ordered by event_time descending. source, severity, event_type, and the time range filter that column.",
    response_model=EventList,
    responses=_LIST_ERRORS,
    dependencies=[Depends(allow_query(EventListQuery))],
)
def list_events_route(
    request: Request,
    query: Annotated[EventListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EventList:
    return list_events(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/events/{event_id}",
    operation_id="get_event",
    tags=["Events"],
    summary="Get one canonical security event",
    description="Returns the OCSF-aligned document projected from the immutable source record.",
    response_model=EventDetail,
    responses=_DETAIL_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_event_route(
    event_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request. Row-level security is set to this tenant.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EventDetail:
    return get_event(_scoped(ctx, tenant), event_id)


@router.get(
    "/alerts",
    operation_id="list_alerts",
    tags=["Alerts"],
    summary="List alerts",
    description="Alerts are ordered by detected_at descending. Filters: source, severity, alert_status, and that time range.",
    response_model=AlertList,
    responses=_LIST_ERRORS,
    dependencies=[Depends(allow_query(AlertListQuery))],
)
def list_alerts_route(
    request: Request,
    query: Annotated[AlertListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> AlertList:
    return list_alerts(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/alerts/{alert_id}",
    operation_id="get_alert",
    tags=["Alerts"],
    summary="Get one alert",
    response_model=AlertRead,
    responses=_DETAIL_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_alert_route(
    alert_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request. Row-level security is set to this tenant.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> AlertRead:
    return get_alert(_scoped(ctx, tenant), alert_id)


@router.get(
    "/findings",
    operation_id="list_findings",
    tags=["Findings"],
    summary="List findings",
    description="Findings are ordered by created_at descending. Filters: severity and that time range.",
    response_model=FindingList,
    responses=_LIST_ERRORS,
    dependencies=[Depends(allow_query(FindingListQuery))],
)
def list_findings_route(
    request: Request,
    query: Annotated[FindingListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> FindingList:
    return list_findings(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/findings/{finding_id}",
    operation_id="get_finding",
    tags=["Findings"],
    summary="Get one finding",
    response_model=FindingDetail,
    responses=_DETAIL_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_finding_route(
    finding_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request. Row-level security is set to this tenant.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> FindingDetail:
    return get_finding(_scoped(ctx, tenant), finding_id)


@router.get(
    "/cases",
    operation_id="list_cases",
    tags=["Cases"],
    summary="List cases",
    description="Cases are ordered by opened_at descending. Filters: severity, case_status, and that time range.",
    response_model=CaseList,
    responses=_LIST_ERRORS,
    dependencies=[Depends(allow_query(CaseListQuery))],
)
def list_cases_route(
    request: Request,
    query: Annotated[CaseListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> CaseList:
    return list_cases(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/cases/{case_id}",
    operation_id="get_case",
    tags=["Cases"],
    summary="Get one case",
    response_model=CaseDetail,
    responses=_DETAIL_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_case_route(
    case_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request. Row-level security is set to this tenant.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> CaseDetail:
    return get_case(_scoped(ctx, tenant), case_id)


@router.get(
    "/investigations",
    operation_id="list_investigations",
    tags=["Investigations"],
    summary="List investigations",
    description="Investigations are ordered by opened_at descending. Filters: investigation_status and that time range.",
    response_model=InvestigationList,
    responses=_LIST_ERRORS,
    dependencies=[Depends(allow_query(InvestigationListQuery))],
)
def list_investigations_route(
    request: Request,
    query: Annotated[InvestigationListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> InvestigationList:
    return list_investigations(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/investigations/{investigation_id}",
    operation_id="get_investigation",
    tags=["Investigations"],
    summary="Get one investigation",
    response_model=InvestigationDetail,
    responses=_DETAIL_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_investigation_route(
    investigation_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request. Row-level security is set to this tenant.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> InvestigationDetail:
    return get_investigation(_scoped(ctx, tenant), investigation_id)


@router.get(
    "/evidence",
    operation_id="list_evidence",
    tags=["Evidence"],
    summary="List evidence custody records",
    description="Evidence is ordered by collected_at descending. Filters: source and that time range. Raw payload bytes are not returned.",
    response_model=EvidenceList,
    responses=_LIST_ERRORS,
    dependencies=[Depends(allow_query(EvidenceListQuery))],
)
def list_evidence_route(
    request: Request,
    query: Annotated[EvidenceListQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EvidenceList:
    return list_evidence(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/evidence/{evidence_id}",
    operation_id="get_evidence",
    tags=["Evidence"],
    summary="Get one evidence custody record",
    description="Returns custody metadata and links. Raw payload bytes are not returned.",
    response_model=EvidenceDetail,
    responses=_DETAIL_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
def get_evidence_route(
    evidence_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request. Row-level security is set to this tenant.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EvidenceDetail:
    return get_evidence(_scoped(ctx, tenant), evidence_id)
