"""Tenant-scoped PostgreSQL full-text search. Redis is not a search index."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, Text, and_, cast, exists, false, func, literal, or_, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.orm import Session

from soc_platform.api.errors import InvalidCursor, ResourceNotFound
from soc_platform.api.pagination import KeyCursor, decode_key_cursor, encode_key_cursor, filter_payload
from soc_platform.api.reader import ReadContext, assert_reader
from soc_platform.api.schemas import PageInfo
from soc_platform.api.search_schemas import (
    AlertSearchHit,
    AlertSearchPage,
    AlertSearchQuery,
    EntitySearchHit,
    EntitySearchPage,
    EntitySearchQuery,
    EventSearchHit,
    EventSearchPage,
    EventSearchQuery,
    FacetBucket,
    FacetQuery,
    SearchFacets,
)
from soc_platform.domain.enums import SearchSort
from soc_platform.models.search import AlertSearchDocument, EventEntity, EventSearchDocument, SecurityEntity
from soc_platform.search.text import prepare_fts_query

_EVENTS = "search_events"
_ALERTS = "search_alerts"
_ENTITIES = "search_entities"
_HEADLINE = "StartSel=,StopSel=,MaxWords=24,MinWords=1,ShortWord=1"
_FACET_LIMIT = 20


def search_events(ctx: ReadContext, query: EventSearchQuery, secret: str) -> EventSearchPage:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, query)
    column, kind, attr = _event_sort(query.sort)
    position = _cursor(secret, query.cursor, _EVENTS, filters)
    prepared = _prepared(query.q)
    headline = _headline(EventSearchDocument.search_text, prepared)
    stmt = _apply_event_filters(select(EventSearchDocument), ctx.tenant_id, query)
    stmt = _keyset(stmt, column, EventSearchDocument.id, position, kind)
    stmt = stmt.order_by(column.desc(), EventSearchDocument.id.desc())
    if headline is not None:
        stmt = stmt.add_columns(headline)
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(
        rows,
        query.limit,
        lambda row: encode_key_cursor(
            secret,
            resource=_EVENTS,
            filters=filters,
            position=_key(row[0], kind, attr),
        ),
    )
    return EventSearchPage(data=[_event_hit(row[0], _snippet(row)) for row in visible], page=page)


def search_alerts(ctx: ReadContext, query: AlertSearchQuery, secret: str) -> AlertSearchPage:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, query)
    column, kind, attr = _alert_sort(query.sort)
    position = _cursor(secret, query.cursor, _ALERTS, filters)
    prepared = _prepared(query.q)
    headline = _headline(AlertSearchDocument.search_text, prepared)
    stmt = _apply_alert_filters(select(AlertSearchDocument), ctx.tenant_id, query)
    stmt = _keyset(stmt, column, AlertSearchDocument.id, position, kind)
    stmt = stmt.order_by(column.desc(), AlertSearchDocument.id.desc())
    if headline is not None:
        stmt = stmt.add_columns(headline)
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(
        rows,
        query.limit,
        lambda row: encode_key_cursor(
            secret,
            resource=_ALERTS,
            filters=filters,
            position=_key(row[0], kind, attr),
        ),
    )
    return AlertSearchPage(data=[_alert_hit(row[0], _snippet(row)) for row in visible], page=page)


def search_entities(ctx: ReadContext, query: EntitySearchQuery, secret: str) -> EntitySearchPage:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, query, entity_type=query.entity_type)
    column, kind, attr = _entity_sort(query.sort)
    position = _cursor(secret, query.cursor, _ENTITIES, filters)
    prepared = _prepared(query.q)
    headline = _headline(SecurityEntity.search_text, prepared)
    stmt = select(SecurityEntity).where(SecurityEntity.tenant_id == ctx.tenant_id)
    if query.entity_type is not None:
        stmt = stmt.where(SecurityEntity.entity_type == query.entity_type)
    match = _match(SecurityEntity.search_vector, prepared)
    if match is not None:
        stmt = stmt.where(match)
    linked = _linked_events(query)
    if linked is not None:
        stmt = stmt.where(linked)
    stmt = _keyset(stmt, column, SecurityEntity.id, position, kind)
    stmt = stmt.order_by(column.desc(), SecurityEntity.id.desc())
    if headline is not None:
        stmt = stmt.add_columns(headline)
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(
        rows,
        query.limit,
        lambda row: encode_key_cursor(
            secret,
            resource=_ENTITIES,
            filters=filters,
            position=_key(row[0], kind, attr),
        ),
    )
    return EntitySearchPage(data=[_entity_hit(row[0], _snippet(row)) for row in visible], page=page)


def get_entity(ctx: ReadContext, entity_id: UUID) -> EntitySearchHit:
    assert_reader(ctx.session, ctx.tenant_id)
    row = ctx.session.scalar(
        select(SecurityEntity).where(SecurityEntity.tenant_id == ctx.tenant_id, SecurityEntity.id == entity_id)
    )
    if row is None:
        raise ResourceNotFound("Entity")
    return _entity_hit(row, None)


def search_facets(ctx: ReadContext, query: FacetQuery) -> SearchFacets:
    assert_reader(ctx.session, ctx.tenant_id)
    return SearchFacets(
        event_type=_buckets(ctx, query, EventSearchDocument.event_type, skip="event_type"),
        severity=_buckets(ctx, query, EventSearchDocument.severity, skip="severity"),
        source=_buckets(ctx, query, EventSearchDocument.source_kind, skip="source"),
        host=_top(ctx, query, EventSearchDocument.hostname),
        user=_top(ctx, query, EventSearchDocument.username),
    )


def _event_sort(sort: SearchSort):
    if sort is SearchSort.SEVERITY:
        return EventSearchDocument.severity_rank, "rank", "severity_rank"
    if sort is SearchSort.CREATED_TIME:
        return EventSearchDocument.created_at, "time", "created_at"
    return EventSearchDocument.event_time, "time", "event_time"


def _alert_sort(sort: SearchSort):
    if sort is SearchSort.SEVERITY:
        return AlertSearchDocument.severity_rank, "rank", "severity_rank"
    if sort is SearchSort.CREATED_TIME:
        return AlertSearchDocument.created_at, "time", "created_at"
    return AlertSearchDocument.detected_at, "time", "detected_at"


def _entity_sort(sort: SearchSort):
    if sort is SearchSort.SEVERITY:
        return SecurityEntity.severity_rank, "rank", "severity_rank"
    if sort is SearchSort.CREATED_TIME:
        return SecurityEntity.first_seen, "time", "first_seen"
    return SecurityEntity.last_seen, "time", "last_seen"


def _apply_event_filters(stmt: Select, tenant_id: UUID, query, *, skip: str | None = None) -> Select:
    stmt = stmt.where(EventSearchDocument.tenant_id == tenant_id)
    if skip != "source" and query.source is not None:
        stmt = stmt.where(EventSearchDocument.source_kind == query.source)
    if skip != "severity" and query.severity is not None:
        stmt = stmt.where(EventSearchDocument.severity == query.severity)
    if skip != "status" and query.status is not None:
        stmt = stmt.where(EventSearchDocument.status == query.status)
    if skip != "event_type" and query.event_type is not None:
        stmt = stmt.where(EventSearchDocument.event_type == query.event_type)
    if skip != "time":
        stmt = _window(stmt, EventSearchDocument.event_time, query.start, query.end)
    match = _match(EventSearchDocument.search_vector, _prepared(query.q))
    if match is not None:
        stmt = stmt.where(match)
    return stmt


def _apply_alert_filters(stmt: Select, tenant_id: UUID, query) -> Select:
    stmt = stmt.where(AlertSearchDocument.tenant_id == tenant_id)
    if query.source is not None:
        stmt = stmt.where(AlertSearchDocument.source_kind == query.source)
    if query.severity is not None:
        stmt = stmt.where(AlertSearchDocument.severity == query.severity)
    if query.status is not None:
        stmt = stmt.where(AlertSearchDocument.status == query.status)
    if query.event_type is not None:
        stmt = stmt.where(AlertSearchDocument.event_type == query.event_type)
    stmt = _window(stmt, AlertSearchDocument.detected_at, query.start, query.end)
    match = _match(AlertSearchDocument.search_vector, _prepared(query.q))
    if match is not None:
        stmt = stmt.where(match)
    return stmt


def _linked_events(query: EntitySearchQuery):
    if not any((query.source, query.severity, query.status, query.event_type, query.start, query.end)):
        return None
    linked = (
        select(EventEntity.id)
        .join(
            EventSearchDocument,
            and_(
                EventSearchDocument.tenant_id == EventEntity.tenant_id,
                EventSearchDocument.id == EventEntity.canonical_event_id,
            ),
        )
        .where(
            EventEntity.tenant_id == SecurityEntity.tenant_id,
            EventEntity.entity_id == SecurityEntity.id,
        )
    )
    if query.source is not None:
        linked = linked.where(EventSearchDocument.source_kind == query.source)
    if query.severity is not None:
        linked = linked.where(EventSearchDocument.severity == query.severity)
    if query.status is not None:
        linked = linked.where(EventSearchDocument.status == query.status)
    if query.event_type is not None:
        linked = linked.where(EventSearchDocument.event_type == query.event_type)
    linked = _window(linked, EventSearchDocument.event_time, query.start, query.end)
    return exists(linked)


def _buckets(ctx: ReadContext, query: FacetQuery, column, *, skip: str) -> list[FacetBucket]:
    stmt = _apply_event_filters(select(column, func.count()), ctx.tenant_id, query, skip=skip)
    stmt = stmt.group_by(column).order_by(func.count().desc(), column.asc())
    return [_bucket(value, count) for value, count in ctx.session.execute(stmt).all()]


def _top(ctx: ReadContext, query: FacetQuery, column) -> list[FacetBucket]:
    stmt = _apply_event_filters(select(column, func.count()), ctx.tenant_id, query)
    stmt = (
        stmt.where(column.is_not(None))
        .group_by(column)
        .order_by(func.count().desc(), column.asc())
        .limit(_FACET_LIMIT)
    )
    return [_bucket(value, count) for value, count in ctx.session.execute(stmt).all()]


def _bucket(value, count: int) -> FacetBucket:
    rendered = value.value if hasattr(value, "value") else str(value)
    return FacetBucket(value=rendered, count=int(count))


def _filters(ctx: ReadContext, query, **extra: Any) -> dict[str, Any]:
    payload = {
        "tenant": ctx.tenant_id,
        "q": query.q,
        "source": query.source,
        "severity": query.severity,
        "status": query.status,
        "event_type": query.event_type,
        "sort": query.sort,
        "start": query.start,
        "end": query.end,
        "limit": query.limit,
    }
    payload.update(extra)
    return filter_payload(payload)


def _cursor(secret: str, token: str | None, resource: str, filters: dict[str, Any]) -> KeyCursor | None:
    if token is None:
        return None
    return decode_key_cursor(secret, token, resource=resource, filters=filters)


def _key(row, kind: str, attr: str) -> KeyCursor:
    if kind == "rank":
        return KeyCursor(row_id=row.id, rank=getattr(row, attr))
    return KeyCursor(row_id=row.id, sort_at=getattr(row, attr))


def _keyset(stmt: Select, column, id_column, position: KeyCursor | None, kind: str) -> Select:
    if position is None:
        return stmt
    if kind == "rank":
        if position.rank is None:
            raise InvalidCursor
        value = position.rank
    else:
        if position.sort_at is None:
            raise InvalidCursor
        value = position.sort_at
    return stmt.where(or_(column < value, and_(column == value, id_column < position.row_id)))


def _window(stmt: Select, column, start: datetime | None, end: datetime | None) -> Select:
    if start is not None:
        stmt = stmt.where(column >= start)
    if end is not None:
        stmt = stmt.where(column < end)
    return stmt


def _prepared(value: str | None) -> str | None:
    if value is None:
        return None
    return prepare_fts_query(value)


def _tsquery(prepared: str):
    return func.websearch_to_tsquery(cast(literal("simple"), REGCONFIG), cast(prepared, Text()))


def _match(column, prepared: str | None):
    if prepared is None:
        return None
    if not prepared:
        return false()
    return column.bool_op("@@")(_tsquery(prepared))


def _headline(column, prepared: str | None):
    if not prepared:
        return None
    return func.ts_headline(
        cast(literal("simple"), REGCONFIG),
        column,
        _tsquery(prepared),
        cast(literal(_HEADLINE), Text()),
    )


def _fetch(session: Session, stmt: Select, limit: int) -> list:
    bounded = stmt.limit(limit + 1).execution_options(populate_existing=True)
    return list(session.execute(bounded).all())


def _page(rows: list, limit: int, encode) -> tuple[list, PageInfo]:
    has_more = len(rows) > limit
    visible = rows[:limit]
    cursor = encode(visible[-1]) if has_more else None
    return visible, PageInfo(limit=limit, has_more=has_more, next_cursor=cursor)


def _snippet(row) -> str | None:
    if len(row) < 2 or row[1] is None:
        return None
    return str(row[1])


def _event_hit(row: EventSearchDocument, headline: str | None) -> EventSearchHit:
    return EventSearchHit(
        id=row.id,
        tenant_id=row.tenant_id,
        source=row.source_kind,
        event_type=row.event_type,
        severity=row.severity,
        status=row.status,
        hostname=row.hostname,
        username=row.username,
        message=row.message,
        event_time=row.event_time,
        created_at=row.created_at,
        headline=headline,
    )


def _alert_hit(row: AlertSearchDocument, headline: str | None) -> AlertSearchHit:
    return AlertSearchHit(
        id=row.id,
        tenant_id=row.tenant_id,
        canonical_event_id=row.canonical_event_id,
        source=row.source_kind,
        title=row.title,
        severity=row.severity,
        status=row.status,
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        event_type=row.event_type,
        hostname=row.hostname,
        username=row.username,
        detected_at=row.detected_at,
        created_at=row.created_at,
        headline=headline,
    )


def _entity_hit(row: SecurityEntity, headline: str | None) -> EntitySearchHit:
    return EntitySearchHit(
        id=row.id,
        tenant_id=row.tenant_id,
        entity_type=row.entity_type,
        value=row.value,
        display_value=row.display_value,
        severity=row.severity,
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        event_count=row.event_count,
        headline=headline,
    )
