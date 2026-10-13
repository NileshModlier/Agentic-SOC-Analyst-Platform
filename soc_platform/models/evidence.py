"""Custody record for raw bytes, plus mutable links into casework."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import EvidenceType
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class Evidence(UUIDPrimaryKey, TenantColumn, Base):
    """Append-only custody artifact. A trigger rejects UPDATE and DELETE."""

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evidence_tenant_id"),
        UniqueConstraint("tenant_id", "source_record_id", name="uq_evidence_source"),
        ForeignKeyConstraint(
            ["tenant_id", "source_record_id"],
            ["source_records.tenant_id", "source_records.id"],
            name="fk_evidence_source",
            ondelete="RESTRICT",
        ),
        enum_check("evidence_type", EvidenceType, "ck_evidence_type"),
        {"comment": "Immutable custody record. Associations live in evidence_links."},
    )

    source_record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_type: Mapped[EvidenceType] = mapped_column(enum_column(EvidenceType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_by: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceLink(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evidence_links_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["evidence.tenant_id", "evidence.id"],
            name="fk_evidence_links_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "alert_id"],
            ["alerts.tenant_id", "alerts.id"],
            name="fk_evidence_links_alert",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "canonical_event_id"],
            ["canonical_events.tenant_id", "canonical_events.id"],
            name="fk_evidence_links_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["findings.tenant_id", "findings.id"],
            name="fk_evidence_links_finding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_evidence_links_investigation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["security_cases.tenant_id", "security_cases.id"],
            name="fk_evidence_links_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "alert_id IS NOT NULL OR canonical_event_id IS NOT NULL OR finding_id IS NOT NULL "
            "OR investigation_id IS NOT NULL OR case_id IS NOT NULL",
            name="ck_evidence_links_has_target",
        ),
        {"comment": "Mutable association from an immutable evidence artifact to casework."},
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    alert_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    canonical_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    linked_by: Mapped[str] = mapped_column(String(256), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
