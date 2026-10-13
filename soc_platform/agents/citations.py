"""Claims are rendered from stored fields. A citation that does not match is rejected."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from soc_platform.api.reader import assert_reader
from soc_platform.domain.canonical import SEVERITY_IDS
from soc_platform.domain.enums import CitationKind, Severity
from soc_platform.models import Alert, CanonicalEvent, Evidence, SecurityEntity

TEMPLATE_KIND = {
    "alert.summary": CitationKind.ALERT,
    "alert.technique": CitationKind.ALERT,
    "alert.no_technique": CitationKind.ALERT,
    "event.summary": CitationKind.EVENT,
    "entity.summary": CitationKind.ENTITY,
    "evidence.custody": CitationKind.EVIDENCE,
}

TEMPLATE_FIELDS = {
    "alert.summary": ("title", "severity", "status"),
    "alert.technique": ("technique",),
    "alert.no_technique": (),
    "event.summary": ("message", "severity", "event_type"),
    "entity.summary": ("entity_type", "display_value", "event_count", "severity"),
    "evidence.custody": ("content_sha256", "evidence_type"),
}

_RANK_TO_SEVERITY = {rank: Severity(name) for name, rank in SEVERITY_IDS.items()}


@dataclass(frozen=True)
class ClaimProposal:
    template: str
    kind: str
    record_id: UUID
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ValidatedClaim:
    template: str
    kind: CitationKind
    record_id: UUID
    arguments: dict[str, Any]
    statement: str
    severity: Severity | None


@dataclass(frozen=True)
class CitationError:
    template: str
    record_id: str
    reason: str


def propose(template: str, kind: str, record_id: UUID, arguments: dict[str, Any]) -> ClaimProposal:
    return ClaimProposal(template=template, kind=kind, record_id=record_id, arguments=dict(arguments))


def validate_proposal(session: Session, tenant_id: UUID, proposal: ClaimProposal) -> ValidatedClaim | CitationError:
    """Reload the cited row and accept the claim only when every argument matches it."""
    identity = str(proposal.record_id)
    expected_kind = TEMPLATE_KIND.get(proposal.template)
    if expected_kind is None:
        return CitationError(proposal.template, identity, "unknown_template")
    if proposal.kind != expected_kind.value:
        return CitationError(proposal.template, identity, "citation_kind_mismatch")
    fields = TEMPLATE_FIELDS[proposal.template]
    if set(proposal.arguments) != set(fields):
        return CitationError(proposal.template, identity, "argument_mismatch")
    stored = _stored_fields(session, tenant_id, expected_kind, proposal.record_id)
    if stored is None:
        return CitationError(proposal.template, identity, "record_not_found")
    if proposal.template == "alert.technique":
        technique = proposal.arguments.get("technique")
        if not isinstance(technique, str) or technique not in stored["technique_ids"]:
            return CitationError(proposal.template, identity, "technique_not_stored")
    elif proposal.template == "alert.no_technique":
        if stored["technique_ids"]:
            return CitationError(proposal.template, identity, "technique_is_stored")
    else:
        for field in fields:
            if proposal.arguments[field] != stored[field]:
                return CitationError(proposal.template, identity, "stored_value_mismatch")
    severity = None
    if isinstance(stored.get("severity"), str):
        severity = Severity(stored["severity"])
    return ValidatedClaim(
        template=proposal.template,
        kind=expected_kind,
        record_id=proposal.record_id,
        arguments={field: proposal.arguments[field] for field in fields},
        statement=render(proposal.template, proposal.record_id, proposal.arguments),
        severity=severity,
    )


def render(template: str, record_id: UUID, arguments: dict[str, Any]) -> str:
    if template == "alert.summary":
        return (
            f"Stored alert {record_id} is titled {arguments['title']} "
            f"with severity {arguments['severity']} and status {arguments['status']}."
        )
    if template == "alert.technique":
        return f"Stored alert {record_id} records technique {arguments['technique']}."
    if template == "alert.no_technique":
        return f"Stored alert {record_id} does not record a technique."
    if template == "event.summary":
        return (
            f"Stored event {record_id} is {arguments['event_type']} "
            f"with severity {arguments['severity']}: {arguments['message']}"
        )
    if template == "entity.summary":
        return (
            f"Stored {arguments['entity_type']} {arguments['display_value']} "
            f"is linked to {arguments['event_count']} events "
            f"with highest severity {arguments['severity']}."
        )
    if template == "evidence.custody":
        return (
            f"Stored evidence {record_id} is {arguments['evidence_type']} "
            f"with sha256 {arguments['content_sha256']}."
        )
    raise ValueError(f"unknown claim template {template}")


def highest_severity(claims: list[ValidatedClaim]) -> Severity:
    ranks = [SEVERITY_IDS[claim.severity.value] for claim in claims if claim.severity is not None]
    if not ranks:
        return Severity.UNKNOWN
    return _RANK_TO_SEVERITY[max(ranks)]


def proposals_from_alert(record_id: UUID, fields: dict[str, Any]) -> list[ClaimProposal]:
    proposals = [
        propose(
            "alert.summary",
            "alert",
            record_id,
            {"title": fields["title"], "severity": fields["severity"], "status": fields["status"]},
        )
    ]
    techniques = list(fields.get("technique_ids") or [])
    if techniques:
        proposals.extend(
            propose("alert.technique", "alert", record_id, {"technique": technique}) for technique in techniques
        )
    else:
        proposals.append(propose("alert.no_technique", "alert", record_id, {}))
    return proposals


def proposal_from_event(record_id: UUID, fields: dict[str, Any]) -> ClaimProposal:
    return propose(
        "event.summary",
        "event",
        record_id,
        {
            "message": fields["message"],
            "severity": fields["severity"],
            "event_type": fields["event_type"],
        },
    )


def proposal_from_entity(record_id: UUID, fields: dict[str, Any]) -> ClaimProposal:
    return propose(
        "entity.summary",
        "entity",
        record_id,
        {
            "entity_type": fields["entity_type"],
            "display_value": fields["display_value"],
            "event_count": fields["event_count"],
            "severity": fields["severity"],
        },
    )


def proposal_from_evidence(record_id: UUID, fields: dict[str, Any]) -> ClaimProposal:
    return propose(
        "evidence.custody",
        "evidence",
        record_id,
        {"content_sha256": fields["content_sha256"], "evidence_type": fields["evidence_type"]},
    )


def _stored_fields(session: Session, tenant_id: UUID, kind: CitationKind, record_id: UUID) -> dict[str, Any] | None:
    assert_reader(session, tenant_id)
    if kind is CitationKind.ALERT:
        row = session.scalar(select(Alert).where(Alert.tenant_id == tenant_id, Alert.id == record_id))
        if row is None:
            return None
        return {
            "title": row.title,
            "severity": row.severity.value,
            "status": row.status.value,
            "technique_ids": list(row.technique_ids or []),
        }
    if kind is CitationKind.EVENT:
        row = session.scalar(
            select(CanonicalEvent).where(CanonicalEvent.tenant_id == tenant_id, CanonicalEvent.id == record_id)
        )
        if row is None:
            return None
        return {"message": row.message, "severity": row.severity.value, "event_type": row.class_name}
    if kind is CitationKind.ENTITY:
        row = session.scalar(
            select(SecurityEntity).where(SecurityEntity.tenant_id == tenant_id, SecurityEntity.id == record_id)
        )
        if row is None:
            return None
        return {
            "entity_type": row.entity_type.value,
            "display_value": row.display_value,
            "event_count": row.event_count,
            "severity": row.severity.value,
        }
    row = session.scalar(select(Evidence).where(Evidence.tenant_id == tenant_id, Evidence.id == record_id))
    if row is None:
        return None
    return {"content_sha256": row.content_sha256, "evidence_type": row.evidence_type.value}
