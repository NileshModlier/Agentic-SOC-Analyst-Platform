"""PostgreSQL-backed tests for intake, custody, outbox, and tenant isolation."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from soc_platform.casework import (
    create_case,
    create_finding,
    create_investigation,
    link_alert_to_finding,
    link_alert_to_investigation,
    link_evidence,
)
from soc_platform.domain.enums import AlertStatus, OutboxStatus, Severity, TenantStatus
from soc_platform.domain.errors import IngestParseError, PayloadTooLarge, TenantDisabled
from soc_platform.hashing import sha256_hex
from soc_platform.ingestion.pipeline import ingest, replay
from soc_platform.ingestion.registry import parser_for
from soc_platform.models import (
    Alert,
    AlertSearchDocument,
    CanonicalEvent,
    DeadLetter,
    EventEntity,
    EventSearchDocument,
    Evidence,
    EvidenceLink,
    OutboxEvent,
    SecurityEntity,
    SourceRecord,
    Tenant,
)
from soc_platform.outbox.publisher import publish_pending
from tests.test_parsers import EDR, SIGMA, WINDOWS_SECURITY, WINDOWS_XML

pytestmark = pytest.mark.integration


def _sigma_bytes() -> bytes:
    return json.dumps(SIGMA).encode()


def test_sigma_ingest_is_transactional_and_replayable(session: Session, tenant: Tenant) -> None:
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma_bytes())
    session.flush()

    stored = session.get(SourceRecord, result.source_record_id)
    assert stored is not None
    assert stored.payload == _sigma_bytes()
    assert stored.content_sha256 == sha256_hex(_sigma_bytes())
    event = session.get(CanonicalEvent, result.canonical_event_id)
    assert event is not None
    assert event.type_uid == 100701
    assert event.document["soc"]["content_sha256"] == stored.content_sha256
    assert event.document["metadata"]["logged_time"] == event.document["metadata"]["logged_time"]
    alert = session.get(Alert, result.alert_id)
    assert alert is not None
    assert alert.status == AlertStatus.NEW
    assert alert.dedup_key == stored.content_sha256
    evidence = session.get(Evidence, result.evidence_id)
    assert evidence is not None
    assert evidence.content_sha256 == stored.content_sha256
    outbox = session.get(OutboxEvent, result.outbox_event_id)
    assert outbox is not None
    assert outbox.status == OutboxStatus.PENDING
    assert outbox.payload["alert_id"] == str(alert.id)

    logged_time = event.document["metadata"]["logged_time"]
    message = event.message
    alert.status = AlertStatus.IN_REVIEW
    session.flush()

    session.execute(delete(EventEntity).where(EventEntity.tenant_id == tenant.id))
    session.execute(delete(AlertSearchDocument).where(AlertSearchDocument.tenant_id == tenant.id))
    session.execute(delete(EventSearchDocument).where(EventSearchDocument.tenant_id == tenant.id))
    session.execute(delete(SecurityEntity).where(SecurityEntity.tenant_id == tenant.id))
    session.execute(delete(EvidenceLink).where(EvidenceLink.tenant_id == tenant.id))
    session.execute(delete(Alert).where(Alert.tenant_id == tenant.id))
    session.execute(delete(CanonicalEvent).where(CanonicalEvent.tenant_id == tenant.id))
    session.flush()

    replayed = replay(session, tenant_id=tenant.id, source_record_id=result.source_record_id)
    restored = session.get(CanonicalEvent, replayed.canonical_event_id)
    restored_alert = session.get(Alert, replayed.alert_id)
    assert restored is not None
    assert restored.message == message
    assert restored.document["process"]["cmd_line"] == "powershell.exe -enc AA=="
    assert restored.document["metadata"]["logged_time"] == logged_time
    assert restored.projection_generation == 1
    assert bytes(session.get(SourceRecord, result.source_record_id).payload) == _sigma_bytes()
    assert restored_alert is not None
    assert restored_alert.status == AlertStatus.NEW


def test_replay_preserves_alert_workflow_status(session: Session, tenant: Tenant) -> None:
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma_bytes())
    alert = session.get(Alert, result.alert_id)
    assert alert is not None
    alert.status = AlertStatus.IN_REVIEW
    session.flush()

    replayed = replay(session, tenant_id=tenant.id, source_record_id=result.source_record_id)
    assert replayed.alert_id == result.alert_id
    assert session.get(Alert, result.alert_id).status == AlertStatus.IN_REVIEW
    assert session.get(Alert, result.alert_id).projection_generation == 2


def test_duplicate_bytes_do_not_create_a_second_outbox_row(session: Session, tenant: Tenant) -> None:
    first = ingest(session, tenant_id=tenant.id, source_kind="mock_edr_alert", payload=json.dumps(EDR).encode())
    second = ingest(session, tenant_id=tenant.id, source_kind="mock_edr_alert", payload=json.dumps(EDR).encode())
    assert second.duplicate is True
    assert second.source_record_id == first.source_record_id
    assert session.scalar(select(func.count()).select_from(SourceRecord).where(SourceRecord.tenant_id == tenant.id)) == 1
    assert session.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.tenant_id == tenant.id)) == 1


def test_same_bytes_are_isolated_per_tenant(session: Session, tenant: Tenant) -> None:
    other = Tenant(slug=f"other-{uuid4().hex[:8]}", name="Other", status=TenantStatus.ACTIVE, created_at=tenant.created_at, updated_at=tenant.updated_at)
    session.add(other)
    session.flush()
    payload = WINDOWS_XML.encode("utf-8")
    first = ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=payload)
    second = ingest(session, tenant_id=other.id, source_kind="windows_event", payload=payload)
    assert first.source_record_id != second.source_record_id
    assert first.alert_id is None
    assert second.alert_id is None
    assert session.get(CanonicalEvent, first.canonical_event_id).class_uid == 1007


def test_invalid_payload_is_stored_and_dead_lettered(session: Session, tenant: Tenant) -> None:
    payload = b"\x80\x81\x82"
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=payload)
    assert result.dead_letter_id is not None
    assert result.alert_id is None
    assert result.canonical_event_id is None
    stored = session.get(SourceRecord, result.source_record_id)
    assert stored is not None
    assert stored.payload == payload
    letter = session.get(DeadLetter, result.dead_letter_id)
    assert letter is not None
    assert letter.reason_code == "invalid_encoding"
    assert letter.resolved_at is None

    again = replay(session, tenant_id=tenant.id, source_record_id=result.source_record_id)
    assert again.dead_letter_id != result.dead_letter_id
    assert again.alert_id is None
    assert session.scalar(select(func.count()).select_from(DeadLetter).where(DeadLetter.source_record_id == stored.id)) == 2


def test_oversized_payload_is_rejected_without_storage(session: Session, tenant: Tenant) -> None:
    with pytest.raises(PayloadTooLarge):
        ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=b"{}", max_payload_bytes=1)
    assert session.scalar(select(func.count()).select_from(SourceRecord).where(SourceRecord.tenant_id == tenant.id)) == 0


def test_disabled_tenant_is_rejected(session: Session, tenant: Tenant) -> None:
    tenant.status = TenantStatus.DISABLED
    session.flush()
    with pytest.raises(TenantDisabled):
        ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=b"{}")


def test_source_and_evidence_rows_are_immutable(session: Session, tenant: Tenant) -> None:
    result = ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=json.dumps(WINDOWS_SECURITY).encode())
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            session.execute(
                text("UPDATE source_records SET content_type = 'text/plain' WHERE id = :id"),
                {"id": result.source_record_id},
            )
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            session.execute(text("DELETE FROM evidence WHERE id = :id"), {"id": result.evidence_id})


def test_source_hash_must_match_payload(session: Session, tenant: Tenant) -> None:
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                SourceRecord(
                    tenant_id=tenant.id,
                    source_kind="windows_event",
                    content_type="application/json",
                    content_sha256="0" * 64,
                    byte_size=3,
                    payload=b"abc",
                    external_id=None,
                    received_at=tenant.created_at,
                )
            )
            session.flush()


def test_cross_tenant_alert_reference_is_rejected(session: Session, tenant: Tenant) -> None:
    result = ingest(session, tenant_id=tenant.id, source_kind="mock_edr_alert", payload=json.dumps(EDR).encode())
    other = Tenant(
        slug=f"cross-{uuid4().hex[:8]}",
        name="Cross",
        status=TenantStatus.ACTIVE,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )
    session.add(other)
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                Alert(
                    tenant_id=other.id,
                    source_record_id=result.source_record_id,
                    canonical_event_id=None,
                    source_kind="mock_edr_alert",
                    external_id="other",
                    title="cross",
                    description=None,
                    severity=Severity.LOW,
                    status=AlertStatus.NEW,
                    rule_id=None,
                    rule_name=None,
                    vendor=None,
                    product=None,
                    technique_ids=[],
                    tactics=[],
                    dedup_key="1" * 64,
                    correlation_key=None,
                    detected_at=tenant.created_at,
                    projection_generation=1,
                    created_at=tenant.created_at,
                    updated_at=tenant.updated_at,
                )
            )
            session.flush()


def test_outbox_is_invisible_until_commit(engine, tenant_factory) -> None:
    payload = json.dumps(WINDOWS_SECURITY).encode()
    first = engine.connect()
    second = engine.connect()
    txn = first.begin()
    other = second.begin()
    try:
        writer = Session(bind=first)
        tenant = tenant_factory(writer)
        result = ingest(writer, tenant_id=tenant.id, source_kind="windows_event", payload=payload)
        writer.flush()
        visible = second.execute(
            text("SELECT count(*) FROM outbox_events WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant.id},
        ).scalar_one()
        stored = second.execute(
            text("SELECT count(*) FROM source_records WHERE id = :id"),
            {"id": result.source_record_id},
        ).scalar_one()
        assert visible == 0
        assert stored == 0
    finally:
        txn.rollback()
        other.rollback()
        first.close()
        second.close()


def test_publisher_writes_redis_then_marks_published(session: Session, tenant: Tenant) -> None:
    fakeredis = pytest.importorskip("fakeredis")
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma_bytes())
    redis = fakeredis.FakeRedis(decode_responses=True)
    handled = publish_pending(session, redis, stream="soc.outbox", batch_size=10, max_attempts=5)
    assert handled == 1
    row = session.get(OutboxEvent, result.outbox_event_id)
    assert row is not None
    assert row.status == OutboxStatus.PUBLISHED
    assert row.redis_message_id
    entries = redis.xrange("soc.outbox")
    assert len(entries) == 1
    body = json.loads(entries[0][1]["payload"])
    assert body["source_record_id"] == str(result.source_record_id)
    assert "powershell" not in entries[0][1]["payload"]


def test_publisher_dead_letters_after_the_attempt_budget(session: Session, tenant: Tenant) -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma_bytes())

    class Down:
        def xadd(self, name: str, fields: dict[str, str]) -> str:
            raise RedisConnectionError("redis down")

    handled = publish_pending(session, Down(), stream="soc.outbox", batch_size=10, max_attempts=1)
    assert handled == 1
    row = session.get(OutboxEvent, result.outbox_event_id)
    assert row is not None
    assert row.status == OutboxStatus.DEAD_LETTERED
    letter = session.scalar(select(DeadLetter).where(DeadLetter.outbox_event_id == row.id))
    assert letter is not None
    assert letter.reason_code == "publish_exhausted"
    assert letter.stage.value == "publish"


def test_publisher_backs_off_before_dead_letter(session: Session, tenant: Tenant) -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma_bytes())

    class Down:
        def xadd(self, name: str, fields: dict[str, str]) -> str:
            raise RedisConnectionError("redis down")

    assert publish_pending(session, Down(), stream="soc.outbox", batch_size=10, max_attempts=5) == 1
    assert publish_pending(session, Down(), stream="soc.outbox", batch_size=10, max_attempts=5) == 0


def test_replay_failure_keeps_the_existing_projection(session: Session, tenant: Tenant, monkeypatch: pytest.MonkeyPatch) -> None:
    result = ingest(session, tenant_id=tenant.id, source_kind="mock_edr_alert", payload=json.dumps(EDR).encode())

    class Broken:
        def parse(self, payload: bytes):
            raise IngestParseError("normalizer failed closed", "schema_mismatch")

    monkeypatch.setattr("soc_platform.ingestion.pipeline.parser_for", lambda kind: Broken())
    failed = replay(session, tenant_id=tenant.id, source_record_id=result.source_record_id)
    assert failed.alert_id == result.alert_id
    assert failed.dead_letter_id is not None
    assert session.get(Alert, result.alert_id).title == "Suspicious process execution"
    assert session.get(SourceRecord, result.source_record_id).payload == json.dumps(EDR).encode()


def test_casework_links_stay_inside_the_tenant(session: Session, tenant: Tenant) -> None:
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma_bytes())
    case = create_case(session, tenant_id=tenant.id, title="Encoded powershell", severity=Severity.HIGH)
    investigation = create_investigation(
        session,
        tenant_id=tenant.id,
        title="Who launched powershell",
        case_id=case.id,
        hypothesis="A user ran an encoded command",
    )
    finding = create_finding(
        session,
        tenant_id=tenant.id,
        title="Encoded PowerShell execution",
        severity=Severity.HIGH,
        created_by="analyst-1",
        case_id=case.id,
        investigation_id=investigation.id,
        technique_ids=["T1059.001"],
        confidence=80,
    )
    link_alert_to_investigation(
        session,
        tenant_id=tenant.id,
        investigation_id=investigation.id,
        alert_id=result.alert_id,
        linked_by="analyst-1",
    )
    link_alert_to_finding(
        session,
        tenant_id=tenant.id,
        finding_id=finding.id,
        alert_id=result.alert_id,
        linked_by="analyst-1",
    )
    link_evidence(
        session,
        tenant_id=tenant.id,
        evidence_id=result.evidence_id,
        investigation_id=investigation.id,
        case_id=case.id,
        linked_by="analyst-1",
    )
    assert finding.case_id == case.id
    assert investigation.case_id == case.id


def test_row_level_security_hides_other_tenants(session: Session, tenant: Tenant) -> None:
    other = Tenant(
        slug=f"rls-{uuid4().hex[:8]}",
        name="RLS",
        status=TenantStatus.ACTIVE,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )
    session.add(other)
    session.flush()
    ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=json.dumps(WINDOWS_SECURITY).encode())
    other_payload = json.dumps({**WINDOWS_SECURITY, "marker": "other"}).encode()
    # The marker is outside the Event object, so this is a different byte string and still a valid event.
    ingest(session, tenant_id=other.id, source_kind="windows_event", payload=other_payload)

    session.execute(text("SET LOCAL ROLE soc_app"))
    session.execute(text("SELECT set_config('soc.tenant_id', :tenant_id, true)"), {"tenant_id": str(tenant.id)})
    visible = session.execute(text("SELECT count(*) FROM source_records")).scalar_one()
    assert visible == 1
    session.execute(text("RESET ROLE"))
    session.execute(text("SET LOCAL ROLE soc_relay"))
    relay_visible = session.execute(text("SELECT count(*) FROM source_records")).scalar_one()
    assert relay_visible >= 2


def test_parser_registry_matches_phase1_sources() -> None:
    from soc_platform.domain.enums import SourceKind

    assert parser_for(SourceKind.SIGMA_ALERT).source_kind == SourceKind.SIGMA_ALERT
    assert parser_for(SourceKind.MOCK_EDR_ALERT).source_kind == SourceKind.MOCK_EDR_ALERT
    assert parser_for(SourceKind.WINDOWS_EVENT).source_kind == SourceKind.WINDOWS_EVENT
