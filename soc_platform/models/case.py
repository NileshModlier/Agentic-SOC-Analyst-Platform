"""Incident container. Table name avoids the CASE keyword."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import CaseStatus, Severity
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class Case(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "security_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_security_cases_tenant_id"),
        enum_check("status", CaseStatus, "ck_security_cases_status"),
        enum_check("severity", Severity, "ck_security_cases_severity"),
        Index("ix_security_cases_tenant_status", "tenant_id", "status"),
        {"comment": "Case model. One case may own many investigations."},
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CaseStatus] = mapped_column(enum_column(CaseStatus), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
