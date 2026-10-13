"""Phase 2 read API against PostgreSQL."""

from __future__ import annotations

import copy
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from soc_platform.api.reader import READER_ROLE, bind_reader
from soc_platform.casework import (
    create_case,
    create_finding,
    create_investigation,
    link_alert_to_finding,
    link_alert_to_investigation,
    link_evidence,
)
from soc_platform.config import Settings
from soc_platform.domain.enums import AlertStatus, CaseStatus, InvestigationStatus, Severity, TenantStatus
from soc_platform.ingestion.pipeline import ingest
from soc_platform.main import create_app
from soc_platform.models import Alert, Tenant
from tests.test_parsers import EDR, SIGMA, WINDOWS_SECURITY

pytestmark = pytest.mark.integration

_PURGE_TABLES = (
    "draft_approvals",
    "draft_citations",
    "draft_claims",
    "investigation_drafts",
    "agent_memories",
    "agent_runs",
    "event_entities",
    "alert_search_documents",
    "event_search_documents",
    "security_entities",
    "investigation_alerts",
    "finding_alerts",
    "evidence_links",
    "alerts",
    "findings",
    "investigations",
    "canonical_events",
    "evidence",
    "ingest_receipts",
    "dead_letters",
    "outbox_events",
    "source_records",
    "security_cases",
    "tenants",
)


@pytest.fixture
def client(engine):
    app = create_app(
        Settings(
            database_url=os.environ["SOC_DATABASE_URL"],
            redis_url="redis://localhost:6379/0",
            api_cursor_secret="test-cursor-secret",
        )
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def database(engine, tenant_factory):
    session = Session(bind=engine)
    created: list = []

    def make_tenant() -> Tenant:
        tenant = tenant_factory(session)
        created.append(tenant.id)
        return tenant

    try:
        yield session, make_tenant
    finally:
        session.rollback()
        session.close()
        for tenant_id in created:
            _purge_tenant(engine, tenant_id)


def test_reader_role_is_select_only_and_tenant_scoped(session: Session, tenant: Tenant, tenant_factory) -> None:
    other = tenant_factory(session)
    ingest(
        session,
        tenant_id=tenant.id,
        source_kind="windows_event",
        payload=_windows(1, "2026-10-06T12:00:01.0000000Z"),
    )
    ingest(
        session,
        tenant_id=other.id,
        source_kind="windows_event",
        payload=_windows(2, "2026-10-06T12:00:02.0000000Z"),
    )

    session.execute(text("SET LOCAL ROLE soc_reader"))
    assert session.scalar(text("SELECT count(*) FROM canonical_events")) == 0
    session.execute(text("RESET ROLE"))

    bind_reader(session, tenant.id)
    assert session.scalar(text("SELECT current_user")) == READER_ROLE
    assert session.scalar(text("SELECT count(*) FROM canonical_events")) == 1
    assert session.scalar(text("SELECT count(*) FROM tenants")) == 1
    assert session.scalar(text("SELECT source_kind FROM source_records")) == "windows_event"

    assert session.scalar(text("SELECT count(*) FROM outbox_events")) >= 1
    assert session.scalar(text("SELECT count(*) FROM dead_letters")) == 0
    for statement in (
        "SELECT payload FROM source_records",
        "SELECT payload FROM outbox_events",
        "SELECT payload_bytes FROM dead_letters",
        "INSERT INTO security_cases (id) VALUES (gen_random_uuid())",
    ):
        with pytest.raises(DBAPIError) as exc:
            with session.begin_nested():
                session.execute(text(statement))
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"


def test_events_filters_pagination_and_tenant_isolation(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    other = make_tenant()
    ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=_windows(1, "2026-10-06T12:00:01.0000000Z"))
    ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=_windows(2, "2026-10-06T12:00:02.0000000Z"))
    ingest(session, tenant_id=tenant.id, source_kind="windows_event", payload=_windows(3, "2026-10-06T12:00:02.0000000Z"))
    sigma = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    other_sigma = ingest(session, tenant_id=other.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    tenant_id = tenant.id
    other_id = other.id
    sigma_event_id = sigma.canonical_event_id
    other_event_id = other_sigma.canonical_event_id
    session.commit()

    listed = _ok(
        client.get(
            "/api/v1/events",
            params={"tenant": str(tenant_id), "source": "windows_event", "limit": 1},
        )
    )
    assert listed["page"]["limit"] == 1
    assert listed["page"]["has_more"] is True
    assert "document" not in listed["data"][0]
    seen = []
    cursor = None
    for _ in range(5):
        params = {"tenant": str(tenant_id), "source": "windows_event", "limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = _ok(client.get("/api/v1/events", params=params))
        assert len(page["data"]) == 1
        seen.append(page["data"][0]["id"])
        cursor = page["page"]["next_cursor"]
        if not page["page"]["has_more"]:
            break
    else:
        raise AssertionError("event pages did not end")
    assert len(seen) == 3
    assert len(set(seen)) == 3

    window = _ok(
        client.get(
            "/api/v1/events",
            params={
                "tenant": str(tenant_id),
                "source": "windows_event",
                "start": "2026-10-06T12:00:02Z",
                "end": "2026-10-06T12:00:03Z",
            },
        )
    )
    assert len(window["data"]) == 2
    assert {row["event_time"][:19] for row in window["data"]} == {"2026-10-06T12:00:02"}

    authentication = _ok(
        client.get(
            "/api/v1/events",
            params={"tenant": str(tenant_id), "event_type": "Authentication", "severity": "informational"},
        )
    )
    assert len(authentication["data"]) == 3
    assert {row["class_name"] for row in authentication["data"]} == {"Authentication"}

    sigma_events = _ok(
        client.get(
            "/api/v1/events",
            params={"tenant": str(tenant_id), "source": "sigma_alert"},
        )
    )
    assert [row["id"] for row in sigma_events["data"]] == [str(sigma_event_id)]
    assert sigma_events["data"][0]["source"] == "sigma_alert"
    # The canonical event keeps the matched activity's severity. Rule severity is on the alert.
    assert sigma_events["data"][0]["severity"] == "informational"
    high_events = _ok(
        client.get("/api/v1/events", params={"tenant": str(tenant_id), "severity": "high"})
    )
    assert high_events["data"] == []

    detail = _ok(client.get(f"/api/v1/events/{sigma_event_id}", params={"tenant": str(tenant_id)}))
    assert detail["document"]["soc"]["source_kind"] == "sigma_alert"
    assert detail["class_name"] == "Process Activity"
    hidden = client.get(f"/api/v1/events/{other_event_id}", params={"tenant": str(tenant_id)})
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "not_found"
    other_list = _ok(client.get("/api/v1/events", params={"tenant": str(other_id)}))
    assert [row["id"] for row in other_list["data"]] == [str(other_event_id)]

    stale = listed["page"]["next_cursor"]
    reused = client.get(
        "/api/v1/events",
        params={"tenant": str(tenant_id), "source": "sigma_alert", "limit": 1, "cursor": stale},
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_cursor"
    tampered = client.get(
        "/api/v1/alerts",
        params={"tenant": str(tenant_id), "cursor": stale},
    )
    assert tampered.status_code == 400


def test_casework_and_evidence_reads(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    sigma = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=_sigma("sigma-a"))
    edr = ingest(session, tenant_id=tenant.id, source_kind="mock_edr_alert", payload=json.dumps(EDR).encode())
    closed_alert = session.get(Alert, sigma.alert_id)
    assert closed_alert is not None
    closed_alert.status = AlertStatus.CLOSED
    contained = create_case(session, tenant_id=tenant.id, title="Contained incident", severity=Severity.HIGH)
    contained.status = CaseStatus.CONTAINED
    open_case = create_case(session, tenant_id=tenant.id, title="Open incident", severity=Severity.LOW)
    closed_inv = create_investigation(
        session, tenant_id=tenant.id, title="Closed lead", case_id=contained.id
    )
    closed_inv.status = InvestigationStatus.CLOSED
    open_inv = create_investigation(session, tenant_id=tenant.id, title="Open lead", case_id=contained.id)
    finding = create_finding(
        session,
        tenant_id=tenant.id,
        title="Encoded powershell",
        severity=Severity.HIGH,
        created_by="analyst-1",
        case_id=contained.id,
        investigation_id=open_inv.id,
    )
    create_finding(
        session,
        tenant_id=tenant.id,
        title="Low confidence note",
        severity=Severity.LOW,
        created_by="analyst-1",
        case_id=open_case.id,
    )
    link_alert_to_investigation(
        session,
        tenant_id=tenant.id,
        investigation_id=open_inv.id,
        alert_id=sigma.alert_id,
        linked_by="analyst-1",
    )
    link_alert_to_finding(
        session,
        tenant_id=tenant.id,
        finding_id=finding.id,
        alert_id=sigma.alert_id,
        linked_by="analyst-1",
    )
    link_evidence(
        session,
        tenant_id=tenant.id,
        evidence_id=sigma.evidence_id,
        case_id=contained.id,
        linked_by="analyst-1",
    )
    tenant_id = tenant.id
    ids = {
        "sigma_alert": sigma.alert_id,
        "edr_alert": edr.alert_id,
        "contained": contained.id,
        "open_case": open_case.id,
        "closed_inv": closed_inv.id,
        "open_inv": open_inv.id,
        "finding": finding.id,
        "evidence": sigma.evidence_id,
    }
    session.commit()

    closed = _ok(
        client.get(
            "/api/v1/alerts",
            params={"tenant": str(tenant_id), "alert_status": "closed", "severity": "high", "source": "sigma_alert"},
        )
    )
    assert [row["id"] for row in closed["data"]] == [str(ids["sigma_alert"])]
    assert closed["data"][0]["status"] == "closed"
    new_alerts = _ok(
        client.get("/api/v1/alerts", params={"tenant": str(tenant_id), "alert_status": "new", "source": "mock_edr_alert"})
    )
    assert [row["id"] for row in new_alerts["data"]] == [str(ids["edr_alert"])]
    assert new_alerts["data"][0]["severity"] == "critical"
    alert = _ok(client.get(f"/api/v1/alerts/{ids['sigma_alert']}", params={"tenant": str(tenant_id)}))
    assert alert["canonical_event_id"]

    cases = _ok(client.get("/api/v1/cases", params={"tenant": str(tenant_id), "case_status": "contained"}))
    assert [row["id"] for row in cases["data"]] == [str(ids["contained"])]
    case = _ok(client.get(f"/api/v1/cases/{ids['contained']}", params={"tenant": str(tenant_id)}))
    assert case["investigation_ids"] == [str(ids["closed_inv"]), str(ids["open_inv"])] or set(case["investigation_ids"]) == {
        str(ids["closed_inv"]),
        str(ids["open_inv"]),
    }
    assert str(ids["finding"]) in case["finding_ids"]
    assert str(ids["open_case"]) not in case["finding_ids"]

    investigations = _ok(
        client.get(
            "/api/v1/investigations",
            params={"tenant": str(tenant_id), "investigation_status": "closed"},
        )
    )
    assert [row["id"] for row in investigations["data"]] == [str(ids["closed_inv"])]
    investigation = _ok(
        client.get(f"/api/v1/investigations/{ids['open_inv']}", params={"tenant": str(tenant_id)})
    )
    assert investigation["alert_ids"] == [str(ids["sigma_alert"])]

    findings = _ok(client.get("/api/v1/findings", params={"tenant": str(tenant_id), "severity": "high"}))
    assert [row["id"] for row in findings["data"]] == [str(ids["finding"])]
    finding_body = _ok(client.get(f"/api/v1/findings/{ids['finding']}", params={"tenant": str(tenant_id)}))
    assert finding_body["alert_ids"] == [str(ids["sigma_alert"])]
    assert finding_body["case_id"] == str(ids["contained"])

    evidence = _ok(client.get("/api/v1/evidence", params={"tenant": str(tenant_id), "source": "sigma_alert"}))
    assert [row["id"] for row in evidence["data"]] == [str(ids["evidence"])]
    assert evidence["data"][0]["byte_size"] > 0
    assert "payload" not in evidence["data"][0]
    detail = _ok(client.get(f"/api/v1/evidence/{ids['evidence']}", params={"tenant": str(tenant_id)}))
    assert "powershell" not in json.dumps(detail)
    assert any(link["case_id"] == str(ids["contained"]) for link in detail["links"])
    assert any(link["canonical_event_id"] for link in detail["links"])
    future = _ok(
        client.get(
            "/api/v1/cases",
            params={"tenant": str(tenant_id), "start": "2099-01-01T00:00:00Z"},
        )
    )
    assert future["data"] == []
    assert future["page"] == {"limit": 50, "has_more": False, "next_cursor": None}


def test_request_contract(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    ingested = ingest(
        session,
        tenant_id=tenant.id,
        source_kind="windows_event",
        payload=_windows(9, "2026-10-06T12:00:01.0000000Z"),
    )
    tenant.status = TenantStatus.DISABLED
    tenant_id = tenant.id
    event_id = ingested.canonical_event_id
    session.commit()

    readable = _ok(client.get("/api/v1/events", params={"tenant": str(tenant_id)}))
    assert [row["id"] for row in readable["data"]] == [str(event_id)]
    assert readable["page"]["limit"] == 50

    missing = client.get("/api/v1/events")
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "validation_error"
    oversized = client.get("/api/v1/events", params={"tenant": str(tenant_id), "limit": 101})
    assert oversized.status_code == 422
    unknown = client.get("/api/v1/events", params={"tenant": str(tenant_id), "q": "powershell"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "invalid_filter"
    naive = client.get("/api/v1/events", params={"tenant": str(tenant_id), "start": "2026-10-06T12:00:00"})
    assert naive.status_code == 422
    backwards = client.get(
        "/api/v1/events",
        params={"tenant": str(tenant_id), "start": "2026-10-06T13:00:00Z", "end": "2026-10-06T12:00:00Z"},
    )
    assert backwards.status_code == 422
    bad_cursor = client.get("/api/v1/alerts", params={"tenant": str(tenant_id), "cursor": "not-a-cursor"})
    assert bad_cursor.status_code == 400
    posted = client.post("/api/v1/events", params={"tenant": str(tenant_id)})
    assert posted.status_code == 405
    assert posted.json()["error"]["code"] == "method_not_allowed"
    absent = client.get("/api/v1/events", params={"tenant": str(uuid4())})
    assert absent.status_code == 404
    assert absent.json()["error"]["code"] == "tenant_not_found"
    missing_event = client.get(f"/api/v1/events/{uuid4()}", params={"tenant": str(tenant_id)})
    assert missing_event.status_code == 404
    assert missing_event.json()["error"]["code"] == "not_found"


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def _windows(record_id: int, when: str) -> bytes:
    body = copy.deepcopy(WINDOWS_SECURITY)
    body["Event"]["System"]["EventRecordID"] = record_id
    body["Event"]["System"]["TimeCreated"]["SystemTime"] = when
    return json.dumps(body).encode()


def _sigma(alert_id: str) -> bytes:
    body = copy.deepcopy(SIGMA)
    body["alert_id"] = alert_id
    body["event"]["winlog"]["record_id"] = alert_id
    return json.dumps(body).encode()


def _purge_tenant(engine, tenant_id) -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE source_records DISABLE TRIGGER source_records_immutable"))
        connection.execute(text("ALTER TABLE evidence DISABLE TRIGGER evidence_immutable"))
        try:
            for table in _PURGE_TABLES:
                if table == "tenants":
                    connection.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})
                else:
                    connection.execute(text(f"DELETE FROM {table} WHERE tenant_id = :id"), {"id": tenant_id})
        finally:
            connection.execute(text("ALTER TABLE evidence ENABLE TRIGGER evidence_immutable"))
            connection.execute(text("ALTER TABLE source_records ENABLE TRIGGER source_records_immutable"))
