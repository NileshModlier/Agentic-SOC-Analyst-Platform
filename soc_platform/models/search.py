"""Derived full-text rows. Replay updates them from the canonical projection."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.canonical import SEVERITY_IDS
from soc_platform.domain.enums import AlertStatus, EntityType, Outcome, Severity, SourceKind
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey

def _severity_rank(name: str) -> CheckConstraint:
    return CheckConstraint(
        f"severity_rank >= 0 AND severity_rank <= {max(SEVERITY_IDS.values())}",
        name=name,
    )


class EventSearchDocument(TenantColumn, Base):
    """One searchable projection per canonical event. ``id`` is the event id."""

    __tablename__ = "event_search_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_event_search_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "id"],
            ["canonical_events.tenant_id", "canonical_events.id"],
            name="fk_event_search_event",
            ondelete="RESTRICT",
        ),
        enum_check("source_kind", SourceKind, "ck_event_search_source"),
        enum_check("severity", Severity, "ck_event_search_severity"),
        enum_check("status", Outcome, "ck_event_search_status"),
        _severity_rank("ck_event_search_rank"),
        Index("ix_event_search_tenant_time", "tenant_id", "event_time", "id"),
        Index("ix_event_search_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_event_search_tenant_severity", "tenant_id", "severity_rank", "id"),
        Index(
            "ix_event_search_host",
            "tenant_id",
            "hostname",
            postgresql_where=sql_text("hostname IS NOT NULL"),
        ),
        Index(
            "ix_event_search_user",
            "tenant_id",
            "username",
            postgresql_where=sql_text("username IS NOT NULL"),
        ),
        Index("ix_event_search_vector", "search_vector", postgresql_using="gin"),
        {"comment": "Security search projection. Built from the canonical event, not the raw payload."},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind, length=64), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    severity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[Outcome] = mapped_column(enum_column(Outcome), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR(),
        Computed("to_tsvector('simple', search_text)", persisted=True),
        nullable=False,
    )


class AlertSearchDocument(TenantColumn, Base):
    """One searchable projection per alert. ``id`` is the alert id."""

    __tablename__ = "alert_search_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_alert_search_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "id"],
            ["alerts.tenant_id", "alerts.id"],
            name="fk_alert_search_alert",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "canonical_event_id"],
            ["canonical_events.tenant_id", "canonical_events.id"],
            name="fk_alert_search_event",
            ondelete="RESTRICT",
        ),
        enum_check("source_kind", SourceKind, "ck_alert_search_source"),
        enum_check("severity", Severity, "ck_alert_search_severity"),
        enum_check("status", AlertStatus, "ck_alert_search_status"),
        _severity_rank("ck_alert_search_rank"),
        Index("ix_alert_search_tenant_time", "tenant_id", "detected_at", "id"),
        Index("ix_alert_search_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_alert_search_tenant_severity", "tenant_id", "severity_rank", "id"),
        Index("ix_alert_search_vector", "search_vector", postgresql_using="gin"),
        {"comment": "Alert search projection. Title and Sigma rule are indexed with the linked event text."},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    canonical_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source_kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind, length=64), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    severity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(enum_column(AlertStatus), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rule_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR(),
        Computed("to_tsvector('simple', search_text)", persisted=True),
        nullable=False,
    )


class SecurityEntity(UUIDPrimaryKey, TenantColumn, Base):
    """Catalog entry for a user, host, process, file, or IP address observed in events."""

    __tablename__ = "security_entities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_security_entities_tenant_id"),
        UniqueConstraint("tenant_id", "entity_type", "value", name="uq_security_entities_value"),
        enum_check("entity_type", EntityType, "ck_security_entities_type"),
        enum_check("severity", Severity, "ck_security_entities_severity"),
        CheckConstraint("event_count >= 0", name="ck_security_entities_count"),
        _severity_rank("ck_security_entities_rank"),
        Index("ix_security_entities_tenant_seen", "tenant_id", "entity_type", "last_seen", "id"),
        Index("ix_security_entities_vector", "search_vector", postgresql_using="gin"),
        {"comment": "Entity search catalog. Counts are derived from event links."},
    )

    entity_type: Mapped[EntityType] = mapped_column(enum_column(EntityType), nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    severity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR(),
        Computed("to_tsvector('simple', search_text)", persisted=True),
        nullable=False,
    )


class EventEntity(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "event_entities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_event_entities_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "canonical_event_id",
            "entity_id",
            name="uq_event_entities_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "canonical_event_id"],
            ["canonical_events.tenant_id", "canonical_events.id"],
            name="fk_event_entities_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "entity_id"],
            ["security_entities.tenant_id", "security_entities.id"],
            name="fk_event_entities_entity",
            ondelete="RESTRICT",
        ),
        Index("ix_event_entities_event", "tenant_id", "canonical_event_id"),
        Index("ix_event_entities_entity", "tenant_id", "entity_id"),
        {"comment": "Event to entity link. Rebuilt when the canonical event is replayed."},
    )

    canonical_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
