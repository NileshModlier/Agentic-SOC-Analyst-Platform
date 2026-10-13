"""Cursor signing does not need PostgreSQL."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from soc_platform.api.errors import InvalidCursor
from soc_platform.api.pagination import (
    KeyCursor,
    decode_cursor,
    decode_key_cursor,
    encode_cursor,
    encode_key_cursor,
    filter_payload,
)
from soc_platform.domain.enums import Severity


def test_cursor_round_trip_is_opaque() -> None:
    filters = filter_payload({"tenant": uuid4(), "severity": Severity.HIGH, "limit": 50, "empty": None})
    row_id = uuid4()
    sort_at = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    token = encode_cursor("test-secret", resource="events", filters=filters, sort_at=sort_at, row_id=row_id)
    assert not token.startswith("{")
    assert "." in token
    position = decode_cursor("test-secret", token, resource="events", filters=filters)
    assert position.row_id == row_id
    assert position.sort_at == sort_at


def test_cursor_rejects_tampering_and_reuse() -> None:
    filters = filter_payload({"tenant": "abc", "limit": 50})
    token = encode_cursor(
        "test-secret",
        resource="events",
        filters=filters,
        sort_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        row_id=uuid4(),
    )
    with pytest.raises(InvalidCursor):
        decode_cursor("other-secret", token, resource="events", filters=filters)
    with pytest.raises(InvalidCursor):
        decode_cursor("test-secret", token, resource="alerts", filters=filters)
    with pytest.raises(InvalidCursor):
        decode_cursor("test-secret", token, resource="events", filters={**filters, "limit": 25})
    flipped = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(InvalidCursor):
        decode_cursor("test-secret", flipped, resource="events", filters=filters)


def test_search_cursor_is_a_separate_version() -> None:
    filters = filter_payload({"tenant": "abc", "sort": "severity", "limit": 50})
    row_id = uuid4()
    token = encode_key_cursor(
        "test-secret",
        resource="search_events",
        filters=filters,
        position=KeyCursor(row_id=row_id, rank=4),
    )
    position = decode_key_cursor("test-secret", token, resource="search_events", filters=filters)
    assert position.row_id == row_id
    assert position.rank == 4
    assert position.sort_at is None
    with pytest.raises(InvalidCursor):
        decode_cursor("test-secret", token, resource="search_events", filters=filters)
    listed = encode_cursor(
        "test-secret",
        resource="search_events",
        filters=filters,
        sort_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        row_id=row_id,
    )
    with pytest.raises(InvalidCursor):
        decode_key_cursor("test-secret", listed, resource="search_events", filters=filters)
