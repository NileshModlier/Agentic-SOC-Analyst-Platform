"""Operational detection. Distinct from an analyst finding and from the raw source bytes."""

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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import AlertStatus, Severity, SourceKind
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class Alert(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_alerts_tenant_id"),
        UniqueConstraint("tenant_id", "source_record_id", name="uq_alerts_source"),
        UniqueConstraint("tenant_id", "dedup_key", name="uq_alerts_dedup"),
        ForeignKeyConstraint(
            ["tenant_id", "source_record_id"],
            ["source_records.tenant_id", "source_records.id"],
            name="fk_alerts_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "canonical_event_id"],
            ["canonical_events.tenant_id", "canonical_events.id"],
            name="fk_alerts_canonical_event",
            ondelete="RESTRICT",
        ),
        CheckConstraint("projection_generation >= 1", name="ck_alerts_generation"),
        enum_check("source_kind", SourceKind, "ck_alerts_source_kind"),
        enum_check("severity", Severity, "ck_alerts_severity"),
        enum_check("status", AlertStatus, "ck_alerts_status"),
        Index("ix_alerts_tenant_status_detected", "tenant_id", "status", "detected_at"),
        Index("ix_alerts_tenant_correlation", "tenant_id", "correlation_key"),
        Index("ix_alerts_techniques", "technique_ids", postgresql_using="gin"),
        {"comment": "Vendor or rule detection. Workflow status survives replay."},
    )

    source_record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    canonical_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source_kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind, length=64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(enum_column(AlertStatus), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rule_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product: Mapped[str | None] = mapped_column(String(128), nullable=True)
    technique_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list, server_default=text("'{}'")
    )
    tactics: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list, server_default=text("'{}'")
    )
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    projection_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
