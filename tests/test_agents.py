"""Agent rules that do not need PostgreSQL."""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest

from soc_platform.agents.actors import require_human
from soc_platform.agents.citations import propose, render, validate_proposal
from soc_platform.agents.drafts import store_draft
from soc_platform.agents.network import NetworkDenied, assert_local_arguments, assert_local_text
from soc_platform.agents.tools import TOOL_NAMES, ToolRegistry
from soc_platform.api.errors import ApiError
from soc_platform.domain.enums import DraftStatus

_AGENTS = Path("soc_platform/agents")
_FORBIDDEN = {"httpx", "requests", "socket", "urllib", "aiohttp", "http.client"}


def test_claim_text_is_rendered_from_the_template() -> None:
    record_id = uuid4()
    statement = render(
        "alert.summary",
        record_id,
        {"title": "Suspicious Encoded PowerShell", "severity": "high", "status": "new"},
    )
    assert str(record_id) in statement
    assert "Suspicious Encoded PowerShell" in statement
    assert "high" in statement
    with pytest.raises(ValueError):
        render("invented.fact", record_id, {})


def test_unknown_claim_template_is_rejected_without_a_database_lookup(monkeypatch) -> None:
    def explode(*_args, **_kwargs):
        raise AssertionError("a rejected template must not read the database")

    monkeypatch.setattr("soc_platform.agents.citations._stored_fields", explode)
    result = validate_proposal(None, uuid4(), propose("invented.fact", "alert", uuid4(), {}))
    assert result.reason == "unknown_template"


def test_people_are_required() -> None:
    assert require_human("  alex  ", field="actor") == "alex"
    with pytest.raises(ApiError) as caught:
        require_human("triage", field="actor")
    assert caught.value.status_code == 422


def test_urls_are_refused() -> None:
    with pytest.raises(NetworkDenied):
        assert_local_text("https://example.test/intel")
    with pytest.raises(NetworkDenied):
        assert_local_arguments({"url": "10.0.0.8"})
    assert_local_text("encoded powershell") is None


def test_tool_registry_is_a_closed_local_set() -> None:
    assert set(ToolRegistry.names) == set(TOOL_NAMES)
    for name in TOOL_NAMES:
        assert not any(word in name for word in ("http", "web", "fetch", "url", "socket"))
    with pytest.raises(PermissionError):
        ToolRegistry().call("fetch_url", url="https://example.test")


def test_agents_cannot_store_an_approved_draft() -> None:
    with pytest.raises(RuntimeError):
        store_draft(
            session=None,
            tenant_id=uuid4(),
            run_id=uuid4(),
            status=DraftStatus.APPROVED,
            title="Draft",
            claims=[],
        )


def test_agent_package_does_not_import_network_clients() -> None:
    for path in _AGENTS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".", 1)[0]]
            else:
                continue
            assert _FORBIDDEN.isdisjoint(names), path.name
