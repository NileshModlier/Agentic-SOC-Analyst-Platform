"""Immutable raw intake and the mutable receipt that tracks normalization."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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
from soc_platform.domain.enums import ReceiptStatus, SourceKind
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey


class SourceRecord(UUIDPrimaryKey, TenantColumn, Base):
    """Append-only. A database trigger rejects UPDATE and DELETE."""

    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_records_tenant_id"),
        UniqueConstraint("tenant_id", "content_sha256", name="uq_source_records_hash"),
        CheckConstraint("byte_size = octet_length(payload)", name="ck_source_records_byte_size"),
        CheckConstraint(
            "content_sha256 = encode(digest(payload, 'sha256'), 'hex')",
            name="ck_source_records_sha256",
        ),
        enum_check("source_kind", SourceKind, "ck_source_records_source_kind"),
        Index("ix_source_records_tenant_received", "tenant_id", "received_at"),
        Index(
            "ix_source_records_external_id",
            "tenant_id",
            "source_kind",
            "external_id",
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        {"comment": "Immutable raw intake. Replay parses payload bytes."},
    )

    source_kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind, length=64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestReceipt(Base):
    """Latest normalization attempt for one source record."""

    __tablename__ = "ingest_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "source_record_id"],
            ["source_records.tenant_id", "source_records.id"],
            name="fk_ingest_receipts_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_ingest_receipts_attempts"),
        enum_check("status", ReceiptStatus, "ck_ingest_receipts_status"),
        {"comment": "Mutable processing state. The source record itself never changes."},
    )

    source_record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[ReceiptStatus] = mapped_column(enum_column(ReceiptStatus), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    projected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
