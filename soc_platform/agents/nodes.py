"""Supervisor and specialist nodes. Each specialist may only call the tool registry."""

from __future__ import annotations

from uuid import UUID

from soc_platform.agents.citations import (
    CitationError,
    ClaimProposal,
    proposal_from_entity,
    proposal_from_event,
    proposal_from_evidence,
    proposals_from_alert,
    validate_proposal,
)
from soc_platform.agents.context import current_run
from soc_platform.agents.drafts import store_draft
from soc_platform.agents.memory import claim_payload, observation_payload, proposal_payload, record_payload, remember
from soc_platform.agents.tools import ToolResult
from soc_platform.domain.enums import AgentName, DraftStatus, MemoryKind

_PLAN = ["triage", "entity", "threat", "reporting"]
_MAX_ENTITIES = 8
_MAX_TECHNIQUES = 8


def supervisor(state: dict) -> dict:
    if state.get("cursor") != 0 or state.get("failed"):
        return {}
    entry = remember(
        current_run(),
        agent=AgentName.SUPERVISOR,
        kind=MemoryKind.PLAN,
        payload={"plan": list(state.get("plan") or _PLAN)},
    )
    return {"memory": [entry]}


def triage(state: dict) -> dict:
    context = current_run()
    proposals = []
    entries = []
    alert_id = state.get("alert_id")
    question = state.get("question")
    if alert_id:
        loaded = context.tools.call("get_alert", alert_id=alert_id)
        entries.append(_observation(AgentName.TRIAGE, "get_alert", {"alert_id": alert_id}, loaded))
        if loaded.error or not loaded.records:
            return {
                "failed": True,
                "error_code": "alert_not_found",
                "error_message": "Stored alert was not found.",
                "memory": entries,
            }
        alert = loaded.records[0]
        proposals.extend(proposals_from_alert(alert.id, alert.fields))
        event_id = alert.fields.get("canonical_event_id")
        if event_id:
            event = context.tools.call("get_event", event_id=event_id)
            entries.append(_observation(AgentName.TRIAGE, "get_event", {"event_id": event_id}, event))
            proposals.extend(_event_proposals(event))
        evidence = context.tools.call("list_alert_evidence", alert_id=alert_id)
        entries.append(_observation(AgentName.TRIAGE, "list_alert_evidence", {"alert_id": alert_id}, evidence))
        proposals.extend(_evidence_proposals(evidence))
    elif question:
        for tool_name in ("search_alerts", "search_events"):
            found = context.tools.call(tool_name, q=question)
            entries.append(_observation(AgentName.TRIAGE, tool_name, {"q": question}, found))
            proposals.extend(_record_proposals(found))
    else:
        return {
            "failed": True,
            "error_code": "missing_subject",
            "error_message": "An alert or a question is required.",
            "memory": entries,
        }
    entries.append(_claims(AgentName.TRIAGE, proposals))
    return {"cursor": state["cursor"] + 1, "memory": entries}


def entity(state: dict) -> dict:
    context = current_run()
    proposals = []
    entries = []
    seen: set[str] = set()
    lookups = 0
    for event_id in _event_ids(state):
        if lookups >= _MAX_ENTITIES:
            break
        extracted = context.tools.call("event_entity_keys", event_id=event_id)
        entries.append(_observation(AgentName.ENTITY, "event_entity_keys", {"event_id": event_id}, extracted))
        keys = []
        for record in extracted.records:
            keys.extend(record.fields.get("keys") or [])
        for key in keys:
            if lookups >= _MAX_ENTITIES:
                break
            marker = f"{key.get('entity_type')}:{key.get('value')}"
            if marker in seen:
                continue
            seen.add(marker)
            lookups += 1
            found = context.tools.call(
                "get_entity_by_value",
                entity_type=key.get("entity_type"),
                value=key.get("display_value") or key.get("value") or "",
            )
            entries.append(
                _observation(
                    AgentName.ENTITY,
                    "get_entity_by_value",
                    {"entity_type": key.get("entity_type"), "value": key.get("value")},
                    found,
                )
            )
            for record in found.records:
                proposals.append(proposal_from_entity(record.id, record.fields))
    if not lookups and state.get("question"):
        found = context.tools.call("search_entities", q=state["question"])
        entries.append(_observation(AgentName.ENTITY, "search_entities", {"q": state["question"]}, found))
        for record in found.records:
            proposals.append(proposal_from_entity(record.id, record.fields))
    entries.append(_claims(AgentName.ENTITY, proposals))
    return {"cursor": state["cursor"] + 1, "memory": entries}


def threat(state: dict) -> dict:
    context = current_run()
    techniques: list[str] = []
    known: set[str] = set()
    for record in _records(state):
        if record.get("kind") != "alert":
            continue
        known.add(record["id"])
        for technique in record.get("fields", {}).get("technique_ids") or []:
            if technique not in techniques:
                techniques.append(technique)
    proposals = []
    entries = []
    if not techniques:
        entries.append(
            remember(
                context,
                agent=AgentName.THREAT,
                kind=MemoryKind.OBSERVATION,
                payload={"tool": "search_alerts", "arguments": {}, "records": [], "error": "no_stored_technique"},
            )
        )
    for technique in techniques[:_MAX_TECHNIQUES]:
        found = context.tools.call("search_alerts", q=technique)
        entries.append(_observation(AgentName.THREAT, "search_alerts", {"q": technique}, found))
        for record in found.records:
            identity = str(record.id)
            if identity in known:
                continue
            known.add(identity)
            proposals.extend(proposals_from_alert(record.id, record.fields))
    entries.append(_claims(AgentName.THREAT, proposals))
    return {"cursor": state["cursor"] + 1, "memory": entries}


def reporting(state: dict) -> dict:
    context = current_run()
    proposals = _proposals(state)
    validated = []
    failures = 0
    for proposal in proposals:
        result = validate_proposal(context.session, context.tenant_id, proposal)
        if isinstance(result, CitationError):
            failures += 1
            continue
        validated.append(result)
    if failures:
        status = DraftStatus.VALIDATION_FAILED
        failed = True
        error_code = "validation_failed"
        error_message = f"{failures} claim did not match a stored record."
    elif not validated:
        status = DraftStatus.INSUFFICIENT_EVIDENCE
        failed = False
        error_code = None
        error_message = None
    else:
        status = DraftStatus.PENDING_APPROVAL
        failed = False
        error_code = None
        error_message = None
    draft = store_draft(
        context.session,
        tenant_id=context.tenant_id,
        run_id=context.run_id,
        status=status,
        title=_title(validated, state.get("question")),
        claims=validated,
    )
    entry = remember(
        context,
        agent=AgentName.REPORTING,
        kind=MemoryKind.OBSERVATION,
        payload={"draft_id": str(draft.id), "status": status.value, "claims": len(validated), "rejected": failures},
    )
    return {
        "cursor": state["cursor"] + 1,
        "failed": failed,
        "error_code": error_code,
        "error_message": error_message,
        "draft_id": str(draft.id),
        "memory": [entry],
    }


def failure(state: dict) -> dict:
    entry = remember(
        current_run(),
        agent=AgentName.SUPERVISOR,
        kind=MemoryKind.FAILURE,
        payload={"error_code": state.get("error_code") or "agent_failed"},
    )
    return {"memory": [entry]}


def route(state: dict) -> str:
    if state.get("failed"):
        return "failure"
    plan = state.get("plan") or _PLAN
    cursor = int(state.get("cursor") or 0)
    if cursor >= len(plan):
        return "end"
    return plan[cursor]


def _observation(agent: AgentName, tool: str, arguments: dict, result: ToolResult) -> dict:
    return remember(
        current_run(),
        agent=agent,
        kind=MemoryKind.OBSERVATION,
        payload=observation_payload(tool, arguments, [_public_record(record) for record in result.records], result.error),
    )


def _claims(agent: AgentName, proposals: list) -> dict:
    return remember(
        current_run(),
        agent=agent,
        kind=MemoryKind.CLAIM,
        payload=claim_payload([proposal_payload(proposal) for proposal in proposals]),
    )


def _public_record(record) -> dict:
    return record_payload(record.kind, record.id, record.fields)


def _event_proposals(result: ToolResult) -> list:
    return [proposal_from_event(record.id, record.fields) for record in result.records if record.kind == "event"]


def _evidence_proposals(result: ToolResult) -> list:
    return [proposal_from_evidence(record.id, record.fields) for record in result.records if record.kind == "evidence"]


def _record_proposals(result: ToolResult) -> list:
    proposals = []
    for record in result.records:
        if record.kind == "alert":
            proposals.extend(proposals_from_alert(record.id, record.fields))
        elif record.kind == "event":
            proposals.append(proposal_from_event(record.id, record.fields))
    return proposals


def _event_ids(state: dict) -> list[str]:
    found: list[str] = []
    for record in _records(state):
        if record.get("kind") == "event" and "keys" not in record.get("fields", {}):
            identity = record["id"]
            if identity not in found:
                found.append(identity)
        event_id = record.get("fields", {}).get("canonical_event_id")
        if isinstance(event_id, str) and event_id not in found:
            found.append(event_id)
    return found


def _records(state: dict) -> list[dict]:
    rows = []
    for entry in state.get("memory") or []:
        payload = entry.get("payload") or {}
        rows.extend(payload.get("records") or [])
    return rows


def _proposals(state: dict) -> list[ClaimProposal]:
    found: list[ClaimProposal] = []
    seen: set[str] = set()
    for entry in state.get("memory") or []:
        if entry.get("kind") != MemoryKind.CLAIM.value:
            continue
        for raw in (entry.get("payload") or {}).get("proposals") or []:
            identity = f"{raw['template']}:{raw['record_id']}:{sorted(raw['arguments'].items())}"
            if identity in seen:
                continue
            seen.add(identity)
            found.append(
                ClaimProposal(
                    template=raw["template"],
                    kind=raw["kind"],
                    record_id=UUID(raw["record_id"]),
                    arguments=dict(raw["arguments"]),
                )
            )
    return found


def _title(claims, question: str | None) -> str:
    for claim in claims:
        if claim.template == "alert.summary":
            return f"Draft: {claim.arguments['title']}"
    if question:
        return f"Draft: {question}"
    return "Investigation draft"
