"""Derived OCSF-aligned security event. Replay updates this row from stored bytes."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import Outcome, Severity
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class CanonicalEvent(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "canonical_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_events_tenant_id"),
        UniqueConstraint("tenant_id", "source_record_id", name="uq_canonical_events_source"),
        ForeignKeyConstraint(
            ["tenant_id", "source_record_id"],
            ["source_records.tenant_id", "source_records.id"],
            name="fk_canonical_events_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint("projection_generation >= 1", name="ck_canonical_events_generation"),
        enum_check("severity", Severity, "ck_canonical_events_severity"),
        enum_check("outcome", Outcome, "ck_canonical_events_outcome"),
        Index("ix_canonical_events_tenant_time", "tenant_id", "event_time"),
        Index(
            "ix_canonical_events_tenant_host",
            "tenant_id",
            "hostname",
            postgresql_where=text("hostname IS NOT NULL"),
        ),
        {"comment": "Derived projection. Rebuild it by replaying source_records.payload."},
    )

    source_record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    category_name: Mapped[str] = mapped_column(String(128), nullable=False)
    class_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    class_name: Mapped[str] = mapped_column(String(128), nullable=False)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_name: Mapped[str] = mapped_column(String(128), nullable=False)
    type_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    outcome: Mapped[Outcome] = mapped_column(enum_column(Outcome), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    technique_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list, server_default=text("'{}'")
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    projection_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
