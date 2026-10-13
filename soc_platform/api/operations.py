"""Tenant-scoped intake reads. Statements never select payload bytes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, select

from soc_platform.api.operations_schemas import (
    ConnectorHealth,
    ConnectorHealthList,
    DeadLetterList,
    DeadLetterQuery,
    DeadLetterRead,
    PublicationList,
    PublicationQuery,
    PublicationRead,
)
from soc_platform.api.pagination import encode_cursor
from soc_platform.api.queries import _before, _fetch, _filters, _page, _position, _window
from soc_platform.api.reader import ReadContext, assert_reader
from soc_platform.domain.enums import ReceiptStatus, SourceKind
from soc_platform.models.dead_letter import DeadLetter
from soc_platform.models.outbox import OutboxEvent
from soc_platform.models.source_record import IngestReceipt, SourceRecord

_DEAD_LETTERS = "dead_letters"
_PUBLICATIONS = "outbox_events"

_CONNECTORS = (
    (SourceKind.SIGMA_ALERT, "Sigma"),
    (SourceKind.MOCK_EDR_ALERT, "EDR"),
    (SourceKind.WINDOWS_EVENT, "Windows"),
)


def connector_health(ctx: ReadContext) -> ConnectorHealthList:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = (
        select(
            SourceRecord.source_kind,
            IngestReceipt.status,
            func.count(),
            func.max(SourceRecord.received_at),
        )
        .join(
            IngestReceipt,
            and_(
                IngestReceipt.tenant_id == SourceRecord.tenant_id,
                IngestReceipt.source_record_id == SourceRecord.id,
            ),
        )
        .where(SourceRecord.tenant_id == ctx.tenant_id)
        .group_by(SourceRecord.source_kind, IngestReceipt.status)
    )
    projected: dict[SourceKind, int] = {}
    dead: dict[SourceKind, int] = {}
    last_seen: dict[SourceKind, datetime] = {}
    for source, status, count, received_at in ctx.session.execute(stmt).all():
        if status == ReceiptStatus.PROJECTED:
            projected[source] = int(count)
        elif status == ReceiptStatus.DEAD_LETTERED:
            dead[source] = int(count)
        if received_at is not None and (source not in last_seen or received_at > last_seen[source]):
            last_seen[source] = received_at
    return ConnectorHealthList(
        data=[
            ConnectorHealth(
                source=source,
                label=label,
                projected=projected.get(source, 0),
                dead_lettered=dead.get(source, 0),
                last_received_at=last_seen.get(source),
            )
            for source, label in _CONNECTORS
        ]
    )


def list_dead_letters(ctx: ReadContext, query: DeadLetterQuery, secret: str) -> DeadLetterList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, open_only=query.open_only, start=query.start, end=query.end, limit=query.limit)
    position = _position(secret, query.cursor, _DEAD_LETTERS, filters)
    stmt = select(
        DeadLetter.id,
        DeadLetter.tenant_id,
        DeadLetter.source_record_id,
        DeadLetter.outbox_event_id,
        DeadLetter.stage,
        DeadLetter.reason_code,
        DeadLetter.error_message,
        DeadLetter.attempt_count,
        DeadLetter.payload_sha256,
        DeadLetter.created_at,
        DeadLetter.resolved_at,
    ).where(DeadLetter.tenant_id == ctx.tenant_id)
    if query.open_only:
        stmt = stmt.where(DeadLetter.resolved_at.is_(None))
    stmt = _window(stmt, DeadLetter.created_at, query.start, query.end)
    stmt = _before(stmt, DeadLetter.created_at, DeadLetter.id, position)
    stmt = stmt.order_by(DeadLetter.created_at.desc(), DeadLetter.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret,
            resource=_DEAD_LETTERS,
            filters=filters,
            sort_at=row.created_at,
            row_id=row.id,
        ),
    )
    return DeadLetterList(
        data=[
            DeadLetterRead(
                id=row.id,
                tenant_id=row.tenant_id,
                source_record_id=row.source_record_id,
                outbox_event_id=row.outbox_event_id,
                stage=row.stage,
                reason_code=row.reason_code,
                error_message=row.error_message,
                attempt_count=row.attempt_count,
                payload_sha256=row.payload_sha256,
                created_at=row.created_at,
                resolved_at=row.resolved_at,
            )
            for row in visible
        ],
        page=page,
    )


def list_publications(ctx: ReadContext, query: PublicationQuery, secret: str) -> PublicationList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, start=query.start, end=query.end, limit=query.limit)
    position = _position(secret, query.cursor, _PUBLICATIONS, filters)
    stmt = select(
        OutboxEvent.id,
        OutboxEvent.tenant_id,
        OutboxEvent.aggregate_type,
        OutboxEvent.aggregate_id,
        OutboxEvent.event_type,
        OutboxEvent.status,
        OutboxEvent.attempts,
        OutboxEvent.last_error,
        OutboxEvent.created_at,
        OutboxEvent.published_at,
    ).where(OutboxEvent.tenant_id == ctx.tenant_id)
    stmt = _window(stmt, OutboxEvent.created_at, query.start, query.end)
    stmt = _before(stmt, OutboxEvent.created_at, OutboxEvent.id, position)
    stmt = stmt.order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret,
            resource=_PUBLICATIONS,
            filters=filters,
            sort_at=row.created_at,
            row_id=row.id,
        ),
    )
    return PublicationList(
        data=[
            PublicationRead(
                id=row.id,
                tenant_id=row.tenant_id,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                event_type=row.event_type,
                status=row.status,
                attempts=row.attempts,
                last_error=row.last_error,
                created_at=row.created_at,
                published_at=row.published_at,
            )
            for row in visible
        ],
        page=page,
    )
