"""Read a run back from workspace tables."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from soc_platform.api.agent_schemas import (
    DRAFT_NOTICE,
    ApprovalRead,
    CitationRead,
    ClaimRead,
    DraftRead,
    MemoryRead,
    RunRead,
)
from soc_platform.api.errors import ResourceNotFound
from soc_platform.api.reader import assert_reader
from soc_platform.models.agent import (
    AgentMemory,
    AgentRun,
    DraftApproval,
    DraftCitation,
    DraftClaim,
    InvestigationDraft,
)


def present_run(session: Session, tenant_id: UUID, run_id: UUID) -> RunRead:
    assert_reader(session, tenant_id)
    run = session.scalar(select(AgentRun).where(AgentRun.tenant_id == tenant_id, AgentRun.id == run_id))
    if run is None:
        raise ResourceNotFound("Run")
    memories = session.scalars(
        select(AgentMemory)
        .where(AgentMemory.tenant_id == tenant_id, AgentMemory.run_id == run.id)
        .order_by(AgentMemory.sequence.asc())
    ).all()
    draft = session.scalar(
        select(InvestigationDraft).where(
            InvestigationDraft.tenant_id == tenant_id,
            InvestigationDraft.run_id == run.id,
        )
    )
    return RunRead(
        id=run.id,
        tenant_id=run.tenant_id,
        alert_id=run.alert_id,
        question=run.question,
        status=run.status,
        error_code=run.error_code,
        error_message=run.error_message,
        requested_by=run.requested_by,
        draft=None if draft is None else present_draft(session, tenant_id, draft.id),
        memory=[
            MemoryRead(sequence=row.sequence, agent=row.agent.value, kind=row.kind.value, payload=dict(row.payload))
            for row in memories
        ],
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def present_draft(session: Session, tenant_id: UUID, draft_id: UUID) -> DraftRead:
    assert_reader(session, tenant_id)
    draft = session.scalar(
        select(InvestigationDraft).where(
            InvestigationDraft.tenant_id == tenant_id,
            InvestigationDraft.id == draft_id,
        )
    )
    if draft is None:
        raise ResourceNotFound("Draft")
    if draft.source_of_truth:
        raise RuntimeError("investigation draft cannot be a source of truth")
    claims = session.scalars(
        select(DraftClaim)
        .where(DraftClaim.tenant_id == tenant_id, DraftClaim.draft_id == draft.id)
        .order_by(DraftClaim.position.asc())
    ).all()
    citations = session.scalars(
        select(DraftCitation).where(DraftCitation.tenant_id == tenant_id, DraftCitation.draft_id == draft.id)
    ).all()
    by_claim: dict[UUID, list[DraftCitation]] = {}
    for citation in citations:
        by_claim.setdefault(citation.claim_id, []).append(citation)
    approval = session.scalar(
        select(DraftApproval).where(DraftApproval.tenant_id == tenant_id, DraftApproval.draft_id == draft.id)
    )
    return DraftRead(
        id=draft.id,
        tenant_id=draft.tenant_id,
        run_id=draft.run_id,
        status=draft.status,
        title=draft.title,
        summary=draft.summary,
        severity=draft.severity,
        source_of_truth=False,
        notice=DRAFT_NOTICE,
        claims=[
            ClaimRead(
                position=claim.position,
                template=claim.template,
                statement=claim.statement,
                arguments=dict(claim.arguments),
                citations=[
                    CitationRead(kind=item.kind, record_id=item.record_id) for item in by_claim.get(claim.id, [])
                ],
            )
            for claim in claims
        ],
        approval=None
        if approval is None
        else ApprovalRead(
            decision=approval.decision,
            actor=approval.actor,
            note=approval.note,
            created_at=approval.created_at,
        ),
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )
