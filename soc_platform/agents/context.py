"""Per-run workspace handed to graph nodes. It is not checkpointed outside this process."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass
class RunContext:
    session: Session
    tenant_id: UUID
    run_id: UUID
    cursor_secret: str
    tools: object


_CURRENT: ContextVar[RunContext | None] = ContextVar("soc_agent_run", default=None)


def current_run() -> RunContext:
    context = _CURRENT.get()
    if context is None:
        raise RuntimeError("investigation workflow is not bound to a run")
    return context


def bind_run(context: RunContext):
    return _CURRENT.set(context)


def reset_run(token) -> None:
    _CURRENT.reset(token)
