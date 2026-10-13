"""Observation wrappers. They record the outcome the callee already decided."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from soc_platform.observability.metrics import record_agent_run, record_draft, record_review, record_search
from soc_platform.observability.tracing import span

_F = TypeVar("_F", bound=Callable[..., Any])


def observe_search(operation: str) -> Callable[[_F], _F]:
    def decorator(func: _F) -> _F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                with span("search", **{"search.operation": operation}):
                    result = func(*args, **kwargs)
            except Exception:
                record_search(operation, time.perf_counter() - started, None, error=True)
                raise
            record_search(operation, time.perf_counter() - started, _result_count(result), error=False)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def observed_agent_run(func: _F) -> _F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            run = func(*args, **kwargs)
        except Exception:
            record_agent_run("failed", time.perf_counter() - started)
            raise
        status = getattr(getattr(run, "status", None), "value", "failed")
        record_agent_run(str(status or "failed"), time.perf_counter() - started)
        return run

    return wrapper  # type: ignore[return-value]


def observed_draft(func: _F) -> _F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with span("draft.store"):
            draft = func(*args, **kwargs)
        status = getattr(getattr(draft, "status", None), "value", "")
        record_draft(str(status))
        return draft

    return wrapper  # type: ignore[return-value]


def observed_decision(func: _F) -> _F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with span("draft.review"):
            draft = func(*args, **kwargs)
        decision = getattr(getattr(draft, "status", None), "value", "rejected")
        record_review(str(decision), getattr(draft, "updated_at", None), getattr(draft, "created_at", None))
        return draft

    return wrapper  # type: ignore[return-value]


def _result_count(result: object) -> float:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return float(len(data))
    total = 0
    found = False
    for name in ("event_type", "severity", "source", "host", "user"):
        rows = getattr(result, name, None)
        if isinstance(rows, list):
            found = True
            total += sum(int(getattr(row, "count", 0) or 0) for row in rows)
    if found:
        return float(total)
    return 1.0
