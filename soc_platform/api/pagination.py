"""Opaque keyset cursors.

A cursor is an HMAC over the resource, the filters that produced the page, and
the sort position of the last returned row. It is not an offset. Changing
tenant, filters, or page size makes the cursor invalid.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from soc_platform.api.errors import InvalidCursor

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
_CURSOR_VERSION = 1
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CursorPosition:
    sort_at: datetime
    row_id: UUID


@dataclass(frozen=True)
class KeyCursor:
    """Keyset position for a search page. Time sorts set ``sort_at``. Severity sets ``rank``."""

    row_id: UUID
    sort_at: datetime | None = None
    rank: int | None = None


def filter_payload(values: dict[str, Any]) -> dict[str, Any]:
    """Stable JSON-ready filter set. None values are omitted."""
    payload: dict[str, Any] = {}
    for key in sorted(values):
        value = values[key]
        if value is None:
            continue
        if isinstance(value, datetime):
            payload[key] = value.astimezone(timezone.utc).isoformat()
        elif isinstance(value, enum.Enum):
            payload[key] = value.value
        elif isinstance(value, UUID):
            payload[key] = str(value)
        else:
            payload[key] = value
    return payload


def encode_cursor(
    secret: str,
    *,
    resource: str,
    filters: dict[str, Any],
    sort_at: datetime,
    row_id: UUID,
) -> str:
    if not secret:
        raise RuntimeError("api cursor secret is empty")
    body = {
        "v": _CURSOR_VERSION,
        "resource": resource,
        "filters": filters,
        "us": _to_microseconds(sort_at),
        "id": str(row_id),
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return f"{_encode(raw)}.{_encode(signature)}"


def decode_cursor(
    secret: str,
    token: str,
    *,
    resource: str,
    filters: dict[str, Any],
) -> CursorPosition:
    try:
        encoded_body, encoded_signature = token.split(".", 1)
        raw = _decode(encoded_body)
        signature = _decode(encoded_signature)
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidCursor
        body = json.loads(raw)
        if body.get("v") != _CURSOR_VERSION or body.get("resource") != resource:
            raise InvalidCursor
        if body.get("filters") != filters:
            raise InvalidCursor
        row_id = UUID(body["id"])
        sort_at = _from_microseconds(int(body["us"]))
    except InvalidCursor:
        raise
    except Exception as exc:
        raise InvalidCursor from exc
    return CursorPosition(sort_at=sort_at, row_id=row_id)


def encode_key_cursor(
    secret: str,
    *,
    resource: str,
    filters: dict[str, Any],
    position: KeyCursor,
) -> str:
    if not secret:
        raise RuntimeError("api cursor secret is empty")
    if position.sort_at is None and position.rank is None:
        raise RuntimeError("search cursor requires a sort position")
    body = {
        "v": 2,
        "resource": resource,
        "filters": filters,
        "us": None if position.sort_at is None else _to_microseconds(position.sort_at),
        "rank": position.rank,
        "id": str(position.row_id),
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return f"{_encode(raw)}.{_encode(signature)}"


def decode_key_cursor(
    secret: str,
    token: str,
    *,
    resource: str,
    filters: dict[str, Any],
) -> KeyCursor:
    try:
        encoded_body, encoded_signature = token.split(".", 1)
        raw = _decode(encoded_body)
        signature = _decode(encoded_signature)
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidCursor
        body = json.loads(raw)
        if body.get("v") != 2 or body.get("resource") != resource or body.get("filters") != filters:
            raise InvalidCursor
        sort_at = None if body.get("us") is None else _from_microseconds(int(body["us"]))
        rank = None if body.get("rank") is None else int(body["rank"])
        if sort_at is None and rank is None:
            raise InvalidCursor
        return KeyCursor(row_id=UUID(body["id"]), sort_at=sort_at, rank=rank)
    except InvalidCursor:
        raise
    except Exception as exc:
        raise InvalidCursor from exc


def _to_microseconds(value: datetime) -> int:
    utc = value.astimezone(timezone.utc)
    return (utc - _EPOCH) // timedelta(microseconds=1)


def _from_microseconds(value: int) -> datetime:
    return _EPOCH + timedelta(microseconds=value)


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
