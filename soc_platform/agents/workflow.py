"""Run one investigation. Canonical tables are not updated."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy.orm import Session

from soc_platform.agents.actors import require_human
from soc_platform.agents.context import RunContext, bind_run, reset_run
from soc_platform.agents.graph import InvestigationState, build_graph
from soc_platform.agents.network import assert_local_text
from soc_platform.agents.tools import ToolRegistry
from soc_platform.api.reader import assert_agent
from soc_platform.db.session import database_now
from soc_platform.domain.enums import AgentRunStatus
from soc_platform.models.agent import AgentRun
from soc_platform.models.mixins import new_uuid
from soc_platform.observability.hooks import observed_agent_run
from soc_platform.observability.tracing import span

_GRAPH = None
_TRACING = ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING")


@observed_agent_run
def start_run(
    session: Session,
    *,
    tenant_id: UUID,
    requested_by: str,
    alert_id: UUID | None = None,
    question: str | None = None,
    cursor_secret: str,
    tools: ToolRegistry | None = None,
) -> AgentRun:
    assert_agent(session, tenant_id)
    person = require_human(requested_by, field="requested_by")
    assert_local_text(question)
    if alert_id is None and question is None:
        raise ValueError("alert_id or question is required")
    now = database_now(session)
    run = AgentRun(
        id=new_uuid(),
        tenant_id=tenant_id,
        alert_id=alert_id,
        question=question,
        status=AgentRunStatus.RUNNING,
        error_code=None,
        error_message=None,
        requested_by=person,
        created_at=now,
        finished_at=None,
    )
    session.add(run)
    session.flush()
    context = RunContext(
        session=session,
        tenant_id=tenant_id,
        run_id=run.id,
        cursor_secret=cursor_secret,
        tools=tools or ToolRegistry(),
    )
    token = bind_run(context)
    try:
        with _tracing_off():
            with span("investigation.workflow"):
                final = _graph().invoke(_initial_state(alert_id, question), config={"recursion_limit": 40})
    except Exception:
        final = {
            "failed": True,
            "error_code": "agent_failed",
            "error_message": "investigation failed",
        }
    finally:
        reset_run(token)
    failed = bool(final.get("failed"))
    run.status = AgentRunStatus.FAILED if failed else AgentRunStatus.COMPLETED
    run.error_code = final.get("error_code") if failed else None
    run.error_message = final.get("error_message") if failed else None
    run.finished_at = database_now(session)
    session.flush()
    return run


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _initial_state(alert_id: UUID | None, question: str | None) -> InvestigationState:
    return {
        "alert_id": None if alert_id is None else str(alert_id),
        "question": question,
        "plan": ["triage", "entity", "threat", "reporting"],
        "cursor": 0,
        "failed": False,
        "error_code": None,
        "error_message": None,
        "draft_id": None,
        "memory": [],
    }


@contextmanager
def _tracing_off():
    saved = {key: os.environ.get(key) for key in _TRACING}
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
