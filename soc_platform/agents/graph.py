"""LangGraph investigation workflow. The checkpointer is in-process only."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from soc_platform.agents.network import NetworkDenied
from soc_platform.agents.nodes import entity, failure, reporting, route, supervisor, threat, triage
from soc_platform.observability.tracing import span


class InvestigationState(TypedDict):
    alert_id: str | None
    question: str | None
    plan: list[str]
    cursor: int
    failed: bool
    error_code: str | None
    error_message: str | None
    draft_id: str | None
    memory: Annotated[list[dict], operator.add]


def build_graph():
    builder = StateGraph(InvestigationState)
    builder.add_node("supervisor", _guard(supervisor, "supervisor"))
    builder.add_node("triage", _guard(triage, "triage"))
    builder.add_node("entity", _guard(entity, "entity"))
    builder.add_node("threat", _guard(threat, "threat"))
    builder.add_node("reporting", _guard(reporting, "reporting"))
    builder.add_node("failure", failure)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route,
        {
            "triage": "triage",
            "entity": "entity",
            "threat": "threat",
            "reporting": "reporting",
            "failure": "failure",
            "end": END,
        },
    )
    for name in ("triage", "entity", "threat", "reporting"):
        builder.add_edge(name, "supervisor")
    builder.add_edge("failure", END)
    return builder.compile()


def _guard(function, agent: str):
    def node(state: InvestigationState) -> dict:
        if state.get("failed") and agent != "supervisor":
            return {}
        session = _session()
        try:
            with session.begin_nested():
                with span("agent.node", **{"agent.name": agent}):
                    return function(state)
        except NetworkDenied:
            return _failed(agent, "network_denied", "Investigation tools cannot use the network.")
        except Exception:
            return _failed(agent, "agent_failed", f"{agent} failed")

    return node


def _failed(agent: str, code: str, message: str) -> dict:
    from soc_platform.agents.context import current_run
    from soc_platform.agents.memory import remember
    from soc_platform.domain.enums import AgentName, MemoryKind

    entry = remember(
        current_run(),
        agent=AgentName(agent) if agent in AgentName._value2member_map_ else AgentName.SUPERVISOR,
        kind=MemoryKind.FAILURE,
        payload={"error_code": code},
    )
    return {
        "failed": True,
        "error_code": code,
        "error_message": message,
        "memory": [entry],
    }


def _session():
    from soc_platform.agents.context import current_run

    return current_run().session
