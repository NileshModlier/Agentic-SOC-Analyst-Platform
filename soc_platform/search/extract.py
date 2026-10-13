"""Pull search text and catalog entities out of a canonical event."""

from __future__ import annotations

from dataclasses import dataclass

from soc_platform.domain.enums import EntityType
from soc_platform.models import CanonicalEvent

_EMPTY = {"", "-", "(none)", "null", "none"}


@dataclass(frozen=True)
class EntityDraft:
    entity_type: EntityType
    value: str
    display_value: str


def clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.casefold() in _EMPTY:
        return None
    return text


def normalize_value(value: str) -> str:
    return " ".join(value.casefold().split())


def event_search_parts(event: CanonicalEvent) -> list[str]:
    document = event.document if isinstance(event.document, dict) else {}
    parts: list[str] = []
    _add(parts, event.username)
    _add(parts, event.hostname)
    _add(parts, event.message)
    _add(parts, _path(document, "unmapped", "sigma_rule_id"))
    process = document.get("process") if isinstance(document.get("process"), dict) else None
    if process is not None:
        _add(parts, process.get("name"))
        _add(parts, process.get("path"))
        _add(parts, process.get("cmd_line"))
        parent = process.get("parent_process") if isinstance(process.get("parent_process"), dict) else None
        if parent is not None:
            _add(parts, parent.get("name"))
            _add(parts, parent.get("path"))
    file_entity = document.get("file") if isinstance(document.get("file"), dict) else None
    if file_entity is not None:
        _add(parts, file_entity.get("name"))
        _add(parts, file_entity.get("path"))
    for address in _ip_values(document):
        _add(parts, address)
    return parts


def entity_drafts(event: CanonicalEvent) -> list[EntityDraft]:
    document = event.document if isinstance(event.document, dict) else {}
    drafts: list[EntityDraft] = []
    seen: set[tuple[str, str]] = set()

    def add(entity_type: EntityType, display: object) -> None:
        shown = clean_text(display)
        if shown is None or len(shown) > 1024:
            return
        value = normalize_value(shown)
        key = (entity_type.value, value)
        if key in seen:
            return
        seen.add(key)
        drafts.append(EntityDraft(entity_type=entity_type, value=value, display_value=shown))

    add(EntityType.USER, event.username)
    add(EntityType.HOST, event.hostname)
    process = document.get("process") if isinstance(document.get("process"), dict) else None
    if process is not None:
        add(EntityType.PROCESS, process.get("path") or process.get("name"))
        parent = process.get("parent_process") if isinstance(process.get("parent_process"), dict) else None
        if parent is not None:
            add(EntityType.PROCESS, parent.get("path") or parent.get("name"))
    file_entity = document.get("file") if isinstance(document.get("file"), dict) else None
    if file_entity is not None:
        add(EntityType.FILE, file_entity.get("path") or file_entity.get("name"))
    for address in _ip_values(document):
        add(EntityType.IP, address)
    return drafts


def _ip_values(document: dict) -> list[str]:
    found: list[str] = []
    for path in (
        ("device", "ip"),
        ("src_endpoint", "ip"),
        ("dst_endpoint", "ip"),
    ):
        _add(found, _path(document, *path))
    observables = document.get("observables")
    if isinstance(observables, list):
        for item in observables:
            if isinstance(item, dict) and item.get("type") == "ip":
                _add(found, item.get("value"))
    return found


def _path(document: dict, *keys: str) -> object:
    current: object = document
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _add(parts: list[str], value: object) -> None:
    text = clean_text(value)
    if text is not None:
        parts.append(text)
