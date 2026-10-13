"""Prometheus metrics. Names match the platform scrape contract.

Inventory levels are emitted by the API collector from PostgreSQL. Process
counters below move only in the process that did the work. A name is one or
the other so a scrape does not export the same series twice.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
REVIEW_BUCKETS = (1, 5, 15, 30, 60, 300, 900, 3600, 14400, 86400)
RESULT_BUCKETS = (0, 1, 5, 10, 25, 50, 100, 250, 1000)

API_REQUESTS = Counter(
    "api_request_total",
    "HTTP requests served by the security API.",
    ("method", "route", "status"),
)
API_DURATION = Histogram(
    "api_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=LATENCY_BUCKETS,
)
API_ERRORS = Counter(
    "api_errors_total",
    "HTTP responses with status 400 or higher.",
    ("method", "route", "status"),
)
SEARCH_REQUESTS = Counter(
    "search_requests_total",
    "Search operations served by the API.",
    ("operation", "status"),
)
SEARCH_DURATION = Histogram(
    "search_duration_seconds",
    "Search operation duration in seconds.",
    ("operation",),
    buckets=LATENCY_BUCKETS,
)
SEARCH_RESULTS = Histogram(
    "search_result_count",
    "Number of rows or facet counts returned by a search operation.",
    ("operation",),
    buckets=RESULT_BUCKETS,
)
AGENT_RUNS = Counter(
    "agent_runs_total",
    "Investigation workflow runs.",
    ("status",),
)
AGENT_DURATION = Histogram(
    "agent_run_duration_seconds",
    "Investigation workflow duration in seconds.",
    ("status",),
    buckets=LATENCY_BUCKETS,
)
DRAFTS_GENERATED = Counter(
    "drafts_generated_total",
    "Investigation drafts stored by an agent.",
    ("status",),
)
CITATION_FAILURES = Counter(
    "citation_validation_failures_total",
    "Drafts stored because a citation did not match the cited record.",
)
INSUFFICIENT_EVIDENCE = Counter(
    "insufficient_evidence_total",
    "Drafts stored because no stored record supported a claim.",
)
DRAFT_APPROVALS = Counter(
    "draft_approvals_total",
    "Drafts a person approved.",
)
DRAFT_REJECTIONS = Counter(
    "draft_rejections_total",
    "Drafts a person rejected, including requests for changes.",
)
REVIEW_REQUESTS = Counter(
    "review_requests_total",
    "Drafts stored as pending a person's decision.",
)
REVIEW_DURATION = Histogram(
    "review_duration_seconds",
    "Seconds from draft creation until a person decides it.",
    ("decision",),
    buckets=REVIEW_BUCKETS,
)
DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Database statement duration in seconds.",
    ("operation",),
    buckets=LATENCY_BUCKETS,
)
REDIS_COMMANDS = Counter(
    "redis_commands_total",
    "Redis commands issued by this process.",
    ("command",),
)
REDIS_DURATION = Histogram(
    "redis_command_duration_seconds",
    "Redis command duration in seconds.",
    ("command",),
    buckets=LATENCY_BUCKETS,
)
REDIS_ERRORS = Counter(
    "redis_errors_total",
    "Redis commands that raised an error.",
    ("command",),
)
OUTBOX_PUBLISH_FAILURES = Counter(
    "outbox_publish_failures_total",
    "Outbox publish attempts that failed, including attempts that will be retried.",
)

def _quiet(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:
        logger.debug("metric update failed", exc_info=True)


def record_api(method: str, route: str, status: int, duration: float) -> None:
    def update() -> None:
        method_label = (method or "GET").upper()[:16]
        route_label = (route or "unmatched")[:128]
        code = str(int(status))
        API_REQUESTS.labels(method=method_label, route=route_label, status=code).inc()
        API_DURATION.labels(method=method_label, route=route_label).observe(max(duration, 0.0))
        if status >= 400:
            API_ERRORS.labels(method=method_label, route=route_label, status=code).inc()

    _quiet(update)


def record_search(operation: str, duration: float, result_count: float | None, *, error: bool) -> None:
    def update() -> None:
        label = (operation or "search")[:64]
        status = "error" if error else "ok"
        SEARCH_REQUESTS.labels(operation=label, status=status).inc()
        SEARCH_DURATION.labels(operation=label).observe(max(duration, 0.0))
        if result_count is not None and not error:
            SEARCH_RESULTS.labels(operation=label).observe(max(result_count, 0.0))

    _quiet(update)


def record_agent_run(status: str, duration: float) -> None:
    def update() -> None:
        label = (status or "failed")[:32]
        AGENT_RUNS.labels(status=label).inc()
        AGENT_DURATION.labels(status=label).observe(max(duration, 0.0))

    _quiet(update)


def record_draft(status: str) -> None:
    def update() -> None:
        label = (status or "unknown")[:64]
        DRAFTS_GENERATED.labels(status=label).inc()
        if label == "validation_failed":
            CITATION_FAILURES.inc()
        elif label == "insufficient_evidence":
            INSUFFICIENT_EVIDENCE.inc()
        elif label == "pending_approval":
            REVIEW_REQUESTS.inc()

    _quiet(update)


def record_review(decision: str, decided_at: object, created_at: object) -> None:
    def update() -> None:
        label = "approved" if decision == "approved" else "rejected"
        if label == "approved":
            DRAFT_APPROVALS.inc()
        else:
            DRAFT_REJECTIONS.inc()
        if hasattr(decided_at, "__sub__") and created_at is not None:
            seconds = (decided_at - created_at).total_seconds()  # type: ignore[operator]
            if seconds >= 0:
                REVIEW_DURATION.labels(decision=label).observe(seconds)

    _quiet(update)


def record_db_query(operation: str, duration: float) -> None:
    def update() -> None:
        label = operation if operation in {"select", "insert", "update"} else "other"
        DB_QUERY_DURATION.labels(operation=label).observe(max(duration, 0.0))

    _quiet(update)


def record_redis(command: str, duration: float, *, error: bool) -> None:
    def update() -> None:
        label = command or "unknown"
        REDIS_COMMANDS.labels(command=label).inc()
        REDIS_DURATION.labels(command=label).observe(max(duration, 0.0))
        if error:
            REDIS_ERRORS.labels(command=label).inc()

    _quiet(update)


def record_outbox_failure() -> None:
    _quiet(OUTBOX_PUBLISH_FAILURES.inc)


def sql_operation(statement: object) -> str:
    text = statement if isinstance(statement, str) else str(getattr(statement, "text", "") or "")
    parts = text.lstrip()[:32].split(None, 1)
    token = parts[0].lower() if parts else ""
    if token in {"select", "with"}:
        return "select"
    if token in {"insert", "update"}:
        return token
    return "other"


def monotonic_seconds() -> float:
    return time.perf_counter()
