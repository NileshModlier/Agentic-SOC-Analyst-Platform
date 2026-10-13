"""Read-only search routes. There are no create, update, or delete operations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from soc_platform.api.reader import ReadContext, reader_session
from soc_platform.api.routes import _scoped, _secret, allow_query
from soc_platform.api.schemas import ErrorResponse
from soc_platform.api.search_queries import get_entity, search_alerts, search_entities, search_events, search_facets
from soc_platform.api.search_schemas import (
    AlertSearchPage,
    AlertSearchQuery,
    EntitySearchHit,
    EntitySearchPage,
    EntitySearchQuery,
    EventSearchPage,
    EventSearchQuery,
    FacetQuery,
    SearchFacets,
)
from soc_platform.observability.hooks import observe_search

router = APIRouter(prefix="/search")

_ERRORS = {
    400: {"model": ErrorResponse, "description": "The cursor is invalid for this query."},
    404: {"model": ErrorResponse, "description": "The tenant is not visible."},
    422: {"model": ErrorResponse, "description": "The query parameters are not valid."},
    500: {"model": ErrorResponse, "description": "The request could not be completed."},
}
_FACET_ERRORS = {
    404: {"model": ErrorResponse, "description": "The tenant is not visible."},
    422: {"model": ErrorResponse, "description": "The query parameters are not valid."},
    500: {"model": ErrorResponse, "description": "The request could not be completed."},
}


@router.get(
    "/events",
    operation_id="search_events",
    tags=["Search"],
    summary="Search canonical security events",
    description=(
        "PostgreSQL full-text search over user, host, IP address, process, file, "
        "event description, and Sigma rule id. Filters are severity, source, status, "
        "event type, and an inclusive-start exclusive-end event time range. "
        "The default sort is event time, newest first. The default page size is 50 and the maximum is 100."
    ),
    response_model=EventSearchPage,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(EventSearchQuery))],
)
@observe_search("events")
def search_events_route(
    request: Request,
    query: Annotated[EventSearchQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EventSearchPage:
    return search_events(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/alerts",
    operation_id="search_alerts",
    tags=["Search"],
    summary="Search alerts",
    description=(
        "PostgreSQL full-text search over alert title, Sigma or detection rule, description, "
        "and the linked event text. event_time sorts by detection time. "
        "Status is the alert workflow status."
    ),
    response_model=AlertSearchPage,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(AlertSearchQuery))],
)
@observe_search("alerts")
def search_alerts_route(
    request: Request,
    query: Annotated[AlertSearchQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> AlertSearchPage:
    return search_alerts(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/entities",
    operation_id="search_entities",
    tags=["Search"],
    summary="Search users, hosts, processes, files, and IP addresses",
    description=(
        "One result model for every catalog entity. The query matches the entity value. "
        "Event filters keep entities that are linked to a matching event. "
        "event_time sorts by last seen and created_time sorts by first seen."
    ),
    response_model=EntitySearchPage,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(EntitySearchQuery))],
)
@observe_search("entities")
def search_entities_route(
    request: Request,
    query: Annotated[EntitySearchQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EntitySearchPage:
    return search_entities(_scoped(ctx, query.tenant), query, _secret(request))


@router.get(
    "/entities/{entity_id}",
    operation_id="get_entity",
    tags=["Search"],
    summary="Get one catalog entity",
    description="Returns the user, host, process, file, or IP catalog row. Related events are a separate search.",
    response_model=EntitySearchHit,
    responses=_ERRORS,
    dependencies=[Depends(allow_query(BaseModel))],
)
@observe_search("entity")
def get_entity_route(
    entity_id: UUID,
    tenant: Annotated[UUID, Query(description="Tenant scope. Required on every request.")],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> EntitySearchHit:
    return get_entity(_scoped(ctx, tenant), entity_id)


@router.get(
    "/facets",
    operation_id="search_facets",
    tags=["Search"],
    summary="Facet the event search corpus",
    description=(
        "Counts for event type, severity, source, host, and user. "
        "The query and filters match event search, except each facet omits its own filter. "
        "Host and user return the twenty largest buckets. Facets are not paginated."
    ),
    response_model=SearchFacets,
    responses=_FACET_ERRORS,
    dependencies=[Depends(allow_query(FacetQuery))],
)
@observe_search("facets")
def search_facets_route(
    query: Annotated[FacetQuery, Query()],
    ctx: Annotated[ReadContext, Depends(reader_session)],
) -> SearchFacets:
    return search_facets(_scoped(ctx, query.tenant), query)
