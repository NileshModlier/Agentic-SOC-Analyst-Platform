"""Intake operations read models. Payloads and raw source bytes are not included."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from soc_platform.api.schemas import PageInfo, PageQuery
from soc_platform.domain.enums import DeadLetterStage, OutboxStatus, SourceKind


class DeadLetterQuery(PageQuery):
    open_only: bool = Field(
        default=False,
        description="When true, return only dead letters that replay has not resolved.",
    )


class PublicationQuery(PageQuery):
    pass


class ConnectorHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SourceKind
    label: str
    projected: int
    dead_lettered: int
    last_received_at: datetime | None


class ConnectorHealthList(BaseModel):
    data: list[ConnectorHealth]


class DeadLetterRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    source_record_id: UUID | None
    outbox_event_id: UUID | None
    stage: DeadLetterStage
    reason_code: str
    error_message: str
    attempt_count: int
    payload_sha256: str | None
    created_at: datetime
    resolved_at: datetime | None


class DeadLetterList(BaseModel):
    data: list[DeadLetterRead]
    page: PageInfo


class PublicationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: str
    status: OutboxStatus
    attempts: int
    last_error: str | None
    created_at: datetime
    published_at: datetime | None


class PublicationList(BaseModel):
    data: list[PublicationRead]
    page: PageInfo
