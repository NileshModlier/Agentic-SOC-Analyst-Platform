"""Store immutable bytes, project records, and enqueue an outbox row in one transaction.

The caller owns the transaction. Commit publishes the intake and the outbox row
together. Rollback discards both. Replay reads ``source_records.payload`` and
does not modify that row.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from soc_platform.db.session import database_now
from soc_platform.observability.tracing import traced
from soc_platform.domain.canonical import NORMALIZER_VERSION, OCSF_VERSION, from_epoch_ms, qualified_user
from soc_platform.domain.enums import (
    AlertStatus,
    DeadLetterStage,
    EvidenceType,
    Outcome,
    OutboxStatus,
    ReceiptStatus,
    Severity,
    SourceKind,
    TenantStatus,
)
from soc_platform.domain.errors import (
    IngestParseError,
    IngestRejected,
    PayloadTooLarge,
    SourceRecordNotFound,
    TenantDisabled,
    TenantNotFound,
)
from soc_platform.domain.events import (
    ALERT_INGESTED,
    INGEST_DEAD_LETTERED,
    INGEST_REPLAY_FAILED,
    INGEST_REPLAYED,
    SECURITY_EVENT_NORMALIZED,
)
from soc_platform.hashing import sha256_hex
from soc_platform.ingestion.codec import clip, sniff_content_type
from soc_platform.ingestion.registry import parser_for
from soc_platform.search.project import project_alert, project_event
from soc_platform.ingestion.types import AlertDraft, ParsedIngest
from soc_platform.models import (
    Alert,
    CanonicalEvent,
    DeadLetter,
    Evidence,
    EvidenceLink,
    IngestReceipt,
    OutboxEvent,
    SourceRecord,
    Tenant,
)
from soc_platform.models.mixins import new_uuid

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class IngestResult:
    tenant_id: UUID
    source_record_id: UUID
    source_kind: SourceKind
    content_sha256: str
    duplicate: bool
    canonical_event_id: UUID | None
    alert_id: UUID | None
    evidence_id: UUID | None
    dead_letter_id: UUID | None
    outbox_event_id: UUID | None
    receipt_status: ReceiptStatus


class _DuplicateSource(Exception):
    def __init__(self, record: SourceRecord) -> None:
        self.record = record


@traced("ingest")
def ingest(
    session: Session,
    *,
    tenant_id: UUID,
    source_kind: SourceKind | str,
    payload: bytes,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> IngestResult:
    if isinstance(payload, bytearray):
        payload = bytes(payload)
    if not isinstance(payload, bytes):
        raise IngestRejected("payload must be bytes", "invalid_payload")
    if len(payload) > max_payload_bytes:
        raise PayloadTooLarge(len(payload), max_payload_bytes)
    kind = source_kind if isinstance(source_kind, SourceKind) else SourceKind(source_kind)
    _require_active_tenant(session, tenant_id)
    digest = sha256_hex(payload)
    existing = _find_source(session, tenant_id, digest)
    if existing is not None:
        return _result_from_existing(session, existing, duplicate=True)

    at = database_now(session)
    try:
        parsed = parser_for(kind).parse(payload)
    except IngestParseError as exc:
        try:
            record = _insert_source(
                session,
                tenant_id=tenant_id,
                source_kind=kind,
                payload=payload,
                digest=digest,
                external_id=None,
                received_at=at,
            )
        except _DuplicateSource as duplicate:
            return _result_from_existing(session, duplicate.record, duplicate=True)
        return _persist_failure(session, record, at, exc, replay=False)

    try:
        record = _insert_source(
            session,
            tenant_id=tenant_id,
            source_kind=kind,
            payload=payload,
            digest=digest,
            external_id=parsed.external_id,
            received_at=at,
        )
    except _DuplicateSource as duplicate:
        return _result_from_existing(session, duplicate.record, duplicate=True)
    return _persist_success(session, record, parsed, at, replay=False)


@traced("replay")
def replay(session: Session, *, tenant_id: UUID, source_record_id: UUID) -> IngestResult:
    """Re-project one source record from the bytes that were stored at intake."""
    _require_active_tenant(session, tenant_id)
    record = session.get(SourceRecord, source_record_id)
    if record is None or record.tenant_id != tenant_id:
        raise SourceRecordNotFound(tenant_id, source_record_id)
    at = database_now(session)
    try:
        parsed = parser_for(record.source_kind).parse(bytes(record.payload))
    except IngestParseError as exc:
        return _persist_failure(session, record, at, exc, replay=True)
    return _persist_success(session, record, parsed, at, replay=True)


def _require_active_tenant(session: Session, tenant_id: UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantNotFound(tenant_id)
    if tenant.status != TenantStatus.ACTIVE:
        raise TenantDisabled(tenant_id)
    return tenant


def _find_source(session: Session, tenant_id: UUID, digest: str) -> SourceRecord | None:
    return session.scalar(
        select(SourceRecord).where(
            SourceRecord.tenant_id == tenant_id,
            SourceRecord.content_sha256 == digest,
        )
    )


def _insert_source(
    session: Session,
    *,
    tenant_id: UUID,
    source_kind: SourceKind,
    payload: bytes,
    digest: str,
    external_id: str | None,
    received_at: datetime,
) -> SourceRecord:
    record = SourceRecord(
        id=new_uuid(),
        tenant_id=tenant_id,
        source_kind=source_kind,
        content_type=sniff_content_type(payload),
        content_sha256=digest,
        byte_size=len(payload),
        payload=payload,
        external_id=external_id,
        received_at=received_at,
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError as exc:
        if record in session:
            session.expunge(record)
        if _constraint_name(exc) != "uq_source_records_hash":
            raise
        existing = _find_source(session, tenant_id, digest)
        if existing is None:
            raise
        raise _DuplicateSource(existing) from exc
    return record


def _persist_success(
    session: Session,
    record: SourceRecord,
    parsed: ParsedIngest,
    at: datetime,
    *,
    replay: bool,
) -> IngestResult:
    event_row = _upsert_event(session, record, parsed, at)
    session.flush()
    alert_row = _upsert_alert(session, record, parsed.alert, event_row, at) if parsed.alert else _alert_for(session, record)
    if parsed.alert is not None:
        session.flush()
    project_event(session, event_row, record.source_kind)
    if alert_row is not None and parsed.alert is not None:
        project_alert(session, alert_row, event_row)
    evidence = _ensure_evidence(session, record, at)
    session.flush()
    _ensure_link(
        session,
        record,
        evidence,
        alert_id=alert_row.id if alert_row is not None and parsed.alert is not None else None,
        canonical_event_id=event_row.id,
        at=at,
    )
    _resolve_dead_letters(session, record, at)
    receipt = _touch_receipt(
        session,
        record,
        at=at,
        status=ReceiptStatus.PROJECTED,
        error_code=None,
        error_message=None,
        projected=True,
    )
    event_type = INGEST_REPLAYED if replay else ALERT_INGESTED if alert_row is not None else SECURITY_EVENT_NORMALIZED
    outbox = _add_outbox(
        session,
        record,
        at=at,
        event_type=event_type,
        canonical_event_id=event_row.id,
        alert_id=alert_row.id if alert_row is not None else None,
        evidence_id=evidence.id,
        dead_letter_id=None,
    )
    session.flush()
    _log_result(record, duplicate=False, dead_lettered=False)
    return IngestResult(
        tenant_id=record.tenant_id,
        source_record_id=record.id,
        source_kind=record.source_kind,
        content_sha256=record.content_sha256,
        duplicate=False,
        canonical_event_id=event_row.id,
        alert_id=alert_row.id if alert_row is not None else None,
        evidence_id=evidence.id,
        dead_letter_id=None,
        outbox_event_id=outbox.id,
        receipt_status=receipt.status,
    )


def _persist_failure(
    session: Session,
    record: SourceRecord,
    at: datetime,
    exc: IngestParseError,
    *,
    replay: bool,
) -> IngestResult:
    receipt = _touch_receipt(
        session,
        record,
        at=at,
        status=ReceiptStatus.DEAD_LETTERED,
        error_code=exc.reason_code,
        error_message=str(exc)[:4000],
        projected=False,
    )
    existing_event = _event_for(session, record)
    existing_alert = _alert_for(session, record)
    existing_evidence = _evidence_for(session, record)
    dead = DeadLetter(
        id=new_uuid(),
        tenant_id=record.tenant_id,
        source_record_id=record.id,
        outbox_event_id=None,
        stage=DeadLetterStage.REPLAY if replay else DeadLetterStage.PARSE,
        reason_code=exc.reason_code,
        error_message=str(exc)[:4000],
        attempt_count=receipt.attempt_count,
        payload_bytes=None,
        payload_sha256=None,
        created_at=at,
        resolved_at=None,
    )
    session.add(dead)
    outbox = _add_outbox(
        session,
        record,
        at=at,
        event_type=INGEST_REPLAY_FAILED if replay else INGEST_DEAD_LETTERED,
        canonical_event_id=existing_event.id if existing_event is not None else None,
        alert_id=existing_alert.id if existing_alert is not None else None,
        evidence_id=existing_evidence.id if existing_evidence is not None else None,
        dead_letter_id=dead.id,
    )
    session.flush()
    _log_result(record, duplicate=False, dead_lettered=True)
    return IngestResult(
        tenant_id=record.tenant_id,
        source_record_id=record.id,
        source_kind=record.source_kind,
        content_sha256=record.content_sha256,
        duplicate=False,
        canonical_event_id=existing_event.id if existing_event is not None else None,
        alert_id=existing_alert.id if existing_alert is not None else None,
        evidence_id=existing_evidence.id if existing_evidence is not None else None,
        dead_letter_id=dead.id,
        outbox_event_id=outbox.id,
        receipt_status=receipt.status,
    )


def _upsert_event(session: Session, record: SourceRecord, parsed: ParsedIngest, at: datetime) -> CanonicalEvent:
    document = parsed.event
    row = _event_for(session, record)
    if row is None:
        row = CanonicalEvent(
            id=new_uuid(),
            tenant_id=record.tenant_id,
            source_record_id=record.id,
            projection_generation=0,
            created_at=at,
            updated_at=at,
            event_time=from_epoch_ms(document.time),
            category_uid=document.category_uid,
            category_name=document.category_name,
            class_uid=document.class_uid,
            class_name=document.class_name,
            activity_id=document.activity_id,
            activity_name=document.activity_name,
            type_uid=document.type_uid,
            severity=Severity(document.severity),
            outcome=Outcome(document.status),
            hostname=None,
            username=None,
            message=document.message,
            technique_ids=[],
            schema_version=OCSF_VERSION,
            normalizer_version=NORMALIZER_VERSION,
            document={},
        )
        session.add(row)
    row.projection_generation += 1
    document.metadata.uid = str(row.id)
    document.metadata.logged_time = _epoch_ms(record.received_at)
    document.soc.source_record_id = record.id
    document.soc.content_sha256 = record.content_sha256
    document.soc.source_kind = record.source_kind.value
    document.soc.normalizer_version = NORMALIZER_VERSION
    row.event_time = from_epoch_ms(document.time)
    row.category_uid = document.category_uid
    row.category_name = document.category_name
    row.class_uid = document.class_uid
    row.class_name = document.class_name
    row.activity_id = document.activity_id
    row.activity_name = document.activity_name
    row.type_uid = document.type_uid
    row.severity = Severity(document.severity)
    row.outcome = Outcome(document.status)
    row.hostname = clip(document.device.hostname if document.device is not None else None, 255)
    row.username = clip(qualified_user(document.user), 255)
    row.message = document.message
    row.technique_ids = [attack.technique.uid for attack in document.attacks if attack.technique is not None]
    row.schema_version = OCSF_VERSION
    row.normalizer_version = NORMALIZER_VERSION
    row.document = document.model_dump(mode="json")
    row.updated_at = at
    return row


def _upsert_alert(
    session: Session,
    record: SourceRecord,
    draft: AlertDraft,
    event_row: CanonicalEvent,
    at: datetime,
) -> Alert:
    row = _alert_for(session, record)
    if row is None:
        row = Alert(
            id=new_uuid(),
            tenant_id=record.tenant_id,
            source_record_id=record.id,
            canonical_event_id=event_row.id,
            source_kind=record.source_kind,
            external_id=draft.external_id,
            title=draft.title,
            description=draft.description,
            severity=Severity(draft.severity),
            status=AlertStatus.NEW,
            rule_id=draft.rule_id,
            rule_name=draft.rule_name,
            vendor=draft.vendor,
            product=draft.product,
            technique_ids=list(draft.technique_ids),
            tactics=list(draft.tactics),
            dedup_key=record.content_sha256,
            correlation_key=draft.correlation_key,
            detected_at=draft.detected_at,
            projection_generation=0,
            created_at=at,
            updated_at=at,
        )
        session.add(row)
    row.projection_generation += 1
    row.canonical_event_id = event_row.id
    row.external_id = draft.external_id
    row.title = draft.title
    row.description = draft.description
    row.severity = Severity(draft.severity)
    row.rule_id = draft.rule_id
    row.rule_name = draft.rule_name
    row.vendor = draft.vendor
    row.product = draft.product
    row.technique_ids = list(draft.technique_ids)
    row.tactics = list(draft.tactics)
    row.correlation_key = draft.correlation_key
    row.detected_at = draft.detected_at
    row.updated_at = at
    return row


def _ensure_evidence(session: Session, record: SourceRecord, at: datetime) -> Evidence:
    existing = _evidence_for(session, record)
    if existing is not None:
        return existing
    row = Evidence(
        id=new_uuid(),
        tenant_id=record.tenant_id,
        source_record_id=record.id,
        evidence_type=EvidenceType.RAW_PAYLOAD,
        description=f"Raw {record.source_kind.value} intake",
        content_sha256=record.content_sha256,
        collected_at=record.received_at,
        collected_by="ingest",
        created_at=at,
    )
    session.add(row)
    return row


def _ensure_link(
    session: Session,
    record: SourceRecord,
    evidence: Evidence,
    *,
    alert_id: UUID | None,
    canonical_event_id: UUID | None,
    at: datetime,
) -> EvidenceLink:
    existing = session.scalar(
        select(EvidenceLink).where(
            EvidenceLink.tenant_id == record.tenant_id,
            EvidenceLink.evidence_id == evidence.id,
            _id_match(EvidenceLink.alert_id, alert_id),
            _id_match(EvidenceLink.canonical_event_id, canonical_event_id),
            EvidenceLink.finding_id.is_(None),
            EvidenceLink.investigation_id.is_(None),
            EvidenceLink.case_id.is_(None),
        )
    )
    if existing is not None:
        return existing
    row = EvidenceLink(
        id=new_uuid(),
        tenant_id=record.tenant_id,
        evidence_id=evidence.id,
        alert_id=alert_id,
        canonical_event_id=canonical_event_id,
        finding_id=None,
        investigation_id=None,
        case_id=None,
        linked_by="ingest",
        linked_at=at,
    )
    session.add(row)
    return row


def _touch_receipt(
    session: Session,
    record: SourceRecord,
    *,
    at: datetime,
    status: ReceiptStatus,
    error_code: str | None,
    error_message: str | None,
    projected: bool,
) -> IngestReceipt:
    row = session.get(IngestReceipt, record.id)
    if row is None:
        row = IngestReceipt(
            source_record_id=record.id,
            tenant_id=record.tenant_id,
            status=status,
            normalizer_version=NORMALIZER_VERSION,
            attempt_count=0,
            error_code=None,
            error_message=None,
            projected_at=None,
            created_at=at,
            updated_at=at,
        )
        session.add(row)
    row.attempt_count += 1
    row.status = status
    row.normalizer_version = NORMALIZER_VERSION
    row.error_code = error_code
    row.error_message = error_message
    if projected:
        row.projected_at = at
    row.updated_at = at
    return row


def _resolve_dead_letters(session: Session, record: SourceRecord, at: datetime) -> None:
    session.execute(
        update(DeadLetter)
        .where(
            DeadLetter.tenant_id == record.tenant_id,
            DeadLetter.source_record_id == record.id,
            DeadLetter.resolved_at.is_(None),
        )
        .values(resolved_at=at)
    )


def _add_outbox(
    session: Session,
    record: SourceRecord,
    *,
    at: datetime,
    event_type: str,
    canonical_event_id: UUID | None,
    alert_id: UUID | None,
    evidence_id: UUID | None,
    dead_letter_id: UUID | None,
) -> OutboxEvent:
    row = OutboxEvent(
        id=new_uuid(),
        tenant_id=record.tenant_id,
        aggregate_type="source_record",
        aggregate_id=record.id,
        event_type=event_type,
        payload={
            "source_record_id": str(record.id),
            "source_kind": record.source_kind.value,
            "content_sha256": record.content_sha256,
            "canonical_event_id": _uuid_or_none(canonical_event_id),
            "alert_id": _uuid_or_none(alert_id),
            "evidence_id": _uuid_or_none(evidence_id),
            "dead_letter_id": _uuid_or_none(dead_letter_id),
        },
        status=OutboxStatus.PENDING,
        attempts=0,
        available_at=at,
        last_error=None,
        redis_message_id=None,
        created_at=at,
        published_at=None,
    )
    session.add(row)
    return row


def _result_from_existing(session: Session, record: SourceRecord, *, duplicate: bool) -> IngestResult:
    event_row = _event_for(session, record)
    alert_row = _alert_for(session, record)
    evidence = _evidence_for(session, record)
    receipt = session.get(IngestReceipt, record.id)
    dead = session.scalar(
        select(DeadLetter)
        .where(
            DeadLetter.tenant_id == record.tenant_id,
            DeadLetter.source_record_id == record.id,
            DeadLetter.resolved_at.is_(None),
        )
        .order_by(DeadLetter.created_at.desc())
    )
    outbox = session.scalar(
        select(OutboxEvent)
        .where(OutboxEvent.tenant_id == record.tenant_id, OutboxEvent.aggregate_id == record.id)
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
    )
    status = receipt.status if receipt is not None else ReceiptStatus.DEAD_LETTERED
    return IngestResult(
        tenant_id=record.tenant_id,
        source_record_id=record.id,
        source_kind=record.source_kind,
        content_sha256=record.content_sha256,
        duplicate=duplicate,
        canonical_event_id=event_row.id if event_row is not None else None,
        alert_id=alert_row.id if alert_row is not None else None,
        evidence_id=evidence.id if evidence is not None else None,
        dead_letter_id=dead.id if dead is not None else None,
        outbox_event_id=outbox.id if outbox is not None else None,
        receipt_status=status,
    )


def _event_for(session: Session, record: SourceRecord) -> CanonicalEvent | None:
    return session.scalar(
        select(CanonicalEvent).where(
            CanonicalEvent.tenant_id == record.tenant_id,
            CanonicalEvent.source_record_id == record.id,
        )
    )


def _alert_for(session: Session, record: SourceRecord) -> Alert | None:
    return session.scalar(
        select(Alert).where(Alert.tenant_id == record.tenant_id, Alert.source_record_id == record.id)
    )


def _evidence_for(session: Session, record: SourceRecord) -> Evidence | None:
    return session.scalar(
        select(Evidence).where(Evidence.tenant_id == record.tenant_id, Evidence.source_record_id == record.id)
    )


def _id_match(column, value: UUID | None):
    if value is None:
        return column.is_(None)
    return column == value


def _uuid_or_none(value: UUID | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _epoch_ms(value: datetime) -> int:
    from soc_platform.domain.canonical import to_epoch_ms

    return to_epoch_ms(value)


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    if diag is None:
        return None
    return getattr(diag, "constraint_name", None)


def _log_result(record: SourceRecord, *, duplicate: bool, dead_lettered: bool) -> None:
    logger.info(
        "intake tenant_id=%s source_kind=%s source_record_id=%s sha256=%s duplicate=%s dead_lettered=%s",
        record.tenant_id,
        record.source_kind.value if isinstance(record.source_kind, enum.Enum) else record.source_kind,
        record.id,
        record.content_sha256,
        duplicate,
        dead_lettered,
    )
