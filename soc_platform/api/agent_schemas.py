"""Investigation workflow contracts. Drafts are not canonical records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soc_platform.api.schemas import PageInfo, PageQuery
from soc_platform.domain.enums import (
    AgentRunStatus,
    ApprovalDecision,
    CitationKind,
    DraftStatus,
    Severity,
)

DRAFT_NOTICE = (
    "This draft is not a source of truth. Approval records a human decision and does not "
    "change alerts, events, findings, cases, investigations, or evidence."
)


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: UUID | None = None
    question: str | None = Field(default=None, max_length=256)
    requested_by: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def require_subject(self) -> RunCreate:
        if self.question is not None:
            stripped = self.question.strip()
            self.question = stripped or None
        if self.alert_id is None and self.question is None:
            raise ValueError("alert_id or question is required")
        self.requested_by = self.requested_by.strip()
        return self


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecision
    actor: str = Field(min_length=1, max_length=256)
    note: str | None = Field(default=None, max_length=2000)


class CitationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CitationKind
    record_id: UUID


class ClaimRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    template: str
    statement: str
    arguments: dict
    citations: list[CitationRead]


class ApprovalRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ApprovalDecision
    actor: str
    note: str | None
    created_at: datetime


class DraftRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    run_id: UUID
    status: DraftStatus
    title: str
    summary: str
    severity: Severity
    source_of_truth: Literal[False]
    notice: str
    claims: list[ClaimRead]
    approval: ApprovalRead | None
    created_at: datetime
    updated_at: datetime


class MemoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    agent: str
    kind: str
    payload: dict


class RunListQuery(PageQuery):
    run_status: AgentRunStatus | None = Field(default=None, description="Workflow status.")
    draft_status: DraftStatus | None = Field(default=None, description="Status of the draft produced by the run.")
    alert_id: UUID | None = Field(default=None, description="Runs started for this alert.")


class DraftListQuery(PageQuery):
    status: DraftStatus | None = Field(default=None, description="Draft status.")


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    alert_id: UUID | None
    question: str | None
    status: AgentRunStatus
    error_code: str | None
    error_message: str | None
    requested_by: str
    draft_id: UUID | None
    draft_status: DraftStatus | None
    draft_title: str | None
    draft_severity: Severity | None
    created_at: datetime
    finished_at: datetime | None


class RunList(BaseModel):
    data: list[RunSummary]
    page: PageInfo


class DraftSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    run_id: UUID
    status: DraftStatus
    title: str
    summary: str
    severity: Severity
    source_of_truth: Literal[False]
    approval: ApprovalRead | None
    created_at: datetime
    updated_at: datetime


class DraftList(BaseModel):
    data: list[DraftSummary]
    page: PageInfo


class RunRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    alert_id: UUID | None
    question: str | None
    status: AgentRunStatus
    error_code: str | None
    error_message: str | None
    requested_by: str
    draft: DraftRead | None
    memory: list[MemoryRead]
    created_at: datetime
    finished_at: datetime | None
