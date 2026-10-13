"""Canonical routes stay read-only. Agent routes write drafts only."""

from fastapi.routing import APIRoute

from soc_platform.config import Settings
from soc_platform.main import create_app

EXPECTED_PATHS = [
    "/api/v1/agent/drafts",
    "/api/v1/agent/drafts/{draft_id}",
    "/api/v1/agent/drafts/{draft_id}/decisions",
    "/api/v1/agent/runs",
    "/api/v1/agent/runs/{run_id}",
    "/api/v1/alerts",
    "/api/v1/alerts/{alert_id}",
    "/api/v1/cases",
    "/api/v1/cases/{case_id}",
    "/api/v1/events",
    "/api/v1/events/{event_id}",
    "/api/v1/evidence",
    "/api/v1/evidence/{evidence_id}",
    "/api/v1/findings",
    "/api/v1/findings/{finding_id}",
    "/api/v1/investigations",
    "/api/v1/investigations/{investigation_id}",
    "/api/v1/operations/connectors",
    "/api/v1/operations/dead-letters",
    "/api/v1/operations/publications",
    "/api/v1/search/alerts",
    "/api/v1/search/entities",
    "/api/v1/search/entities/{entity_id}",
    "/api/v1/search/events",
    "/api/v1/search/facets",
]


def _app():
    return create_app(
        Settings(
            database_url="postgresql+psycopg://soc:soc@localhost:5434/soc",
            redis_url="redis://localhost:6379/0",
        )
    )


def _api_routes(app):
    found = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        routes = original.routes if original is not None else [route]
        found.extend(item for item in routes if isinstance(item, APIRoute))
    return found


def test_registers_only_read_routes() -> None:
    app = _app()
    api_routes = _api_routes(app)
    methods = {method for route in api_routes for method in route.methods}
    assert methods <= {"GET", "HEAD", "POST"}
    assert methods.isdisjoint({"PUT", "PATCH", "DELETE"})
    post_paths = {path for path, operations in app.openapi()["paths"].items() if "post" in operations}
    assert post_paths == {"/api/v1/agent/runs", "/api/v1/agent/drafts/{draft_id}/decisions"}
    for path, operations in app.openapi()["paths"].items():
        assert operations.keys().isdisjoint({"put", "patch", "delete"})
        if not path.startswith("/api/v1/agent/"):
            assert "post" not in operations
    assert sorted(app.openapi()["paths"]) == EXPECTED_PATHS
    assert app.openapi_url == "/openapi.json"
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"


def test_openapi_declares_tenant_limit_and_cursor() -> None:
    schema = _app().openapi()
    events = schema["paths"]["/api/v1/events"]["get"]
    names = {item["name"] for item in events["parameters"]}
    assert {"tenant", "source", "severity", "event_type", "start", "end", "limit", "cursor"} <= names
    limit = next(item for item in events["parameters"] if item["name"] == "limit")
    assert limit["schema"]["default"] == 50
    assert limit["schema"]["maximum"] == 100
    tenant = next(item for item in events["parameters"] if item["name"] == "tenant")
    assert tenant["required"] is True
    alerts = schema["paths"]["/api/v1/alerts"]["get"]
    alert_names = {item["name"] for item in alerts["parameters"]}
    assert "alert_status" in alert_names
    assert "event_type" not in alert_names
    cases = schema["paths"]["/api/v1/cases"]["get"]
    assert "case_status" in {item["name"] for item in cases["parameters"]}
    investigations = schema["paths"]["/api/v1/investigations"]["get"]
    assert "investigation_status" in {item["name"] for item in investigations["parameters"]}
    search = schema["paths"]["/api/v1/search/events"]["get"]
    search_names = {item["name"] for item in search["parameters"]}
    assert {
        "tenant",
        "q",
        "sort",
        "severity",
        "source",
        "status",
        "event_type",
        "start",
        "end",
        "limit",
        "cursor",
    } <= search_names
    search_limit = next(item for item in search["parameters"] if item["name"] == "limit")
    assert search_limit["schema"]["default"] == 50
    assert search_limit["schema"]["maximum"] == 100
    entities = schema["paths"]["/api/v1/search/entities"]["get"]
    assert "entity_type" in {item["name"] for item in entities["parameters"]}
    facets = schema["paths"]["/api/v1/search/facets"]["get"]
    facet_names = {item["name"] for item in facets["parameters"]}
    assert {"tenant", "q", "severity", "source", "status", "event_type", "start", "end"} <= facet_names
    assert facet_names.isdisjoint({"limit", "cursor", "sort"})
