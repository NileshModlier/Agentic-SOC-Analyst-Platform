"""Publish pending outbox rows to Redis Streams.

Delivery is at-least-once. The row is marked published only after ``XADD``
returns. A crash between those steps publishes the same outbox id again.
Consumers dedupe on that id. The relay role is expected to bypass row-level
security; request-scoped roles must not.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from soc_platform.db.session import database_now
from soc_platform.observability.metrics import record_outbox_failure
from soc_platform.observability.tracing import traced
from soc_platform.domain.enums import DeadLetterStage, OutboxStatus
from soc_platform.models import DeadLetter, OutboxEvent
from soc_platform.models.mixins import new_uuid

logger = logging.getLogger(__name__)


class RedisStreams(Protocol):
    def xadd(self, name: str, fields: dict[str, str]) -> str | bytes: ...


@traced("outbox.publish")
def publish_pending(
    session: Session,
    redis: RedisStreams,
    *,
    stream: str,
    batch_size: int,
    max_attempts: int,
) -> int:
    rows = session.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxStatus.PENDING,
            OutboxEvent.available_at <= func.clock_timestamp(),
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    handled = 0
    for row in rows:
        handled += 1
        fields = {
            "event_id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "event_type": row.event_type,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": str(row.aggregate_id),
            "payload": json.dumps(row.payload, separators=(",", ":"), sort_keys=True),
        }
        try:
            message_id = redis.xadd(stream, fields)
        except Exception as exc:
            if not _is_publish_failure(exc):
                raise
            _record_failure(session, row, exc, max_attempts=max_attempts)
            continue
        row.status = OutboxStatus.PUBLISHED
        row.published_at = database_now(session)
        row.redis_message_id = _message_id(message_id)
        row.last_error = None
    session.flush()
    return handled


def _record_failure(session: Session, row: OutboxEvent, exc: Exception, *, max_attempts: int) -> None:
    record_outbox_failure()
    row.attempts += 1
    row.last_error = str(exc)[:2000]
    if row.attempts >= max_attempts:
        row.status = OutboxStatus.DEAD_LETTERED
        session.add(
            DeadLetter(
                id=new_uuid(),
                tenant_id=row.tenant_id,
                source_record_id=row.aggregate_id if row.aggregate_type == "source_record" else None,
                outbox_event_id=row.id,
                stage=DeadLetterStage.PUBLISH,
                reason_code="publish_exhausted",
                error_message=row.last_error,
                attempt_count=row.attempts,
                payload_bytes=None,
                payload_sha256=None,
                created_at=database_now(session),
                resolved_at=None,
            )
        )
        logger.warning(
            "outbox dead-lettered event_id=%s tenant_id=%s attempts=%s",
            row.id,
            row.tenant_id,
            row.attempts,
        )
        return
    delay = min(60, 2**row.attempts)
    row.available_at = database_now(session) + timedelta(seconds=delay)
    logger.warning(
        "outbox publish failed event_id=%s tenant_id=%s attempts=%s",
        row.id,
        row.tenant_id,
        row.attempts,
    )


def _is_publish_failure(exc: Exception) -> bool:
    try:
        from redis.exceptions import RedisError
    except ImportError:
        RedisError = ()  # type: ignore[assignment]
    return isinstance(exc, (OSError, RedisError))


def _message_id(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
