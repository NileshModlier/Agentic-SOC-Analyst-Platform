"""Tenant-scoped reads. Statements select projected columns and never source payload bytes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from soc_platform.api.pagination import CursorPosition, decode_cursor, encode_cursor, filter_payload
from soc_platform.api.reader import ReadContext, assert_reader
from soc_platform.api.schemas import (
    AlertList,
    AlertListQuery,
    AlertRead,
    CaseDetail,
    CaseList,
    CaseListQuery,
    CaseRead,
    EventDetail,
    EventList,
    EventListQuery,
    EventRead,
    EvidenceDetail,
    EvidenceLinkRead,
    EvidenceList,
    EvidenceListQuery,
    EvidenceRead,
    FindingDetail,
    FindingList,
    FindingListQuery,
    FindingRead,
    InvestigationDetail,
    InvestigationList,
    InvestigationListQuery,
    InvestigationRead,
    PageInfo,
)
from soc_platform.api.errors import ResourceNotFound
from soc_platform.models import (
    Alert,
    CanonicalEvent,
    Case,
    Evidence,
    EvidenceLink,
    Finding,
    FindingAlert,
    Investigation,
    InvestigationAlert,
    SourceRecord,
)

_EVENTS = "events"
_ALERTS = "alerts"
_FINDINGS = "findings"
_CASES = "cases"
_INVESTIGATIONS = "investigations"
_EVIDENCE = "evidence"


def list_events(ctx: ReadContext, query: EventListQuery, secret: str) -> EventList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(
        ctx,
        source=query.source,
        severity=query.severity,
        event_type=query.event_type,
        start=query.start,
        end=query.end,
        limit=query.limit,
    )
    position = _position(secret, query.cursor, _EVENTS, filters)
    stmt = (
        select(CanonicalEvent, SourceRecord.source_kind)
        .join(
            SourceRecord,
            and_(
                SourceRecord.tenant_id == CanonicalEvent.tenant_id,
                SourceRecord.id == CanonicalEvent.source_record_id,
            ),
        )
        .where(CanonicalEvent.tenant_id == ctx.tenant_id)
    )
    if query.source is not None:
        stmt = stmt.where(SourceRecord.source_kind == query.source)
    if query.severity is not None:
        stmt = stmt.where(CanonicalEvent.severity == query.severity)
    if query.event_type is not None:
        stmt = stmt.where(CanonicalEvent.class_name == query.event_type)
    stmt = _window(stmt, CanonicalEvent.event_time, query.start, query.end)
    stmt = _before(stmt, CanonicalEvent.event_time, CanonicalEvent.id, position)
    stmt = stmt.order_by(CanonicalEvent.event_time.desc(), CanonicalEvent.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    page_rows, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret,
            resource=_EVENTS,
            filters=filters,
            sort_at=row[0].event_time,
            row_id=row[0].id,
        ),
    )
    return EventList(data=[_event(row[0], row[1]) for row in page_rows], page=page)


def get_event(ctx: ReadContext, event_id: UUID) -> EventDetail:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = (
        select(CanonicalEvent, SourceRecord.source_kind)
        .join(
            SourceRecord,
            and_(
                SourceRecord.tenant_id == CanonicalEvent.tenant_id,
                SourceRecord.id == CanonicalEvent.source_record_id,
            ),
        )
        .where(CanonicalEvent.tenant_id == ctx.tenant_id, CanonicalEvent.id == event_id)
    )
    row, source = _one(ctx.session, stmt, "Event")
    summary = _event(row, source)
    return EventDetail(**summary.model_dump(), document=dict(row.document))


def list_alerts(ctx: ReadContext, query: AlertListQuery, secret: str) -> AlertList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(
        ctx,
        source=query.source,
        severity=query.severity,
        alert_status=query.alert_status,
        start=query.start,
        end=query.end,
        limit=query.limit,
    )
    position = _position(secret, query.cursor, _ALERTS, filters)
    stmt = select(Alert).where(Alert.tenant_id == ctx.tenant_id)
    if query.source is not None:
        stmt = stmt.where(Alert.source_kind == query.source)
    if query.severity is not None:
        stmt = stmt.where(Alert.severity == query.severity)
    if query.alert_status is not None:
        stmt = stmt.where(Alert.status == query.alert_status)
    stmt = _window(stmt, Alert.detected_at, query.start, query.end)
    stmt = _before(stmt, Alert.detected_at, Alert.id, position)
    stmt = stmt.order_by(Alert.detected_at.desc(), Alert.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    page_rows, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret, resource=_ALERTS, filters=filters, sort_at=row[0].detected_at, row_id=row[0].id
        ),
    )
    return AlertList(data=[_alert(row[0]) for row in page_rows], page=page)


def get_alert(ctx: ReadContext, alert_id: UUID) -> AlertRead:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = select(Alert).where(Alert.tenant_id == ctx.tenant_id, Alert.id == alert_id)
    row = _one(ctx.session, stmt, "Alert")
    return _alert(row[0])


def list_findings(ctx: ReadContext, query: FindingListQuery, secret: str) -> FindingList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, severity=query.severity, start=query.start, end=query.end, limit=query.limit)
    position = _position(secret, query.cursor, _FINDINGS, filters)
    stmt = select(Finding).where(Finding.tenant_id == ctx.tenant_id)
    if query.severity is not None:
        stmt = stmt.where(Finding.severity == query.severity)
    stmt = _window(stmt, Finding.created_at, query.start, query.end)
    stmt = _before(stmt, Finding.created_at, Finding.id, position)
    stmt = stmt.order_by(Finding.created_at.desc(), Finding.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    page_rows, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret, resource=_FINDINGS, filters=filters, sort_at=row[0].created_at, row_id=row[0].id
        ),
    )
    return FindingList(data=[_finding(row[0]) for row in page_rows], page=page)


def get_finding(ctx: ReadContext, finding_id: UUID) -> FindingDetail:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = select(Finding).where(Finding.tenant_id == ctx.tenant_id, Finding.id == finding_id)
    row = _one(ctx.session, stmt, "Finding")[0]
    alert_ids = list(
        ctx.session.scalars(
            select(FindingAlert.alert_id)
            .where(FindingAlert.tenant_id == ctx.tenant_id, FindingAlert.finding_id == finding_id)
            .order_by(FindingAlert.linked_at.asc(), FindingAlert.alert_id.asc())
        ).all()
    )
    return FindingDetail(**_finding(row).model_dump(), alert_ids=alert_ids)


def list_cases(ctx: ReadContext, query: CaseListQuery, secret: str) -> CaseList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(
        ctx,
        severity=query.severity,
        case_status=query.case_status,
        start=query.start,
        end=query.end,
        limit=query.limit,
    )
    position = _position(secret, query.cursor, _CASES, filters)
    stmt = select(Case).where(Case.tenant_id == ctx.tenant_id)
    if query.severity is not None:
        stmt = stmt.where(Case.severity == query.severity)
    if query.case_status is not None:
        stmt = stmt.where(Case.status == query.case_status)
    stmt = _window(stmt, Case.opened_at, query.start, query.end)
    stmt = _before(stmt, Case.opened_at, Case.id, position)
    stmt = stmt.order_by(Case.opened_at.desc(), Case.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    page_rows, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret, resource=_CASES, filters=filters, sort_at=row[0].opened_at, row_id=row[0].id
        ),
    )
    return CaseList(data=[_case(row[0]) for row in page_rows], page=page)


def get_case(ctx: ReadContext, case_id: UUID) -> CaseDetail:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = select(Case).where(Case.tenant_id == ctx.tenant_id, Case.id == case_id)
    row = _one(ctx.session, stmt, "Case")[0]
    investigation_ids = list(
        ctx.session.scalars(
            select(Investigation.id)
            .where(Investigation.tenant_id == ctx.tenant_id, Investigation.case_id == case_id)
            .order_by(Investigation.opened_at.asc(), Investigation.id.asc())
        ).all()
    )
    finding_ids = list(
        ctx.session.scalars(
            select(Finding.id)
            .where(Finding.tenant_id == ctx.tenant_id, Finding.case_id == case_id)
            .order_by(Finding.created_at.asc(), Finding.id.asc())
        ).all()
    )
    return CaseDetail(
        **_case(row).model_dump(),
        investigation_ids=investigation_ids,
        finding_ids=finding_ids,
    )


def list_investigations(ctx: ReadContext, query: InvestigationListQuery, secret: str) -> InvestigationList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(
        ctx,
        investigation_status=query.investigation_status,
        start=query.start,
        end=query.end,
        limit=query.limit,
    )
    position = _position(secret, query.cursor, _INVESTIGATIONS, filters)
    stmt = select(Investigation).where(Investigation.tenant_id == ctx.tenant_id)
    if query.investigation_status is not None:
        stmt = stmt.where(Investigation.status == query.investigation_status)
    stmt = _window(stmt, Investigation.opened_at, query.start, query.end)
    stmt = _before(stmt, Investigation.opened_at, Investigation.id, position)
    stmt = stmt.order_by(Investigation.opened_at.desc(), Investigation.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    page_rows, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret,
            resource=_INVESTIGATIONS,
            filters=filters,
            sort_at=row[0].opened_at,
            row_id=row[0].id,
        ),
    )
    return InvestigationList(data=[_investigation(row[0]) for row in page_rows], page=page)


def get_investigation(ctx: ReadContext, investigation_id: UUID) -> InvestigationDetail:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = select(Investigation).where(
        Investigation.tenant_id == ctx.tenant_id, Investigation.id == investigation_id
    )
    row = _one(ctx.session, stmt, "Investigation")[0]
    alert_ids = list(
        ctx.session.scalars(
            select(InvestigationAlert.alert_id)
            .where(
                InvestigationAlert.tenant_id == ctx.tenant_id,
                InvestigationAlert.investigation_id == investigation_id,
            )
            .order_by(InvestigationAlert.linked_at.asc(), InvestigationAlert.alert_id.asc())
        ).all()
    )
    return InvestigationDetail(**_investigation(row).model_dump(), alert_ids=alert_ids)


def list_evidence(ctx: ReadContext, query: EvidenceListQuery, secret: str) -> EvidenceList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(ctx, source=query.source, start=query.start, end=query.end, limit=query.limit)
    position = _position(secret, query.cursor, _EVIDENCE, filters)
    stmt = (
        select(Evidence, SourceRecord.source_kind, SourceRecord.byte_size)
        .join(
            SourceRecord,
            and_(
                SourceRecord.tenant_id == Evidence.tenant_id,
                SourceRecord.id == Evidence.source_record_id,
            ),
        )
        .where(Evidence.tenant_id == ctx.tenant_id)
    )
    if query.source is not None:
        stmt = stmt.where(SourceRecord.source_kind == query.source)
    stmt = _window(stmt, Evidence.collected_at, query.start, query.end)
    stmt = _before(stmt, Evidence.collected_at, Evidence.id, position)
    stmt = stmt.order_by(Evidence.collected_at.desc(), Evidence.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    page_rows, page = _page(
        rows,
        query.limit,
        lambda row: encode_cursor(
            secret, resource=_EVIDENCE, filters=filters, sort_at=row[0].collected_at, row_id=row[0].id
        ),
    )
    return EvidenceList(data=[_evidence(row[0], row[1], row[2]) for row in page_rows], page=page)


def get_evidence(ctx: ReadContext, evidence_id: UUID) -> EvidenceDetail:
    assert_reader(ctx.session, ctx.tenant_id)
    stmt = (
        select(Evidence, SourceRecord.source_kind, SourceRecord.byte_size)
        .join(
            SourceRecord,
            and_(
                SourceRecord.tenant_id == Evidence.tenant_id,
                SourceRecord.id == Evidence.source_record_id,
            ),
        )
        .where(Evidence.tenant_id == ctx.tenant_id, Evidence.id == evidence_id)
    )
    row, source, byte_size = _one(ctx.session, stmt, "Evidence")
    links = list(
        ctx.session.scalars(
            select(EvidenceLink)
            .where(EvidenceLink.tenant_id == ctx.tenant_id, EvidenceLink.evidence_id == evidence_id)
            .order_by(EvidenceLink.linked_at.asc(), EvidenceLink.id.asc())
        ).all()
    )
    return EvidenceDetail(
        **_evidence(row, source, byte_size).model_dump(),
        links=[_link(item) for item in links],
    )


def _filters(ctx: ReadContext, **values: Any) -> dict[str, Any]:
    return filter_payload({"tenant": ctx.tenant_id, **values})


def _position(secret: str, cursor: str | None, resource: str, filters: dict[str, Any]) -> CursorPosition | None:
    if cursor is None:
        return None
    return decode_cursor(secret, cursor, resource=resource, filters=filters)


def _window(stmt: Select, column, start: datetime | None, end: datetime | None) -> Select:
    if start is not None:
        stmt = stmt.where(column >= start)
    if end is not None:
        stmt = stmt.where(column < end)
    return stmt


def _before(stmt: Select, time_column, id_column, position: CursorPosition | None) -> Select:
    if position is None:
        return stmt
    return stmt.where(
        or_(
            time_column < position.sort_at,
            and_(time_column == position.sort_at, id_column < position.row_id),
        )
    )


def _fetch(session: Session, stmt: Select, limit: int) -> list:
    bounded = stmt.limit(limit + 1).execution_options(populate_existing=True)
    return list(session.execute(bounded).all())


def _one(session: Session, stmt: Select, resource: str):
    row = session.execute(stmt.limit(1).execution_options(populate_existing=True)).one_or_none()
    if row is None:
        raise ResourceNotFound(resource)
    return row


def _page(rows: list, limit: int, encode) -> tuple[list, PageInfo]:
    has_more = len(rows) > limit
    visible = rows[:limit]
    cursor = encode(visible[-1]) if has_more else None
    return visible, PageInfo(limit=limit, has_more=has_more, next_cursor=cursor)


def _event(row: CanonicalEvent, source) -> EventRead:
    return EventRead(
        id=row.id,
        tenant_id=row.tenant_id,
        source_record_id=row.source_record_id,
        source=source,
        event_time=row.event_time,
        category_uid=row.category_uid,
        category_name=row.category_name,
        class_uid=row.class_uid,
        class_name=row.class_name,
        activity_id=row.activity_id,
        activity_name=row.activity_name,
        type_uid=row.type_uid,
        severity=row.severity,
        outcome=row.outcome,
        hostname=row.hostname,
        username=row.username,
        message=row.message,
        technique_ids=list(row.technique_ids or []),
        schema_version=row.schema_version,
        normalizer_version=row.normalizer_version,
        projection_generation=row.projection_generation,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _alert(row: Alert) -> AlertRead:
    return AlertRead(
        id=row.id,
        tenant_id=row.tenant_id,
        source_record_id=row.source_record_id,
        canonical_event_id=row.canonical_event_id,
        source=row.source_kind,
        external_id=row.external_id,
        title=row.title,
        description=row.description,
        severity=row.severity,
        status=row.status,
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        vendor=row.vendor,
        product=row.product,
        technique_ids=list(row.technique_ids or []),
        tactics=list(row.tactics or []),
        dedup_key=row.dedup_key,
        correlation_key=row.correlation_key,
        detected_at=row.detected_at,
        projection_generation=row.projection_generation,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _finding(row: Finding) -> FindingRead:
    return FindingRead(
        id=row.id,
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        investigation_id=row.investigation_id,
        title=row.title,
        summary=row.summary,
        severity=row.severity,
        confidence=row.confidence,
        status=row.status,
        disposition=row.disposition,
        technique_ids=list(row.technique_ids or []),
        tactics=list(row.tactics or []),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _investigation(row: Investigation) -> InvestigationRead:
    return InvestigationRead(
        id=row.id,
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        title=row.title,
        status=row.status,
        priority=row.priority,
        hypothesis=row.hypothesis,
        summary=row.summary,
        assignee=row.assignee,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _case(row: Case) -> CaseRead:
    return CaseRead(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        description=row.description,
        status=row.status,
        severity=row.severity,
        assignee=row.assignee,
        external_ref=row.external_ref,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _evidence(row: Evidence, source, byte_size: int) -> EvidenceRead:
    return EvidenceRead(
        id=row.id,
        tenant_id=row.tenant_id,
        source_record_id=row.source_record_id,
        source=source,
        evidence_type=row.evidence_type,
        description=row.description,
        content_sha256=row.content_sha256,
        byte_size=byte_size,
        collected_at=row.collected_at,
        collected_by=row.collected_by,
        created_at=row.created_at,
    )


def _link(row: EvidenceLink) -> EvidenceLinkRead:
    return EvidenceLinkRead(
        id=row.id,
        alert_id=row.alert_id,
        canonical_event_id=row.canonical_event_id,
        finding_id=row.finding_id,
        investigation_id=row.investigation_id,
        case_id=row.case_id,
        linked_by=row.linked_by,
        linked_at=row.linked_at,
    )
