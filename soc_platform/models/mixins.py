"""Shared mapped columns."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)


class TenantColumn:
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )


class CreatedAtColumn:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UpdatedAtColumn:
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
