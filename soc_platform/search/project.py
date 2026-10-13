"""Maintain search projections in the caller's transaction."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from soc_platform.domain.canonical import SEVERITY_IDS
from soc_platform.domain.enums import Severity, SourceKind
from soc_platform.models import Alert, CanonicalEvent
from soc_platform.models.mixins import new_uuid
from soc_platform.models.search import AlertSearchDocument, EventEntity, EventSearchDocument, SecurityEntity
from soc_platform.search.extract import entity_drafts, event_search_parts
from soc_platform.search.text import fts_document

_RANK_TO_SEVERITY = {rank: Severity(name) for name, rank in SEVERITY_IDS.items()}


def rebuild_search(session: Session) -> None:
    """Project every stored event and alert. Used by the Phase 3 migration."""
    events = list(session.scalars(select(CanonicalEvent)).all())
    by_id = {event.id: event for event in events}
    for event in events:
        source = _source_kind(session, event)
        project_event(session, event, source)
    for alert in session.scalars(select(Alert)).all():
        event = by_id.get(alert.canonical_event_id) if alert.canonical_event_id is not None else None
        project_alert(session, alert, event)


def project_event(session: Session, event: CanonicalEvent, source_kind: SourceKind | str) -> None:
    kind = source_kind if isinstance(source_kind, SourceKind) else SourceKind(source_kind)
    rank = SEVERITY_IDS[event.severity.value if isinstance(event.severity, Severity) else str(event.severity)]
    text = fts_document(*event_search_parts(event))
    row = session.get(EventSearchDocument, event.id)
    if row is None:
        row = EventSearchDocument(id=event.id, tenant_id=event.tenant_id, search_text=text or event.message)
        session.add(row)
    row.source_kind = kind
    row.severity = event.severity
    row.severity_rank = rank
    row.status = event.outcome
    row.event_type = event.class_name
    row.hostname = event.hostname
    row.username = event.username
    row.message = event.message
    row.event_time = event.event_time
    row.created_at = event.created_at
    row.search_text = text or event.message
    _relink_entities(session, event)
    session.flush()


def project_alert(session: Session, alert: Alert, event: CanonicalEvent | None) -> None:
    rank = SEVERITY_IDS[alert.severity.value if isinstance(alert.severity, Severity) else str(alert.severity)]
    parts = [alert.title, alert.rule_name, alert.rule_id, alert.description]
    if event is not None:
        parts.extend(event_search_parts(event))
    text = fts_document(*parts)
    row = session.get(AlertSearchDocument, alert.id)
    if row is None:
        row = AlertSearchDocument(id=alert.id, tenant_id=alert.tenant_id, search_text=text or alert.title)
        session.add(row)
    row.canonical_event_id = alert.canonical_event_id
    row.source_kind = alert.source_kind
    row.severity = alert.severity
    row.severity_rank = rank
    row.status = alert.status
    row.title = alert.title
    row.rule_id = alert.rule_id
    row.rule_name = alert.rule_name
    row.event_type = None if event is None else event.class_name
    row.hostname = None if event is None else event.hostname
    row.username = None if event is None else event.username
    row.detected_at = alert.detected_at
    row.created_at = alert.created_at
    row.search_text = text or alert.title
    session.flush()


def _relink_entities(session: Session, event: CanonicalEvent) -> None:
    drafts = entity_drafts(event)
    existing = list(
        session.scalars(
            select(EventEntity).where(
                EventEntity.tenant_id == event.tenant_id,
                EventEntity.canonical_event_id == event.id,
            )
        ).all()
    )
    previous_ids = {link.entity_id for link in existing}
    wanted: dict[UUID, SecurityEntity] = {}
    for draft in drafts:
        entity = _upsert_entity(session, event.tenant_id, draft, event.event_time)
        wanted[entity.id] = entity
    for link in existing:
        if link.entity_id not in wanted:
            session.delete(link)
    linked = previous_ids
    for entity_id in wanted:
        if entity_id not in linked:
            session.add(
                EventEntity(
                    id=new_uuid(),
                    tenant_id=event.tenant_id,
                    canonical_event_id=event.id,
                    entity_id=entity_id,
                )
            )
    session.flush()
    _refresh_entities(session, event.tenant_id, previous_ids | set(wanted))


def _upsert_entity(session: Session, tenant_id: UUID, draft, seen_at) -> SecurityEntity:
    row = session.scalar(
        select(SecurityEntity).where(
            SecurityEntity.tenant_id == tenant_id,
            SecurityEntity.entity_type == draft.entity_type,
            SecurityEntity.value == draft.value,
        )
    )
    if row is not None:
        return row
    row = SecurityEntity(
        id=new_uuid(),
        tenant_id=tenant_id,
        entity_type=draft.entity_type,
        value=draft.value,
        display_value=draft.display_value,
        severity=Severity.UNKNOWN,
        severity_rank=0,
        first_seen=seen_at,
        last_seen=seen_at,
        event_count=0,
        search_text=fts_document(draft.display_value),
    )
    session.add(row)
    session.flush()
    return row


def _refresh_entities(session: Session, tenant_id: UUID, entity_ids: set[UUID]) -> None:
    if not entity_ids:
        return
    stats = session.execute(
        select(
            EventEntity.entity_id,
            func.count(),
            func.min(EventSearchDocument.event_time),
            func.max(EventSearchDocument.event_time),
            func.max(EventSearchDocument.severity_rank),
        )
        .join(
            EventSearchDocument,
            (EventSearchDocument.tenant_id == EventEntity.tenant_id)
            & (EventSearchDocument.id == EventEntity.canonical_event_id),
        )
        .where(EventEntity.tenant_id == tenant_id, EventEntity.entity_id.in_(entity_ids))
        .group_by(EventEntity.entity_id)
    ).all()
    found = {row[0] for row in stats}
    for entity_id, count, first_seen, last_seen, rank in stats:
        entity = session.get(SecurityEntity, entity_id)
        if entity is None:
            continue
        entity.event_count = int(count)
        entity.first_seen = first_seen
        entity.last_seen = last_seen
        entity.severity_rank = int(rank)
        entity.severity = _RANK_TO_SEVERITY[int(rank)]
    missing = entity_ids - found
    if missing:
        session.execute(
            delete(EventEntity).where(EventEntity.tenant_id == tenant_id, EventEntity.entity_id.in_(missing))
        )
        session.execute(
            delete(SecurityEntity).where(SecurityEntity.tenant_id == tenant_id, SecurityEntity.id.in_(missing))
        )
    session.flush()


def _source_kind(session: Session, event: CanonicalEvent) -> SourceKind:
    document = event.document if isinstance(event.document, dict) else {}
    soc = document.get("soc") if isinstance(document.get("soc"), dict) else {}
    raw = soc.get("source_kind")
    if isinstance(raw, str):
        return SourceKind(raw)
    from soc_platform.models import SourceRecord

    record = session.get(SourceRecord, event.source_record_id)
    if record is not None:
        return record.source_kind if isinstance(record.source_kind, SourceKind) else SourceKind(record.source_kind)
    raise RuntimeError(f"canonical event {event.id} has no source kind")
