"""Phase 4 investigation workflow against PostgreSQL."""

from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from soc_platform.agents.citations import propose, validate_proposal
from soc_platform.agents.tools import ToolRegistry
from soc_platform.agents.workflow import start_run
from soc_platform.api.reader import bind_agent, bind_reader
from soc_platform.config import Settings
from soc_platform.domain.enums import DraftStatus
from soc_platform.ingestion.pipeline import ingest
from soc_platform.main import create_app
from soc_platform.models import Alert, Finding
from tests.test_parsers import SIGMA

pytestmark = pytest.mark.integration


class _BrokenTools(ToolRegistry):
    def call(self, name: str, **arguments):
        if name == "get_alert":
            raise RuntimeError("disk")
        return super().call(name, **arguments)


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

    def make_tenant():
        tenant = tenant_factory(session)
        created.append(tenant.id)
        return tenant

    try:
        yield session, make_tenant
    finally:
        session.rollback()
        session.close()
        from tests.test_api import _purge_tenant

        for tenant_id in created:
            _purge_tenant(engine, tenant_id)


def test_workflow_drafts_cited_claims_and_requires_a_person(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    other = make_tenant()
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    tenant_id = str(tenant.id)
    other_id = str(other.id)
    alert_id = str(result.alert_id)
    session.commit()

    created = client.post(
        "/api/v1/agent/runs",
        params={"tenant": tenant_id},
        json={"alert_id": alert_id, "requested_by": "alex"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "completed"
    assert body["draft"]["source_of_truth"] is False
    assert body["draft"]["status"] == "pending_approval"
    assert body["draft"]["approval"] is None
    statements = " ".join(claim["statement"] for claim in body["draft"]["claims"])
    assert "Suspicious Encoded PowerShell" in statements
    assert "T1059.001" in statements
    assert all(claim["citations"] for claim in body["draft"]["claims"])
    kinds = {citation["kind"] for claim in body["draft"]["claims"] for citation in claim["citations"]}
    assert {"alert", "event", "entity", "evidence"} <= kinds
    agents = {item["agent"] for item in body["memory"]}
    assert {"supervisor", "triage", "entity", "threat", "reporting"} <= agents
    assert _ok(client.get("/api/v1/findings", params={"tenant": tenant_id}))["data"] == []
    alert = _ok(client.get(f"/api/v1/alerts/{alert_id}", params={"tenant": tenant_id}))
    assert alert["status"] == "new"

    hidden = client.get(f"/api/v1/agent/runs/{body['id']}", params={"tenant": other_id})
    assert hidden.status_code == 404
    agent_actor = client.post(
        f"/api/v1/agent/drafts/{body['draft']['id']}/decisions",
        params={"tenant": tenant_id},
        json={"decision": "approved", "actor": "triage"},
    )
    assert agent_actor.status_code == 422

    approved = client.post(
        f"/api/v1/agent/drafts/{body['draft']['id']}/decisions",
        params={"tenant": tenant_id},
        json={"decision": "approved", "actor": "alex", "note": "Matches the stored alert."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["source_of_truth"] is False
    assert approved.json()["approval"]["actor"] == "alex"
    again = client.post(
        f"/api/v1/agent/drafts/{body['draft']['id']}/decisions",
        params={"tenant": tenant_id},
        json={"decision": "rejected", "actor": "alex"},
    )
    assert again.status_code == 409
    assert _ok(client.get("/api/v1/findings", params={"tenant": tenant_id}))["data"] == []
    assert _ok(client.get(f"/api/v1/alerts/{alert_id}", params={"tenant": tenant_id}))["status"] == "new"

    missing = client.post(
        "/api/v1/agent/runs",
        params={"tenant": tenant_id},
        json={"alert_id": str(uuid4()), "requested_by": "alex"},
    )
    assert missing.status_code == 201, missing.text
    assert missing.json()["status"] == "failed"
    assert missing.json()["error_code"] == "alert_not_found"
    assert missing.json()["draft"] is None

    empty = client.post(
        "/api/v1/agent/runs",
        params={"tenant": tenant_id},
        json={"question": "zzzz-no-such-record", "requested_by": "alex"},
    )
    assert empty.status_code == 201, empty.text
    assert empty.json()["draft"]["status"] == "insufficient_evidence"
    refused = client.post(
        f"/api/v1/agent/drafts/{empty.json()['draft']['id']}/decisions",
        params={"tenant": tenant_id},
        json={"decision": "approved", "actor": "alex"},
    )
    assert refused.status_code == 409

    networked = client.post(
        "/api/v1/agent/runs",
        params={"tenant": tenant_id},
        json={"question": "https://example.test/intel", "requested_by": "alex"},
    )
    assert networked.status_code == 422
    assert networked.json()["error"]["code"] == "network_denied"
    posted = client.post("/api/v1/events", params={"tenant": tenant_id})
    assert posted.status_code == 405

    bind_agent(session, tenant.id)
    mismatch = validate_proposal(
        session,
        tenant.id,
        propose("alert.summary", "alert", result.alert_id, {"title": "forged", "severity": "high", "status": "new"}),
    )
    assert mismatch.reason == "stored_value_mismatch"
    missing_record = validate_proposal(
        session,
        tenant.id,
        propose("alert.summary", "alert", uuid4(), {"title": "x", "severity": "high", "status": "new"}),
    )
    assert missing_record.reason == "record_not_found"
    with pytest.raises(DBAPIError) as denied:
        with session.begin_nested():
            session.execute(text("UPDATE alerts SET title = 'changed'"))
    assert getattr(denied.value.orig, "sqlstate", None) == "42501"
    session.rollback()

    bind_reader(session, tenant.id)
    with pytest.raises(DBAPIError) as reader_denied:
        with session.begin_nested():
            session.execute(
                text(
                    "INSERT INTO investigation_drafts (id, tenant_id, run_id, status, title, summary, severity, source_of_truth, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :tenant, gen_random_uuid(), 'pending_approval', 'x', 'y', 'high', false, now(), now())"
                ),
                {"tenant": tenant.id},
            )
    assert getattr(reader_denied.value.orig, "sqlstate", None) == "42501"
    assert session.scalar(select(func.count()).select_from(Finding).where(Finding.tenant_id == tenant.id)) == 0
    assert session.scalar(select(Alert.status).where(Alert.id == result.alert_id)) == "new"


def test_tool_failure_does_not_approve_a_draft(database) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    session.commit()
    bind_agent(session, tenant.id)
    run = start_run(
        session,
        tenant_id=tenant.id,
        requested_by="alex",
        alert_id=result.alert_id,
        cursor_secret="test-cursor-secret",
        tools=_BrokenTools(),
    )
    session.commit()
    assert run.status.value == "failed"
    assert run.error_code == "agent_failed"
    assert run.error_message == "triage failed"
    assert "disk" not in (run.error_message or "")
    bind_reader(session, tenant.id)
    from soc_platform.models.agent import InvestigationDraft

    drafts = session.scalar(
        select(func.count()).select_from(InvestigationDraft).where(InvestigationDraft.tenant_id == tenant.id)
    )
    assert drafts == 0
    assert session.scalar(select(Alert.status).where(Alert.id == result.alert_id)) == "new"
    assert DraftStatus.APPROVED.value == "approved"


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()
