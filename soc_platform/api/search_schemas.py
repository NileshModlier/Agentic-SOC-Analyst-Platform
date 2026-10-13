"""Search read models and query contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from soc_platform.api.schemas import PageInfo, PageQuery, TimeWindow
from soc_platform.domain.enums import (
    AlertStatus,
    EntityType,
    Outcome,
    SearchSort,
    Severity,
    SourceKind,
)


class SearchFilters(BaseModel):
    q: str | None = Field(
        default=None,
        max_length=256,
        description=(
            "Full-text query. Words are required together. "
            "Punctuation in IP addresses, paths, and process names is folded before matching."
        ),
    )
    source: SourceKind | None = Field(default=None, description="Intake source kind.")
    severity: Severity | None = Field(default=None, description="Severity.")
    event_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="OCSF class name, for example Authentication or Process Activity. Match is case-sensitive.",
        examples=["Authentication"],
    )

    @field_validator("q")
    @classmethod
    def clean_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("event_type")
    @classmethod
    def clean_event_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("event_type must not be empty")
        return stripped


class EventSearchQuery(SearchFilters, PageQuery):
    sort: SearchSort = Field(
        default=SearchSort.EVENT_TIME,
        description="event_time and created_time are newest first. severity is highest first.",
    )
    status: Outcome | None = Field(
        default=None,
        description="OCSF status of the event: success, failure, unknown, or other.",
    )


class AlertSearchQuery(SearchFilters, PageQuery):
    sort: SearchSort = Field(
        default=SearchSort.EVENT_TIME,
        description="event_time sorts by detection time. created_time is newest first. severity is highest first.",
    )
    status: AlertStatus | None = Field(default=None, description="Alert workflow status.")


class EntitySearchQuery(SearchFilters, PageQuery):
    sort: SearchSort = Field(
        default=SearchSort.EVENT_TIME,
        description=(
            "event_time sorts by last seen. created_time sorts by first seen. "
            "severity is the highest severity of a linked event."
        ),
    )
    status: Outcome | None = Field(
        default=None,
        description="Keep entities linked to an event with this OCSF status.",
    )
    entity_type: EntityType | None = Field(
        default=None,
        description="Restrict the catalog to user, host, process, file, or ip.",
    )


class FacetQuery(SearchFilters, TimeWindow):
    tenant: UUID = Field(
        description="Tenant scope. Required on every request. Row-level security is set to this tenant."
    )
    status: Outcome | None = Field(
        default=None,
        description="OCSF status applied to the event corpus. Status is not itself a facet.",
    )


class EventSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    source: SourceKind
    event_type: str
    severity: Severity
    status: Outcome
    hostname: str | None
    username: str | None
    message: str
    event_time: datetime
    created_at: datetime
    headline: str | None = None


class EventSearchPage(BaseModel):
    data: list[EventSearchHit]
    page: PageInfo


class AlertSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    canonical_event_id: UUID | None
    source: SourceKind
    title: str
    severity: Severity
    status: AlertStatus
    rule_id: str | None
    rule_name: str | None
    event_type: str | None
    hostname: str | None
    username: str | None
    detected_at: datetime
    created_at: datetime
    headline: str | None = None


class AlertSearchPage(BaseModel):
    data: list[AlertSearchHit]
    page: PageInfo


class EntitySearchHit(BaseModel):
    """One catalog row. entity_type distinguishes users, hosts, processes, files, and IP addresses."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    entity_type: EntityType
    value: str
    display_value: str
    severity: Severity
    first_seen: datetime
    last_seen: datetime
    event_count: int
    headline: str | None = None


class EntitySearchPage(BaseModel):
    data: list[EntitySearchHit]
    page: PageInfo


class FacetBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    count: int


class SearchFacets(BaseModel):
    """Event-corpus counts. Each facet ignores its own filter and keeps the rest of the query."""

    model_config = ConfigDict(extra="forbid")

    event_type: list[FacetBucket]
    severity: list[FacetBucket]
    source: list[FacetBucket]
    host: list[FacetBucket]
    user: list[FacetBucket]
