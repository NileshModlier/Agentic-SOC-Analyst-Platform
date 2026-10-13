"""Read-only tools. The registry has no network tool and cannot grow one at call time."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select

from soc_platform.agents.network import assert_local_arguments
from soc_platform.api.errors import ResourceNotFound
from soc_platform.api.queries import get_alert, get_event
from soc_platform.api.reader import ReadContext, assert_reader
from soc_platform.api.search_queries import search_alerts, search_entities, search_events
from soc_platform.api.search_schemas import AlertSearchQuery, EntitySearchQuery, EventSearchQuery
from soc_platform.domain.enums import EntityType
from soc_platform.models import Evidence, EvidenceLink, SecurityEntity
from soc_platform.search.extract import entity_drafts, normalize_value

TOOL_NAMES = (
    "get_alert",
    "get_event",
    "search_alerts",
    "search_events",
    "search_entities",
    "get_entity",
    "get_entity_by_value",
    "event_entity_keys",
    "list_alert_evidence",
)
_MAX_HITS = 5


@dataclass(frozen=True)
class ToolRecord:
    kind: str
    id: UUID
    fields: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    name: str
    records: list[ToolRecord] = field(default_factory=list)
    error: str | None = None


class ToolRegistry:
    """Closed set of local reads. `call` rejects every name outside TOOL_NAMES."""

    names = TOOL_NAMES

    def call(self, name: str, **arguments: Any) -> ToolResult:
        if name not in TOOL_NAMES:
            raise PermissionError(f"tool {name} is not available to investigation agents")
        assert_local_arguments(arguments)
        method = getattr(self, name)
        return method(**arguments)

    def get_alert(self, *, alert_id: str) -> ToolResult:
        return _one("get_alert", "alert", _parse_id(alert_id), _load_alert)

    def get_event(self, *, event_id: str) -> ToolResult:
        return _one("get_event", "event", _parse_id(event_id), _load_event)

    def get_entity(self, *, entity_id: str) -> ToolResult:
        parsed = _parse_id(entity_id)
        if isinstance(parsed, ToolResult):
            return parsed
        context = _context()
        assert_reader(context.session, context.tenant_id)
        row = context.session.scalar(
            select(SecurityEntity).where(
                SecurityEntity.tenant_id == context.tenant_id,
                SecurityEntity.id == parsed,
            )
        )
        if row is None:
            return ToolResult("get_entity", error="not_found")
        return ToolResult("get_entity", [_entity_record(row)])

    def get_entity_by_value(self, *, entity_type: str, value: str) -> ToolResult:
        try:
            kind = EntityType(entity_type)
        except ValueError:
            return ToolResult("get_entity_by_value", error="invalid_entity_type")
        context = _context()
        assert_reader(context.session, context.tenant_id)
        row = context.session.scalar(
            select(SecurityEntity).where(
                SecurityEntity.tenant_id == context.tenant_id,
                SecurityEntity.entity_type == kind,
                SecurityEntity.value == normalize_value(value),
            )
        )
        if row is None:
            return ToolResult("get_entity_by_value", error="not_found")
        return ToolResult("get_entity_by_value", [_entity_record(row)])

    def search_alerts(self, *, q: str, limit: int = _MAX_HITS) -> ToolResult:
        return _search("search_alerts", q, limit, _alert_search)

    def search_events(self, *, q: str, limit: int = _MAX_HITS) -> ToolResult:
        return _search("search_events", q, limit, _event_search)

    def search_entities(self, *, q: str, limit: int = _MAX_HITS, entity_type: str | None = None) -> ToolResult:
        context = _context()
        prepared = _query(q)
        if prepared is None:
            return ToolResult("search_entities", error="query_required")
        kind = None
        if entity_type is not None:
            try:
                kind = EntityType(entity_type)
            except ValueError:
                return ToolResult("search_entities", error="invalid_entity_type")
        page = search_entities(
            ReadContext(context.session, context.tenant_id),
            EntitySearchQuery(tenant=context.tenant_id, q=prepared, limit=_cap(limit), entity_type=kind),
            context.cursor_secret,
        )
        records = []
        for hit in page.data:
            loaded = self.get_entity(entity_id=str(hit.id))
            records.extend(loaded.records)
        return ToolResult("search_entities", records[:_MAX_HITS])

    def event_entity_keys(self, *, event_id: str) -> ToolResult:
        parsed = _parse_id(event_id)
        if isinstance(parsed, ToolResult):
            return parsed
        context = _context()
        assert_reader(context.session, context.tenant_id)
        from soc_platform.models import CanonicalEvent

        event = context.session.scalar(
            select(CanonicalEvent).where(
                CanonicalEvent.tenant_id == context.tenant_id,
                CanonicalEvent.id == parsed,
            )
        )
        if event is None:
            return ToolResult("event_entity_keys", error="not_found")
        keys = [
            {"entity_type": draft.entity_type.value, "value": draft.value, "display_value": draft.display_value}
            for draft in entity_drafts(event)
        ]
        return ToolResult(
            "event_entity_keys",
            [ToolRecord("event", parsed, {"keys": keys})],
        )

    def list_alert_evidence(self, *, alert_id: str) -> ToolResult:
        parsed = _parse_id(alert_id)
        if isinstance(parsed, ToolResult):
            return parsed
        context = _context()
        assert_reader(context.session, context.tenant_id)
        rows = context.session.scalars(
            select(Evidence)
            .join(
                EvidenceLink,
                and_(
                    EvidenceLink.tenant_id == Evidence.tenant_id,
                    EvidenceLink.evidence_id == Evidence.id,
                ),
            )
            .where(Evidence.tenant_id == context.tenant_id, EvidenceLink.alert_id == parsed)
            .limit(_MAX_HITS)
        ).all()
        return ToolResult("list_alert_evidence", [_evidence_record(row) for row in rows])


def _context():
    from soc_platform.agents.context import current_run

    return current_run()


def _one(name: str, kind: str, parsed: UUID | ToolResult, loader) -> ToolResult:
    if isinstance(parsed, ToolResult):
        return ToolResult(name, error=parsed.error)
    try:
        record = loader(parsed)
    except ResourceNotFound:
        return ToolResult(name, error="not_found")
    return ToolResult(name, [record])


def _load_alert(alert_id: UUID) -> ToolRecord:
    context = _context()
    row = get_alert(ReadContext(context.session, context.tenant_id), alert_id)
    return ToolRecord(
        "alert",
        row.id,
        {
            "title": row.title,
            "severity": row.severity.value,
            "status": row.status.value,
            "technique_ids": list(row.technique_ids or []),
            "rule_id": row.rule_id,
            "canonical_event_id": None if row.canonical_event_id is None else str(row.canonical_event_id),
        },
    )


def _load_event(event_id: UUID) -> ToolRecord:
    context = _context()
    row = get_event(ReadContext(context.session, context.tenant_id), event_id)
    return ToolRecord(
        "event",
        row.id,
        {
            "message": row.message,
            "severity": row.severity.value,
            "event_type": row.class_name,
            "hostname": row.hostname,
            "username": row.username,
        },
    )


def _entity_record(row: SecurityEntity) -> ToolRecord:
    return ToolRecord(
        "entity",
        row.id,
        {
            "entity_type": row.entity_type.value,
            "display_value": row.display_value,
            "value": row.value,
            "event_count": row.event_count,
            "severity": row.severity.value,
        },
    )


def _evidence_record(row: Evidence) -> ToolRecord:
    return ToolRecord(
        "evidence",
        row.id,
        {"content_sha256": row.content_sha256, "evidence_type": row.evidence_type.value},
    )


def _search(name: str, q: str, limit: int, runner) -> ToolResult:
    prepared = _query(q)
    if prepared is None:
        return ToolResult(name, error="query_required")
    context = _context()
    page = runner(context, prepared, _cap(limit))
    records: list[ToolRecord] = []
    for hit in page.data:
        if name == "search_alerts":
            loaded = _one("get_alert", "alert", hit.id, _load_alert)
        else:
            loaded = _one("get_event", "event", hit.id, _load_event)
        records.extend(loaded.records)
        if len(records) >= _MAX_HITS:
            break
    return ToolResult(name, records)


def _alert_search(context, q: str, limit: int):
    return search_alerts(
        ReadContext(context.session, context.tenant_id),
        AlertSearchQuery(tenant=context.tenant_id, q=q, limit=limit),
        context.cursor_secret,
    )


def _event_search(context, q: str, limit: int):
    return search_events(
        ReadContext(context.session, context.tenant_id),
        EventSearchQuery(tenant=context.tenant_id, q=q, limit=limit),
        context.cursor_secret,
    )


def _parse_id(value: str) -> UUID | ToolResult:
    try:
        return UUID(str(value))
    except ValueError:
        return ToolResult("parse", error="invalid_id")


def _query(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:256]


def _cap(limit: int) -> int:
    return max(1, min(int(limit), _MAX_HITS))
