"""Phase 6 observability stays outside the security API contract."""

from __future__ import annotations

import io
import json
import logging
import re

from fastapi.testclient import TestClient

from soc_platform.config import Settings
from soc_platform.main import create_app
from soc_platform.observability.context import normalize_correlation_id, reset_correlation_id, set_correlation_id
from soc_platform.observability.logging import ContextFilter, JsonFormatter
from soc_platform.observability.hooks import observe_search
from soc_platform.observability.metrics import (
    AGENT_RUNS,
    API_ERRORS,
    API_REQUESTS,
    CITATION_FAILURES,
    DRAFT_APPROVALS,
    DRAFTS_GENERATED,
    OUTBOX_PUBLISH_FAILURES,
    REDIS_ERRORS,
    REVIEW_REQUESTS,
    SEARCH_REQUESTS,
    record_agent_run,
    record_draft,
    record_outbox_failure,
    record_redis,
    record_review,
    sql_operation,
)
from soc_platform.observability.redis import instrument_redis_client

_TRACE = re.compile(r"^[0-9a-f]{32}$")
_SPAN = re.compile(r"^[0-9a-f]{16}$")
_NAMES = (
    "api_request_total",
    "api_request_duration_seconds",
    "api_errors_total",
    "search_requests_total",
    "search_duration_seconds",
    "search_result_count",
    "events_ingested_total",
    "events_replayed_total",
    "outbox_events_total",
    "outbox_publish_failures_total",
    "dead_letters_total",
    "alerts_total",
    "high_severity_alerts_total",
    "open_alerts_total",
    "active_cases_total",
    "investigations_total",
    "agent_runs_total",
    "agent_run_duration_seconds",
    "drafts_generated_total",
    "citation_validation_failures_total",
    "insufficient_evidence_total",
    "draft_approvals_total",
    "draft_rejections_total",
    "review_requests_total",
    "review_duration_seconds",
    "db_query_duration_seconds",
    "db_pool_connections",
    "redis_commands_total",
    "redis_command_duration_seconds",
    "redis_errors_total",
    "dependency_up",
)


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://soc:soc@localhost:5434/soc",
        redis_url="redis://localhost:6379/0",
        otlp_endpoint="",
        metrics_enabled=True,
        log_format="text",
    )


def _counter(metric, **labels: str) -> float:
    return float(metric.labels(**labels)._value.get()) if labels else float(metric._value.get())


def test_json_logs_carry_service_and_correlation() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter("soc-api"))
    log = logging.getLogger("soc.test.observability")
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    token = set_correlation_id("phase6-log")
    try:
        log.info("intake recorded")
    finally:
        reset_correlation_id(token)
    payload = json.loads(stream.getvalue())
    assert payload["service"] == "soc-api"
    assert payload["correlation_id"] == "phase6-log"
    assert payload["message"] == "intake recorded"
    assert set(payload) >= {"timestamp", "level", "logger", "trace_id", "span_id"}


def test_correlation_id_rejects_injected_values() -> None:
    assert normalize_correlation_id("phase6-test") == "phase6-test"
    generated = normalize_correlation_id("bad id\n")
    assert generated != "bad id\n"
    assert normalize_correlation_id(None) != ""


def test_sql_operation_keeps_only_the_verb() -> None:
    assert sql_operation("SELECT secret FROM alerts WHERE tenant_id = 'x'") == "select"
    assert sql_operation("INSERT INTO outbox_events (payload) VALUES ('secret')") == "insert"
    assert sql_operation("UPDATE alerts SET status = 'closed'") == "update"
    assert sql_operation("DELETE FROM alerts") == "other"


def test_process_metrics_move_without_a_collector() -> None:
    drafts = _counter(DRAFTS_GENERATED, status="pending_approval")
    reviews = _counter(REVIEW_REQUESTS)
    citations = _counter(CITATION_FAILURES)
    approvals = _counter(DRAFT_APPROVALS)
    agents = _counter(AGENT_RUNS, status="completed")
    failures = _counter(OUTBOX_PUBLISH_FAILURES)
    redis_errors = _counter(REDIS_ERRORS, command="XADD")
    record_draft("pending_approval")
    record_draft("validation_failed")
    record_review("approved", decided_at=_Stamp(10), created_at=_Stamp(4))
    record_agent_run("completed", 0.05)
    record_outbox_failure()
    record_redis("XADD", 0.01, error=True)
    assert _counter(DRAFTS_GENERATED, status="pending_approval") == drafts + 1
    assert _counter(REVIEW_REQUESTS) == reviews + 1
    assert _counter(CITATION_FAILURES) == citations + 1
    assert _counter(DRAFT_APPROVALS) == approvals + 1
    assert _counter(AGENT_RUNS, status="completed") == agents + 1
    assert _counter(OUTBOX_PUBLISH_FAILURES) == failures + 1
    assert _counter(REDIS_ERRORS, command="XADD") == redis_errors + 1


def test_search_observer_counts_results_and_reraises() -> None:
    before = _counter(SEARCH_REQUESTS, operation="events", status="ok")

    @observe_search("events")
    def succeed():
        return _Page([1, 2, 3])

    assert len(succeed().data) == 3
    assert _counter(SEARCH_REQUESTS, operation="events", status="ok") == before + 1

    errors = _counter(SEARCH_REQUESTS, operation="events", status="error")

    @observe_search("events")
    def fail():
        raise RuntimeError("search failed")

    try:
        fail()
    except RuntimeError as exc:
        assert str(exc) == "search failed"
    else:
        raise AssertionError("search exception was swallowed")
    assert _counter(SEARCH_REQUESTS, operation="events", status="error") == errors + 1


def test_redis_wrapper_preserves_results() -> None:
    class Client:
        def execute_command(self, *args, **kwargs):
            assert args == ("GET", "session")
            return b"ok"

    wrapped = instrument_redis_client(Client())
    assert wrapped.execute_command("GET", "session") == b"ok"


def test_health_carries_trace_headers_and_metrics_stay_out_of_openapi() -> None:
    app = create_app(_settings())
    assert "/health" not in app.openapi()["paths"]
    assert "/ready" not in app.openapi()["paths"]
    assert "/metrics" not in app.openapi()["paths"]
    with TestClient(app) as client:
        health = client.get("/health", headers={"X-Correlation-ID": "phase6-test"})
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert health.headers["x-correlation-id"] == "phase6-test"
        assert _TRACE.fullmatch(health.headers["x-trace-id"])
        assert _SPAN.fullmatch(health.headers["x-span-id"])

        rejected = client.get("/health", headers={"X-Correlation-ID": "bad id"})
        assert rejected.headers["x-correlation-id"] != "bad id"
        assert _TRACE.fullmatch(rejected.headers["x-trace-id"])

        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ok", "postgres": "ok", "redis": "ok"}

        requests_before = _counter(API_REQUESTS, method="GET", route="/api/v1/alerts", status="422")
        errors_before = _counter(API_ERRORS, method="GET", route="/api/v1/alerts", status="422")
        missing_tenant = client.get("/api/v1/alerts")
        assert missing_tenant.status_code == 422
        assert missing_tenant.headers["x-trace-id"]
        assert _counter(API_REQUESTS, method="GET", route="/api/v1/alerts", status="422") == requests_before + 1
        assert _counter(API_ERRORS, method="GET", route="/api/v1/alerts", status="422") == errors_before + 1

        body = client.get("/metrics").text
        for name in _NAMES:
            assert name in body


class _Page:
    def __init__(self, data: list[int]) -> None:
        self.data = data


class _Stamp:
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds

    def __sub__(self, other: _Stamp) -> _Stamp:
        return _Stamp(self.seconds - other.seconds)

    def total_seconds(self) -> float:
        return float(self.seconds)
