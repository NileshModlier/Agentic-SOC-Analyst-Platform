"""Phase 5 reads used by the security operations console."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from soc_platform.config import Settings
from soc_platform.ingestion.pipeline import ingest
from soc_platform.main import create_app
from tests.test_parsers import SIGMA

pytestmark = pytest.mark.integration


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


def test_console_reads_list_workspace_entities_and_intake(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    session.commit()
    tenant_id = str(tenant.id)

    created = client.post(
        "/api/v1/agent/runs",
        params={"tenant": tenant_id},
        json={"alert_id": str(result.alert_id), "requested_by": "Analyst"},
    )
    assert created.status_code == 201, created.text
    draft_id = created.json()["draft"]["id"]

    runs = client.get("/api/v1/agent/runs", params={"tenant": tenant_id, "draft_status": "pending_approval"})
    assert runs.status_code == 200, runs.text
    assert runs.json()["data"][0]["draft_id"] == draft_id

    drafts = client.get("/api/v1/agent/drafts", params={"tenant": tenant_id, "status": "pending_approval"})
    assert drafts.status_code == 200, drafts.text
    assert drafts.json()["data"][0]["source_of_truth"] is False

    entities = client.get("/api/v1/search/entities", params={"tenant": tenant_id, "entity_type": "host", "limit": 5})
    assert entities.status_code == 200, entities.text
    entity_id = entities.json()["data"][0]["id"]
    entity = client.get(f"/api/v1/search/entities/{entity_id}", params={"tenant": tenant_id})
    assert entity.status_code == 200, entity.text
    assert entity.json()["entity_type"] == "host"

    connectors = client.get("/api/v1/operations/connectors", params={"tenant": tenant_id})
    assert connectors.status_code == 200, connectors.text
    sigma = next(item for item in connectors.json()["data"] if item["source"] == "sigma_alert")
    assert sigma["projected"] >= 1

    letters = client.get("/api/v1/operations/dead-letters", params={"tenant": tenant_id})
    assert letters.status_code == 200, letters.text
    publications = client.get("/api/v1/operations/publications", params={"tenant": tenant_id})
    assert publications.status_code == 200, publications.text
    assert publications.json()["data"]
    assert "payload" not in publications.json()["data"][0]
