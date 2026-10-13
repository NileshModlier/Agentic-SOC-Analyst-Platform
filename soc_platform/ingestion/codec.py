"""Byte decoding and small deterministic parsers shared by intake normalizers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from soc_platform.domain.errors import IngestParseError

_FRACTION = re.compile(r"\.(\d+)")
_OFFSET_NO_COLON = re.compile(r"([+-]\d{2})(\d{2})$")
_BLANK = {"", "-", "null", "none", "(none)"}


def decode_text(payload: bytes) -> str:
    if len(payload) == 0:
        raise IngestParseError("payload is empty", "empty_payload")
    if payload.startswith(b"\xff\xfe") or payload.startswith(b"\xfe\xff"):
        try:
            return payload.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise IngestParseError("payload is not valid UTF-16 text", "invalid_encoding") from exc
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestParseError("payload is not valid UTF-8 text", "invalid_encoding") from exc


def sniff_content_type(payload: bytes) -> str:
    try:
        text = decode_text(payload)
    except IngestParseError:
        return "application/octet-stream"
    stripped = text.lstrip("\ufeff \t\r\n")
    if stripped.startswith("<"):
        return "application/xml"
    if stripped.startswith("{"):
        return "application/json"
    return "application/octet-stream"


def load_json_object(payload: bytes) -> dict:
    text = decode_text(payload)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestParseError("payload is not valid JSON", "invalid_json") from exc
    if not isinstance(value, dict):
        raise IngestParseError("payload JSON must be an object", "schema_mismatch")
    return value


def parse_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IngestParseError(f"missing {field}", "missing_timestamp")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    match = _FRACTION.search(raw)
    if match and len(match.group(1)) > 6:
        raw = raw[: match.start(1)] + match.group(1)[:6] + raw[match.end(1) :]
    offset = _OFFSET_NO_COLON.search(raw)
    if offset and "T" in raw:
        raw = raw[: offset.start()] + offset.group(1) + ":" + offset.group(2)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise IngestParseError(f"invalid {field}", "invalid_timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def text_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.lower() in _BLANK:
        return None
    return cleaned


def clean_external_id(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 256:
        raise IngestParseError("external id exceeds 256 characters", "schema_mismatch")
    return value


def techniques_from_tags(tags: object) -> tuple[list[str], list[str]]:
    if not isinstance(tags, list):
        return [], []
    techniques: list[str] = []
    tactics: list[str] = []
    seen_techniques: set[str] = set()
    seen_tactics: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        lowered = tag.strip().lower()
        if not lowered.startswith("attack."):
            continue
        body = lowered.removeprefix("attack.")
        if body.startswith("t") and len(body) > 1 and body[1].isdigit():
            technique = body.upper()
            if technique not in seen_techniques:
                seen_techniques.add(technique)
                techniques.append(technique)
            continue
        if body and body not in seen_tactics:
            seen_tactics.add(body)
            tactics.append(body)
    return techniques, tactics


def map_severity(value: str | None, *, default: str = "informational") -> str:
    if value is None:
        return default
    normalized = value.strip().lower()
    table = {
        "informational": "informational",
        "info": "informational",
        "information": "informational",
        "low": "low",
        "medium": "medium",
        "med": "medium",
        "high": "high",
        "critical": "critical",
        "crit": "critical",
        "unknown": "unknown",
    }
    if normalized not in table:
        raise IngestParseError(f"unsupported severity {value}", "schema_mismatch")
    return table[normalized]


def parse_windows_pid(value: str | None) -> int | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw or raw == "-":
        return None
    try:
        return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return None


def parse_port(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        port = int(value)
    except ValueError:
        return None
    if port < 0 or port > 65535:
        return None
    return port


_HASH_IDS = {"md5": 1, "sha1": 2, "sha256": 3, "sha-1": 2, "sha-256": 3}


def parse_hash_list(value: str | None) -> list[tuple[str, int | None, str]]:
    if value is None:
        return []
    found: list[tuple[str, int | None, str]] = []
    for part in value.split(","):
        if "=" not in part:
            continue
        algorithm, digest = part.split("=", 1)
        algorithm = algorithm.strip()
        digest = digest.strip().lower()
        if not algorithm or not digest or digest in _BLANK:
            continue
        found.append((algorithm.upper().replace("SHA256", "SHA-256").replace("SHA1", "SHA-1"), _HASH_IDS.get(algorithm.lower()), digest))
    return found


def clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[:limit]
