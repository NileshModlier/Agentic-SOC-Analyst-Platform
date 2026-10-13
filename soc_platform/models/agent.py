"""Investigation workspace. These rows are drafts, not canonical records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from soc_platform.db.base import Base
from soc_platform.db.types import enum_check, enum_column
from soc_platform.domain.enums import (
    AgentName,
    AgentRunStatus,
    ApprovalDecision,
    CitationKind,
    DraftStatus,
    MemoryKind,
    Severity,
)
from soc_platform.models.mixins import TenantColumn, UUIDPrimaryKey

CLAIM_TEMPLATES = (
    "alert.summary",
    "alert.technique",
    "alert.no_technique",
    "event.summary",
    "entity.summary",
    "evidence.custody",
)


class AgentRun(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id"),
        enum_check("status", AgentRunStatus, "ck_agent_runs_status"),
        Index("ix_agent_runs_tenant_created", "tenant_id", "created_at"),
        {"comment": "One investigation workflow. The run is workspace state, not a finding."},
    )

    alert_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(enum_column(AgentRunStatus), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMemory(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_memories_tenant_id"),
        UniqueConstraint("tenant_id", "run_id", "sequence", name="uq_agent_memories_sequence"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_memories_run",
            ondelete="RESTRICT",
        ),
        enum_check("agent", AgentName, "ck_agent_memories_agent"),
        enum_check("kind", MemoryKind, "ck_agent_memories_kind"),
        CheckConstraint("sequence >= 1", name="ck_agent_memories_sequence"),
        Index("ix_agent_memories_run", "tenant_id", "run_id", "sequence"),
        {"comment": "Agent workspace memory. Observations are not canonical facts."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    agent: Mapped[AgentName] = mapped_column(enum_column(AgentName), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[MemoryKind] = mapped_column(enum_column(MemoryKind), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvestigationDraft(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "investigation_drafts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_investigation_drafts_tenant_id"),
        UniqueConstraint("tenant_id", "run_id", name="uq_investigation_drafts_run"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_investigation_drafts_run",
            ondelete="RESTRICT",
        ),
        enum_check("status", DraftStatus, "ck_investigation_drafts_status"),
        enum_check("severity", Severity, "ck_investigation_drafts_severity"),
        CheckConstraint("source_of_truth = false", name="ck_investigation_drafts_not_truth"),
        Index("ix_investigation_drafts_status", "tenant_id", "status"),
        {"comment": "Cited investigation draft. Approval does not write a finding."},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[DraftStatus] = mapped_column(enum_column(DraftStatus), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(enum_column(Severity), nullable=False)
    source_of_truth: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DraftClaim(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "draft_claims"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_draft_claims_tenant_id"),
        UniqueConstraint("tenant_id", "draft_id", "position", name="uq_draft_claims_position"),
        ForeignKeyConstraint(
            ["tenant_id", "draft_id"],
            ["investigation_drafts.tenant_id", "investigation_drafts.id"],
            name="fk_draft_claims_draft",
            ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="ck_draft_claims_position"),
        CheckConstraint(
            "template IN (" + ", ".join(f"'{item}'" for item in CLAIM_TEMPLATES) + ")",
            name="ck_draft_claims_template",
        ),
        Index("ix_draft_claims_draft", "tenant_id", "draft_id", "position"),
        {"comment": "A claim rendered from a stored record. The statement is not free text."},
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)


class DraftCitation(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "draft_citations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_draft_citations_tenant_id"),
        UniqueConstraint("tenant_id", "claim_id", name="uq_draft_citations_claim"),
        ForeignKeyConstraint(
            ["tenant_id", "draft_id"],
            ["investigation_drafts.tenant_id", "investigation_drafts.id"],
            name="fk_draft_citations_draft",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "claim_id"],
            ["draft_claims.tenant_id", "draft_claims.id"],
            name="fk_draft_citations_claim",
            ondelete="RESTRICT",
        ),
        enum_check("kind", CitationKind, "ck_draft_citations_kind"),
        Index("ix_draft_citations_record", "tenant_id", "kind", "record_id"),
        {"comment": "Citation to one stored record in this tenant."},
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[CitationKind] = mapped_column(enum_column(CitationKind), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class DraftApproval(UUIDPrimaryKey, TenantColumn, Base):
    __tablename__ = "draft_approvals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_draft_approvals_tenant_id"),
        UniqueConstraint("tenant_id", "draft_id", name="uq_draft_approvals_draft"),
        ForeignKeyConstraint(
            ["tenant_id", "draft_id"],
            ["investigation_drafts.tenant_id", "investigation_drafts.id"],
            name="fk_draft_approvals_draft",
            ondelete="RESTRICT",
        ),
        enum_check("decision", ApprovalDecision, "ck_draft_approvals_decision"),
        {"comment": "Human decision. Agents cannot insert this row."},
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(enum_column(ApprovalDecision), nullable=False)
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
