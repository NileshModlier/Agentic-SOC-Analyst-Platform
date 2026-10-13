"""Durable failure record for parse, replay, and publication."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import DeadLetterStage
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class DeadLetter(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "dead_letters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_dead_letters_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "source_record_id"],
            ["source_records.tenant_id", "source_records.id"],
            name="fk_dead_letters_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "outbox_event_id"],
            ["outbox_events.tenant_id", "outbox_events.id"],
            name="fk_dead_letters_outbox",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_record_id IS NOT NULL OR outbox_event_id IS NOT NULL OR payload_bytes IS NOT NULL",
            name="ck_dead_letters_has_body",
        ),
        CheckConstraint(
            "payload_bytes IS NULL OR payload_sha256 = encode(digest(payload_bytes, 'sha256'), 'hex')",
            name="ck_dead_letters_sha256",
        ),
        CheckConstraint("attempt_count >= 1", name="ck_dead_letters_attempts"),
        enum_check("stage", DeadLetterStage, "ck_dead_letters_stage"),
        Index(
            "ix_dead_letters_open",
            "tenant_id",
            "created_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        {"comment": "Dead-letter support. Resolve by replay; do not delete the row."},
    )

    source_record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    stage: Mapped[DeadLetterStage] = mapped_column(enum_column(DeadLetterStage), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
