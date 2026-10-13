"""Read models and query contracts. These shapes are the OpenAPI response contract."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from soc_platform.api.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from soc_platform.domain.enums import (
    AlertStatus,
    CaseStatus,
    EvidenceType,
    FindingStatus,
    InvestigationStatus,
    Outcome,
    Priority,
    Severity,
    SourceKind,
)


class ErrorDetail(BaseModel):
    loc: list[str]
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class PageInfo(BaseModel):
    """Keyset page. `limit` is the requested page size, not the number of rows returned."""

    limit: int
    has_more: bool
    next_cursor: str | None = None


class TimeWindow(BaseModel):
    start: datetime | None = Field(
        default=None,
        description="Inclusive lower bound of the resource time range. A timezone offset is required.",
    )
    end: datetime | None = Field(
        default=None,
        description="Exclusive upper bound of the resource time range. A timezone offset is required.",
    )

    @model_validator(mode="after")
    def check_window(self) -> TimeWindow:
        for label, value in (("start", self.start), ("end", self.end)):
            if value is not None and value.utcoffset() is None:
                raise ValueError(f"{label} must include a timezone offset")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class PageQuery(TimeWindow):
    tenant: UUID = Field(
        description="Tenant scope. Required on every request. Row-level security is set to this tenant."
    )
    limit: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum rows to return. Default 50. Maximum 100.",
    )
    cursor: str | None = Field(
        default=None,
        max_length=4096,
        description="Opaque cursor from the previous page. It is bound to this resource, tenant, filters, and limit.",
    )


class EventListQuery(PageQuery):
    source: SourceKind | None = Field(default=None, description="Intake source kind.")
    severity: Severity | None = Field(default=None, description="OCSF severity.")
    event_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="OCSF class name, for example Authentication or Process Activity. Match is case-sensitive.",
        examples=["Authentication"],
    )

    @model_validator(mode="after")
    def strip_event_type(self) -> EventListQuery:
        if self.event_type is not None:
            stripped = self.event_type.strip()
            if not stripped:
                raise ValueError("event_type must not be empty")
            self.event_type = stripped
        return self


class AlertListQuery(PageQuery):
    source: SourceKind | None = Field(default=None, description="Intake source kind.")
    severity: Severity | None = Field(default=None, description="Alert severity.")
    alert_status: AlertStatus | None = Field(default=None, description="Alert workflow status.")


class FindingListQuery(PageQuery):
    severity: Severity | None = Field(default=None, description="Finding severity.")


class CaseListQuery(PageQuery):
    severity: Severity | None = Field(default=None, description="Case severity.")
    case_status: CaseStatus | None = Field(default=None, description="Case status.")


class InvestigationListQuery(PageQuery):
    investigation_status: InvestigationStatus | None = Field(
        default=None, description="Investigation status."
    )


class EvidenceListQuery(PageQuery):
    source: SourceKind | None = Field(default=None, description="Intake source kind of the underlying record.")


class EventRead(BaseModel):
    """Canonical security event summary. The OCSF document is returned by the detail operation."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    source_record_id: UUID
    source: SourceKind
    event_time: datetime
    category_uid: int
    category_name: str
    class_uid: int
    class_name: str
    activity_id: int
    activity_name: str
    type_uid: int
    severity: Severity
    outcome: Outcome
    hostname: str | None
    username: str | None
    message: str
    technique_ids: list[str]
    schema_version: str
    normalizer_version: str
    projection_generation: int
    created_at: datetime
    updated_at: datetime


class EventDetail(EventRead):
    document: dict


class EventList(BaseModel):
    data: list[EventRead]
    page: PageInfo


class AlertRead(BaseModel):
    """Operational detection. Distinct from a finding and from the raw source bytes."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    source_record_id: UUID
    canonical_event_id: UUID | None
    source: SourceKind
    external_id: str | None
    title: str
    description: str | None
    severity: Severity
    status: AlertStatus
    rule_id: str | None
    rule_name: str | None
    vendor: str | None
    product: str | None
    technique_ids: list[str]
    tactics: list[str]
    dedup_key: str
    correlation_key: str | None
    detected_at: datetime
    projection_generation: int
    created_at: datetime
    updated_at: datetime


class AlertList(BaseModel):
    data: list[AlertRead]
    page: PageInfo


class FindingRead(BaseModel):
    """Analyst or platform conclusion."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    case_id: UUID | None
    investigation_id: UUID | None
    title: str
    summary: str | None
    severity: Severity
    confidence: int | None
    status: FindingStatus
    disposition: str | None
    technique_ids: list[str]
    tactics: list[str]
    created_by: str
    created_at: datetime
    updated_at: datetime


class FindingDetail(FindingRead):
    alert_ids: list[UUID] = Field(description="Linked alerts, oldest link first.")


class FindingList(BaseModel):
    data: list[FindingRead]
    page: PageInfo


class InvestigationRead(BaseModel):
    """Unit of analysis. Belongs to at most one case."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    case_id: UUID | None
    title: str
    status: InvestigationStatus
    priority: Priority
    hypothesis: str | None
    summary: str | None
    assignee: str | None
    opened_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InvestigationDetail(InvestigationRead):
    alert_ids: list[UUID] = Field(description="Linked alerts, oldest link first.")


class InvestigationList(BaseModel):
    data: list[InvestigationRead]
    page: PageInfo


class CaseRead(BaseModel):
    """Incident container."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    title: str
    description: str | None
    status: CaseStatus
    severity: Severity
    assignee: str | None
    external_ref: str | None
    opened_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CaseDetail(CaseRead):
    investigation_ids: list[UUID] = Field(description="Investigations in this case, oldest opened first.")
    finding_ids: list[UUID] = Field(description="Findings in this case, oldest created first.")


class CaseList(BaseModel):
    data: list[CaseRead]
    page: PageInfo


class EvidenceRead(BaseModel):
    """Custody metadata. Raw source bytes are not part of this contract."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    source_record_id: UUID
    source: SourceKind
    evidence_type: EvidenceType
    description: str
    content_sha256: str
    byte_size: int
    collected_at: datetime
    collected_by: str
    created_at: datetime


class EvidenceLinkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    alert_id: UUID | None
    canonical_event_id: UUID | None
    finding_id: UUID | None
    investigation_id: UUID | None
    case_id: UUID | None
    linked_by: str
    linked_at: datetime


class EvidenceDetail(EvidenceRead):
    links: list[EvidenceLinkRead]


class EvidenceList(BaseModel):
    data: list[EvidenceRead]
    page: PageInfo
