"""Tenant root. Every other record references a tenant through a composite foreign key."""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import TenantStatus
from soc_platform.models.mixins import CreatedAtColumn, UUIDPrimaryKey, UpdatedAtColumn


class Tenant(UUIDPrimaryKey, CreatedAtColumn, UpdatedAtColumn, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        enum_check("status", TenantStatus, "ck_tenants_status"),
        {"comment": "Isolation root. Child rows reference (tenant_id, id) pairs."},
    )

    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(enum_column(TenantStatus), nullable=False)
