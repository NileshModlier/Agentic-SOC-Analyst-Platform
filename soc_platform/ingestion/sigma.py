"""Sigma rule-match alerts.

The envelope is JSON. ``rule`` carries the Sigma rule. ``event``, ``match``, or
``matched_event`` carries the log that matched. A Windows-shaped match becomes
the underlying activity event; otherwise the canonical event is a Detection Finding.
"""

from __future__ import annotations

from soc_platform.domain.canonical import DETECTION_FINDING, Attack, TechniqueRef, TacticRef, build_event, qualified_user
from soc_platform.domain.canonical import CanonicalEventDocument
from soc_platform.domain.enums import SourceKind
from soc_platform.domain.errors import IngestParseError
from soc_platform.ingestion.codec import (
    clean_external_id,
    clip,
    load_json_object,
    map_severity,
    parse_timestamp,
    techniques_from_tags,
    text_or_none,
)
from soc_platform.ingestion.types import AlertDraft, ParsedIngest
from soc_platform.ingestion.windows_event import project_windows_event


class SigmaAlertParser:
    source_kind = SourceKind.SIGMA_ALERT

    def parse(self, payload: bytes) -> ParsedIngest:
        data = load_json_object(payload)
        rule = data.get("rule") if isinstance(data.get("rule"), dict) else {}
        title = text_or_none(rule.get("title")) or text_or_none(data.get("title"))
        if title is None:
            raise IngestParseError("sigma alert is missing a title", "schema_mismatch")
        level = text_or_none(rule.get("level")) or text_or_none(data.get("level")) or text_or_none(data.get("severity"))
        severity = map_severity(level)
        tags = rule.get("tags") if isinstance(rule.get("tags"), list) else data.get("tags")
        techniques, tactics = techniques_from_tags(tags)
        description = text_or_none(rule.get("description")) or text_or_none(data.get("description"))
        rule_id = text_or_none(rule.get("id"))
        logsource = rule.get("logsource") if isinstance(rule.get("logsource"), dict) else {}
        if not logsource and isinstance(data.get("logsource"), dict):
            logsource = data["logsource"]
        product = text_or_none(logsource.get("product"))
        external_id = clean_external_id(_external_id(data, rule_id))
        matched = _matched_event(data)
        detected_at, original_time = _detected_at(data, matched)
        event = _activity_event(matched, title, severity, detected_at, original_time, techniques, tactics)
        _attach_rule(event, rule_id, techniques, tactics)
        host = event.device.hostname if event.device is not None else None
        correlation = clip(f"sigma:{rule_id or title}:{host or '-'}:{qualified_user(event.user) or '-'}", 512)
        alert = AlertDraft(
            external_id=external_id,
            title=title,
            description=description,
            severity=severity,
            detected_at=detected_at,
            rule_id=rule_id,
            rule_name=title,
            technique_ids=tuple(techniques),
            tactics=tuple(tactics),
            vendor="Sigma",
            product=product,
            correlation_key=correlation,
        )
        return ParsedIngest(external_id=external_id, event=event, alert=alert)


def _external_id(data: dict, rule_id: str | None) -> str | None:
    for key in ("alert_id", "match_id", "detection_id"):
        value = text_or_none(data.get(key))
        if value is not None:
            return value
    top_level = text_or_none(data.get("id"))
    if top_level is not None and top_level != rule_id:
        return top_level
    return None


def _matched_event(data: dict) -> dict | None:
    for key in ("event", "match", "matched_event"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return None


def _detected_at(data: dict, matched: dict | None):
    for key in ("detected_at", "timestamp", "time", "@timestamp"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            return parse_timestamp(raw, field=key), raw.strip()
    if matched is not None:
        for key in ("@timestamp", "timestamp", "time"):
            raw = matched.get(key)
            if isinstance(raw, str) and raw.strip():
                return parse_timestamp(raw, field=key), raw.strip()
        if _looks_like_windows(matched):
            try:
                extracted = extract_windows_event_from_mapping(matched)
            except IngestParseError:
                extracted = None
            if extracted is not None:
                return parse_timestamp(extracted.occurred_at_raw, field="TimeCreated"), extracted.occurred_at_raw
    raise IngestParseError("sigma alert is missing a timestamp", "missing_timestamp")


def _activity_event(matched, title, severity, detected_at, original_time, techniques, tactics):
    if matched is not None and _looks_like_windows(matched):
        try:
            projected = project_windows_event(extract_windows_event_from_mapping(matched))
        except IngestParseError:
            projected = None
        if projected is not None:
            return projected.event
    return build_event(
        event_class=DETECTION_FINDING,
        activity_id=1,
        activity_name="Create",
        severity=severity,
        status="success",
        event_time=detected_at,
        message=title,
        source_kind=SourceKind.SIGMA_ALERT.value,
        product_name="Sigma",
        product_vendor="Sigma",
        feature_name=title,
        technique_ids=techniques,
        tactics=tactics,
        unmapped={"match": matched} if matched is not None else {},
        original_time=original_time,
    )


def _attach_rule(event: CanonicalEventDocument, rule_id: str | None, techniques: list[str], tactics: list[str]) -> None:
    if rule_id is not None:
        event.unmapped["sigma_rule_id"] = rule_id
    seen_techniques = {attack.technique.uid for attack in event.attacks if attack.technique is not None}
    seen_tactics = {attack.tactic.name for attack in event.attacks if attack.tactic is not None}
    for technique in techniques:
        if technique not in seen_techniques:
            event.attacks.append(Attack(technique=TechniqueRef(uid=technique)))
            seen_techniques.add(technique)
    for tactic in tactics:
        if tactic not in seen_tactics:
            event.attacks.append(Attack(tactic=TacticRef(name=tactic)))
            seen_tactics.add(tactic)
    if event.attacks and "security_control" not in event.metadata.profiles:
        event.metadata.profiles.append("security_control")


def _looks_like_windows(data: dict) -> bool:
    if isinstance(data.get("winlog"), dict) or isinstance(data.get("Event"), dict):
        return True
    system = data.get("System")
    return isinstance(system, dict) and "EventID" in system


def extract_windows_event_from_mapping(data: dict):
    from soc_platform.ingestion.windows_event import _from_json

    return _from_json(data)
