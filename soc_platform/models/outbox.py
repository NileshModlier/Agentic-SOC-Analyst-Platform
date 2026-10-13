"""Transactional outbox. A row is written in the same transaction as the domain change."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import OutboxStatus
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class OutboxEvent(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_outbox_events_tenant_id"),
        CheckConstraint("attempts >= 0", name="ck_outbox_events_attempts"),
        enum_check("status", OutboxStatus, "ck_outbox_events_status"),
        Index("ix_outbox_events_pending", "status", "available_at"),
        Index("ix_outbox_events_aggregate", "tenant_id", "aggregate_id"),
        {"comment": "Same-transaction publication log. Relay delivery is at-least-once."},
    )

    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(enum_column(OutboxStatus), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    redis_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
