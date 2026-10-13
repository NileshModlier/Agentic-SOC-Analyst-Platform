"""Draft storage and the human approval gate."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from soc_platform.agents.actors import require_human
from soc_platform.agents.citations import ValidatedClaim, highest_severity
from soc_platform.api.errors import Conflict, ResourceNotFound
from soc_platform.api.reader import assert_agent
from soc_platform.db.session import database_now
from soc_platform.domain.enums import ApprovalDecision, DraftStatus, Severity
from soc_platform.models.agent import DraftApproval, DraftCitation, DraftClaim, InvestigationDraft
from soc_platform.models.mixins import new_uuid
from soc_platform.observability.hooks import observed_decision, observed_draft

_AGENT_STATUSES = frozenset(
    {
        DraftStatus.PENDING_APPROVAL,
        DraftStatus.INSUFFICIENT_EVIDENCE,
        DraftStatus.VALIDATION_FAILED,
    }
)


@observed_draft
def store_draft(
    session,
    *,
    tenant_id: UUID,
    run_id: UUID,
    status: DraftStatus,
    title: str,
    claims: list[ValidatedClaim],
    severity: Severity | None = None,
) -> InvestigationDraft:
    if status not in _AGENT_STATUSES:
        raise RuntimeError("agents cannot approve or reject a draft")
    assert_agent(session, tenant_id)
    now = database_now(session)
    summary = "\n".join(claim.statement for claim in claims) or _empty_summary(status)
    draft = InvestigationDraft(
        id=new_uuid(),
        tenant_id=tenant_id,
        run_id=run_id,
        status=status,
        title=title[:500],
        summary=summary,
        severity=severity or highest_severity(claims),
        source_of_truth=False,
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    session.flush()
    for position, claim in enumerate(claims):
        row = DraftClaim(
            id=new_uuid(),
            tenant_id=tenant_id,
            draft_id=draft.id,
            position=position,
            template=claim.template,
            statement=claim.statement,
            arguments=claim.arguments,
        )
        session.add(row)
        session.flush()
        session.add(
            DraftCitation(
                id=new_uuid(),
                tenant_id=tenant_id,
                draft_id=draft.id,
                claim_id=row.id,
                kind=claim.kind,
                record_id=claim.record_id,
            )
        )
    session.flush()
    return draft


@observed_decision
def decide_draft(
    session,
    *,
    tenant_id: UUID,
    draft_id: UUID,
    decision: ApprovalDecision,
    actor: str,
    note: str | None,
) -> InvestigationDraft:
    assert_agent(session, tenant_id)
    person = require_human(actor, field="actor")
    draft = session.scalar(
        select(InvestigationDraft).where(
            InvestigationDraft.tenant_id == tenant_id,
            InvestigationDraft.id == draft_id,
        )
    )
    if draft is None:
        raise ResourceNotFound("Draft")
    if draft.status != DraftStatus.PENDING_APPROVAL:
        raise Conflict("Only a draft that is pending approval can be decided.")
    existing = session.scalar(
        select(DraftApproval.id).where(
            DraftApproval.tenant_id == tenant_id,
            DraftApproval.draft_id == draft.id,
        )
    )
    if existing is not None:
        raise Conflict("This draft already has a human decision.")
    now = database_now(session)
    session.add(
        DraftApproval(
            id=new_uuid(),
            tenant_id=tenant_id,
            draft_id=draft.id,
            decision=decision,
            actor=person,
            note=None if note is None else note.strip() or None,
            created_at=now,
        )
    )
    draft.status = DraftStatus.APPROVED if decision == ApprovalDecision.APPROVED else DraftStatus.REJECTED
    draft.updated_at = now
    draft.source_of_truth = False
    session.flush()
    return draft


def _empty_summary(status: DraftStatus) -> str:
    if status is DraftStatus.VALIDATION_FAILED:
        return "One or more claims did not match the stored record."
    return "No stored record supported a claim."
