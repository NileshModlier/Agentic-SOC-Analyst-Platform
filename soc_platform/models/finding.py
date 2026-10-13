"""Analyst or platform conclusion. A finding may group alerts; it is not itself an alert."""

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
from soc_platform.domain.enums import FindingStatus, Severity
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class Finding(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_findings_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["security_cases.tenant_id", "security_cases.id"],
            name="fk_findings_case",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_findings_investigation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_findings_confidence",
        ),
        enum_check("status", FindingStatus, "ck_findings_status"),
        enum_check("severity", Severity, "ck_findings_severity"),
        Index("ix_findings_tenant_status", "tenant_id", "status"),
        {"comment": "Finding model. Conclusions reference alerts; they do not replace them."},
    )

    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[FindingStatus] = mapped_column(enum_column(FindingStatus), nullable=False)
    disposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    technique_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list, server_default=text("'{}'")
    )
    tactics: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list, server_default=text("'{}'")
    )
    created_by: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
