"""Create casework records. These functions flush and do not commit."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from soc_platform.db.session import database_now
from soc_platform.domain.enums import CaseStatus, FindingStatus, InvestigationStatus, Priority, Severity
from soc_platform.models import Case, EvidenceLink, Finding, FindingAlert, Investigation, InvestigationAlert
from soc_platform.models.mixins import new_uuid


def create_case(
    session: Session,
    *,
    tenant_id: UUID,
    title: str,
    severity: Severity | str,
    description: str | None = None,
    assignee: str | None = None,
    external_ref: str | None = None,
) -> Case:
    at = database_now(session)
    row = Case(
        id=new_uuid(),
        tenant_id=tenant_id,
        title=title,
        description=description,
        status=CaseStatus.OPEN,
        severity=severity if isinstance(severity, Severity) else Severity(severity),
        assignee=assignee,
        external_ref=external_ref,
        opened_at=at,
        closed_at=None,
        created_at=at,
        updated_at=at,
    )
    session.add(row)
    session.flush()
    return row


def create_investigation(
    session: Session,
    *,
    tenant_id: UUID,
    title: str,
    priority: Priority | str = Priority.P3,
    case_id: UUID | None = None,
    hypothesis: str | None = None,
    assignee: str | None = None,
) -> Investigation:
    at = database_now(session)
    row = Investigation(
        id=new_uuid(),
        tenant_id=tenant_id,
        case_id=case_id,
        title=title,
        status=InvestigationStatus.OPEN,
        priority=priority if isinstance(priority, Priority) else Priority(priority),
        hypothesis=hypothesis,
        summary=None,
        assignee=assignee,
        opened_at=at,
        closed_at=None,
        created_at=at,
        updated_at=at,
    )
    session.add(row)
    session.flush()
    return row


def create_finding(
    session: Session,
    *,
    tenant_id: UUID,
    title: str,
    severity: Severity | str,
    created_by: str,
    summary: str | None = None,
    confidence: int | None = None,
    case_id: UUID | None = None,
    investigation_id: UUID | None = None,
    technique_ids: list[str] | None = None,
    tactics: list[str] | None = None,
) -> Finding:
    at = database_now(session)
    row = Finding(
        id=new_uuid(),
        tenant_id=tenant_id,
        case_id=case_id,
        investigation_id=investigation_id,
        title=title,
        summary=summary,
        severity=severity if isinstance(severity, Severity) else Severity(severity),
        confidence=confidence,
        status=FindingStatus.OPEN,
        disposition=None,
        technique_ids=list(technique_ids or []),
        tactics=list(tactics or []),
        created_by=created_by,
        created_at=at,
        updated_at=at,
    )
    session.add(row)
    session.flush()
    return row


def link_alert_to_investigation(
    session: Session,
    *,
    tenant_id: UUID,
    investigation_id: UUID,
    alert_id: UUID,
    linked_by: str,
) -> InvestigationAlert:
    at = database_now(session)
    row = InvestigationAlert(
        id=new_uuid(),
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        alert_id=alert_id,
        linked_by=linked_by,
        linked_at=at,
    )
    session.add(row)
    session.flush()
    return row


def link_alert_to_finding(
    session: Session,
    *,
    tenant_id: UUID,
    finding_id: UUID,
    alert_id: UUID,
    linked_by: str,
) -> FindingAlert:
    at = database_now(session)
    row = FindingAlert(
        id=new_uuid(),
        tenant_id=tenant_id,
        finding_id=finding_id,
        alert_id=alert_id,
        linked_by=linked_by,
        linked_at=at,
    )
    session.add(row)
    session.flush()
    return row


def link_evidence(
    session: Session,
    *,
    tenant_id: UUID,
    evidence_id: UUID,
    linked_by: str,
    alert_id: UUID | None = None,
    canonical_event_id: UUID | None = None,
    finding_id: UUID | None = None,
    investigation_id: UUID | None = None,
    case_id: UUID | None = None,
) -> EvidenceLink:
    at = database_now(session)
    row = EvidenceLink(
        id=new_uuid(),
        tenant_id=tenant_id,
        evidence_id=evidence_id,
        alert_id=alert_id,
        canonical_event_id=canonical_event_id,
        finding_id=finding_id,
        investigation_id=investigation_id,
        case_id=case_id,
        linked_by=linked_by,
        linked_at=at,
    )
    session.add(row)
    session.flush()
    return row
