"""Unit of analysis. Belongs to at most one case."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import InvestigationStatus, Priority
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class Investigation(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "investigations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_investigations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["security_cases.tenant_id", "security_cases.id"],
            name="fk_investigations_case",
            ondelete="RESTRICT",
        ),
        enum_check("status", InvestigationStatus, "ck_investigations_status"),
        enum_check("priority", Priority, "ck_investigations_priority"),
        Index("ix_investigations_tenant_status", "tenant_id", "status"),
        {"comment": "Investigation model. Hypotheses are mutable; linked evidence is not."},
    )

    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[InvestigationStatus] = mapped_column(enum_column(InvestigationStatus), nullable=False)
    priority: Mapped[Priority] = mapped_column(enum_column(Priority), nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(256), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
