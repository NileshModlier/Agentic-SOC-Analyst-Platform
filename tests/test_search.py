"""Phase 3 search against PostgreSQL full text search."""

from __future__ import annotations

import copy
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from soc_platform.api.reader import bind_reader
from soc_platform.config import Settings
from soc_platform.domain.canonical import SEVERITY_IDS
from soc_platform.ingestion.pipeline import ingest, replay
from soc_platform.main import create_app
from tests.test_parsers import EDR, SIGMA, WINDOWS_SECURITY

pytestmark = pytest.mark.integration

RULE_ID = SIGMA["rule"]["id"]


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


def test_search_filters_facets_sort_and_cursor(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    other = make_tenant()
    late = ingest(
        session,
        tenant_id=tenant.id,
        source_kind="windows_event",
        payload=_windows(4624, 1, "2026-10-06T15:00:00.0000000Z"),
    )
    ingest(
        session,
        tenant_id=tenant.id,
        source_kind="windows_event",
        payload=_windows(4625, 2, "2026-10-06T12:30:00.0000000Z"),
    )
    sigma = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    edr = ingest(session, tenant_id=tenant.id, source_kind="mock_edr_alert", payload=json.dumps(EDR).encode())
    file_event = ingest(
        session,
        tenant_id=tenant.id,
        source_kind="windows_event",
        payload=_file("2026-10-06T13:00:00.0000000Z"),
    )
    early = ingest(
        session,
        tenant_id=tenant.id,
        source_kind="windows_event",
        payload=_windows(4634, 99, "2026-10-06T10:00:00.0000000Z", user="carol"),
    )
    ingest(
        session,
        tenant_id=other.id,
        source_kind="windows_event",
        payload=_windows(4624, 7, "2026-10-06T12:00:00.0000000Z", user="bob-only-marker", ip="10.9.9.9"),
    )
    tenant_id = str(tenant.id)
    other_id = str(other.id)
    late_id = str(late.canonical_event_id)
    early_id = str(early.canonical_event_id)
    sigma_event_id = str(sigma.canonical_event_id)
    file_id = str(file_event.canonical_event_id)
    session.commit()

    events = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id}))
    assert events["page"]["limit"] == 50
    assert events["page"]["has_more"] is False
    assert len(events["data"]) == 6
    assert all(item["headline"] is None for item in events["data"])
    assert events["data"][0]["id"] == late_id

    created = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "sort": "created_time"}))
    assert created["data"][0]["id"] == early_id

    by_severity = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "sort": "severity"}))
    ranks = [SEVERITY_IDS[item["severity"]] for item in by_severity["data"]]
    assert ranks == sorted(ranks, reverse=True)
    assert by_severity["data"][0]["source"] == "mock_edr_alert"
    assert by_severity["data"][0]["severity"] == "critical"

    powershell = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "powershell.exe"}))
    assert sigma_event_id in {item["id"] for item in powershell["data"]}
    assert powershell["data"][0]["headline"]
    assert "powershell" in powershell["data"][0]["headline"].casefold()

    address = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "10.0.0.8"}))
    assert late_id in {item["id"] for item in address["data"]}
    assert len(address["data"]) >= 2

    rule = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": RULE_ID}))
    assert [item["id"] for item in rule["data"]] == [sigma_event_id]

    assert _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "Encoded"}))["data"] == []
    encoded_alerts = _ok(client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "q": "Encoded"}))
    sigma_alert = next(item for item in encoded_alerts["data"] if item["title"] == "Suspicious Encoded PowerShell")
    assert sigma_alert["headline"]
    assert "encoded" in sigma_alert["headline"].casefold()

    alerts_by_time = _ok(client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "sort": "event_time"}))
    assert [item["source"] for item in alerts_by_time["data"]] == ["sigma_alert", "mock_edr_alert"]
    alerts_by_severity = _ok(client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "sort": "severity"}))
    assert [item["severity"] for item in alerts_by_severity["data"]] == ["critical", "high"]
    assert alerts_by_severity["data"][0]["id"] == str(edr.alert_id)

    failure = _ok(
        client.get(
            "/api/v1/search/events",
            params={"tenant": tenant_id, "status": "failure", "source": "windows_event", "event_type": "Authentication"},
        )
    )
    assert len(failure["data"]) == 1
    assert failure["data"][0]["severity"] == "medium"
    assert failure["data"][0]["status"] == "failure"

    window = _ok(
        client.get(
            "/api/v1/search/events",
            params={"tenant": tenant_id, "start": "2026-10-06T12:15:00Z", "end": "2026-10-06T12:45:00Z"},
        )
    )
    assert len(window["data"]) == 1
    assert window["data"][0]["status"] == "failure"

    file_hits = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "payload.dll"}))
    assert [item["id"] for item in file_hits["data"]] == [file_id]

    entities = _ok(client.get("/api/v1/search/entities", params={"tenant": tenant_id, "q": "alice", "limit": 100}))
    assert "user" in {item["entity_type"] for item in entities["data"]}
    assert all(item["headline"] for item in entities["data"])
    assert _types(client, tenant_id) == {"user", "host", "process", "file", "ip"}

    ip_entities = _ok(
        client.get(
            "/api/v1/search/entities",
            params={"tenant": tenant_id, "entity_type": "ip", "q": "10.0.0.8"},
        )
    )
    assert len(ip_entities["data"]) == 1
    assert ip_entities["data"][0]["value"] == "10.0.0.8"
    assert ip_entities["data"][0]["event_count"] >= 2
    assert ip_entities["data"][0]["severity"] == "medium"
    assert {item["entity_type"] for item in ip_entities["data"]} == {"ip"}

    files = _ok(
        client.get("/api/v1/search/entities", params={"tenant": tenant_id, "entity_type": "file", "q": "payload.dll"})
    )
    assert len(files["data"]) == 1
    assert "payload.dll" in files["data"][0]["display_value"].casefold()

    medium_entities = _ok(
        client.get("/api/v1/search/entities", params={"tenant": tenant_id, "severity": "medium", "entity_type": "ip"})
    )
    assert any(item["value"] == "10.0.0.8" for item in medium_entities["data"])

    facets = _ok(client.get("/api/v1/search/facets", params={"tenant": tenant_id}))
    assert sum(item["count"] for item in facets["severity"]) == 6
    assert {item["value"] for item in facets["event_type"]} >= {
        "Authentication",
        "Process Activity",
        "File System Activity",
    }
    assert {item["value"] for item in facets["source"]} == {"windows_event", "sigma_alert", "mock_edr_alert"}
    assert any("alice" in item["value"].casefold() for item in facets["user"])
    assert any("DC01" in item["value"] or "WKSTN" in item["value"] for item in facets["host"])
    assert len(facets["host"]) <= 20
    assert len(facets["user"]) <= 20

    filtered = _ok(client.get("/api/v1/search/facets", params={"tenant": tenant_id, "severity": "informational"}))
    assert sum(item["count"] for item in filtered["severity"]) == 6
    assert sum(item["count"] for item in filtered["event_type"]) < 6
    source_filtered = _ok(client.get("/api/v1/search/facets", params={"tenant": tenant_id, "source": "windows_event"}))
    assert {item["value"] for item in source_filtered["source"]} == {
        "windows_event",
        "sigma_alert",
        "mock_edr_alert",
    }

    seen = _walk(client, "/api/v1/search/events", {"tenant": tenant_id, "limit": "1"})
    assert len(seen) == 6
    assert len(set(seen)) == 6
    cursor = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "limit": 1}))["page"]["next_cursor"]
    assert cursor and "." in cursor and not cursor.startswith("{")
    reused = client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "limit": 1, "cursor": cursor})
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_cursor"
    changed = client.get("/api/v1/search/events", params={"tenant": tenant_id, "limit": 1, "cursor": cursor, "q": "alice"})
    assert changed.status_code == 400

    assert client.get("/api/v1/search/events", params={"tenant": other_id, "q": "10.0.0.8"}).json()["data"] == []
    assert client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "bob-only-marker"}).json()["data"] == []
    other_hits = _ok(client.get("/api/v1/search/events", params={"tenant": other_id, "q": "bob-only-marker"}))
    assert len(other_hits["data"]) == 1

    assert client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "..."}).json()["data"] == []
    assert client.get("/api/v1/search/events", params={"tenant": tenant_id, "limit": 101}).status_code == 422
    assert client.get("/api/v1/search/events", params={"tenant": tenant_id, "status": "new"}).status_code == 422
    assert client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "status": "success"}).status_code == 422
    assert client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "status": "closed"}).json()["data"] == []
    unknown = client.get("/api/v1/search/events", params={"tenant": tenant_id, "foo": "1"})
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "invalid_filter"
    posted = client.post("/api/v1/search/events", params={"tenant": tenant_id})
    assert posted.status_code == 405
    assert posted.json()["error"]["code"] == "method_not_allowed"
    facet_page = client.get("/api/v1/search/facets", params={"tenant": tenant_id, "limit": 1})
    assert facet_page.status_code == 422

    bind_reader(session, tenant.id)
    assert session.scalar(text("SELECT count(*) FROM event_search_documents")) == 6
    assert session.scalar(text("SELECT count(*) FROM alert_search_documents")) == 2
    assert session.scalar(text("SELECT count(*) FROM security_entities")) >= 5
    with pytest.raises(DBAPIError) as exc:
        with session.begin_nested():
            session.execute(text("INSERT INTO event_search_documents (id) VALUES (gen_random_uuid())"))
    assert getattr(exc.value.orig, "sqlstate", None) == "42501"


def test_replay_updates_search_in_place(database, client: TestClient) -> None:
    session, make_tenant = database
    tenant = make_tenant()
    result = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    tenant_id = str(tenant.id)
    session.commit()

    before = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "powershell"}))
    hosts = _ok(
        client.get(
            "/api/v1/search/entities",
            params={"tenant": tenant_id, "entity_type": "host", "q": "WKSTN-01.corp.local"},
        )
    )
    assert len(before["data"]) == 1
    assert len(hosts["data"]) == 1
    event_count = hosts["data"][0]["event_count"]

    duplicate = ingest(session, tenant_id=tenant.id, source_kind="sigma_alert", payload=json.dumps(SIGMA).encode())
    assert duplicate.duplicate is True
    replay(session, tenant_id=tenant.id, source_record_id=result.source_record_id)
    session.commit()

    after = _ok(client.get("/api/v1/search/events", params={"tenant": tenant_id, "q": "powershell"}))
    hosts_after = _ok(
        client.get(
            "/api/v1/search/entities",
            params={"tenant": tenant_id, "entity_type": "host", "q": "WKSTN-01.corp.local"},
        )
    )
    assert [item["id"] for item in after["data"]] == [item["id"] for item in before["data"]]
    assert len(hosts_after["data"]) == 1
    assert hosts_after["data"][0]["event_count"] == event_count
    alerts = _ok(client.get("/api/v1/search/alerts", params={"tenant": tenant_id, "q": RULE_ID}))
    assert len(alerts["data"]) == 1


def _types(client: TestClient, tenant_id: str) -> set[str]:
    page = _ok(client.get("/api/v1/search/entities", params={"tenant": tenant_id, "limit": 100}))
    return {item["entity_type"] for item in page["data"]}


def _walk(client: TestClient, path: str, params: dict) -> list[str]:
    seen = []
    cursor = None
    for _ in range(20):
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        page = _ok(client.get(path, params=query))
        assert len(page["data"]) == 1
        seen.append(page["data"][0]["id"])
        cursor = page["page"]["next_cursor"]
        if not page["page"]["has_more"]:
            return seen
    raise AssertionError("search pages did not end")


def _ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def _windows(event_id: int, record_id: int, when: str, user: str = "alice", ip: str = "10.0.0.8") -> bytes:
    body = copy.deepcopy(WINDOWS_SECURITY)
    body["Event"]["System"]["EventID"] = event_id
    body["Event"]["System"]["EventRecordID"] = record_id
    body["Event"]["System"]["TimeCreated"]["SystemTime"] = when
    body["Event"]["EventData"]["TargetUserName"] = user
    body["Event"]["EventData"]["IpAddress"] = ip
    return json.dumps(body).encode()


def _file(when: str) -> bytes:
    return json.dumps(
        {
            "Event": {
                "System": {
                    "Provider": {"Name": "Microsoft-Windows-Sysmon"},
                    "EventID": 11,
                    "TimeCreated": {"SystemTime": when},
                    "Computer": "WKSTN-01.corp.local",
                    "Channel": "Microsoft-Windows-Sysmon/Operational",
                    "EventRecordID": 900,
                },
                "EventData": {"TargetFilename": r"C:\Temp\payload.dll"},
            }
        }
    ).encode()
