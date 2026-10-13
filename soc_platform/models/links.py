"""Associations that must stay inside a single tenant."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class FindingAlert(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "finding_alerts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_finding_alerts_tenant_id"),
        UniqueConstraint("tenant_id", "finding_id", "alert_id", name="uq_finding_alerts_pair"),
        ForeignKeyConstraint(
            ["tenant_id", "finding_id"],
            ["findings.tenant_id", "findings.id"],
            name="fk_finding_alerts_finding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "alert_id"],
            ["alerts.tenant_id", "alerts.id"],
            name="fk_finding_alerts_alert",
            ondelete="RESTRICT",
        ),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    alert_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    linked_by: Mapped[str] = mapped_column(String(256), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvestigationAlert(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "investigation_alerts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_investigation_alerts_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "investigation_id",
            "alert_id",
            name="uq_investigation_alerts_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_investigation_alerts_investigation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "alert_id"],
            ["alerts.tenant_id", "alerts.id"],
            name="fk_investigation_alerts_alert",
            ondelete="RESTRICT",
        ),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    alert_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    linked_by: Mapped[str] = mapped_column(String(256), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
