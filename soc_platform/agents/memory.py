"""Append-only workspace memory for one run."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from soc_platform.agents.context import RunContext
from soc_platform.api.reader import assert_agent
from soc_platform.db.session import database_now
from soc_platform.domain.enums import AgentName, MemoryKind
from soc_platform.models.agent import AgentMemory
from soc_platform.models.mixins import new_uuid


def remember(context: RunContext, *, agent: AgentName, kind: MemoryKind, payload: dict[str, Any]) -> dict[str, Any]:
    assert_agent(context.session, context.tenant_id)
    sequence = context.session.scalar(
        select(func.max(AgentMemory.sequence)).where(
            AgentMemory.tenant_id == context.tenant_id,
            AgentMemory.run_id == context.run_id,
        )
    )
    row = AgentMemory(
        id=new_uuid(),
        tenant_id=context.tenant_id,
        run_id=context.run_id,
        agent=agent,
        sequence=int(sequence or 0) + 1,
        kind=kind,
        payload=payload,
        created_at=database_now(context.session),
    )
    context.session.add(row)
    context.session.flush()
    return {"sequence": row.sequence, "agent": agent.value, "kind": kind.value, "payload": payload}


def claim_payload(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    return {"proposals": proposals}


def observation_payload(tool: str, arguments: dict[str, Any], records: list[dict[str, Any]], error: str | None) -> dict:
    return {"tool": tool, "arguments": arguments, "records": records, "error": error}


def record_payload(kind: str, record_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "id": str(record_id), "fields": fields}


def proposal_payload(proposal) -> dict[str, Any]:
    return {
        "template": proposal.template,
        "kind": proposal.kind,
        "record_id": str(proposal.record_id),
        "arguments": proposal.arguments,
    }
