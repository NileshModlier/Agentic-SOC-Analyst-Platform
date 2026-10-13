"""Paged reads of investigation workspace rows. These rows are drafts, not findings."""

from __future__ import annotations

from sqlalchemy import and_, select

from soc_platform.api.agent_schemas import (
    ApprovalRead,
    DraftList,
    DraftListQuery,
    DraftSummary,
    RunList,
    RunListQuery,
    RunSummary,
)
from soc_platform.api.pagination import encode_cursor
from soc_platform.api.queries import _before, _fetch, _filters, _page, _position, _window
from soc_platform.api.reader import ReadContext, assert_reader
from soc_platform.models.agent import AgentRun, DraftApproval, InvestigationDraft

_RUNS = "agent_runs"
_DRAFTS = "investigation_drafts"


def list_runs(ctx: ReadContext, query: RunListQuery, secret: str) -> RunList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(
        ctx,
        run_status=query.run_status,
        draft_status=query.draft_status,
        alert_id=query.alert_id,
        start=query.start,
        end=query.end,
        limit=query.limit,
    )
    position = _position(secret, query.cursor, _RUNS, filters)
    stmt = (
        select(AgentRun, InvestigationDraft)
        .outerjoin(
            InvestigationDraft,
            and_(
                InvestigationDraft.tenant_id == AgentRun.tenant_id,
                InvestigationDraft.run_id == AgentRun.id,
            ),
        )
        .where(AgentRun.tenant_id == ctx.tenant_id)
    )
    if query.run_status is not None:
        stmt = stmt.where(AgentRun.status == query.run_status)
    if query.draft_status is not None:
        stmt = stmt.where(InvestigationDraft.status == query.draft_status)
    if query.alert_id is not None:
        stmt = stmt.where(AgentRun.alert_id == query.alert_id)
    stmt = _window(stmt, AgentRun.created_at, query.start, query.end)
    stmt = _before(stmt, AgentRun.created_at, AgentRun.id, position)
    stmt = stmt.order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(rows, query.limit, lambda row: _cursor(secret, _RUNS, filters, row[0]))
    return RunList(data=[_run_summary(run, draft) for run, draft in visible], page=page)


def list_drafts(ctx: ReadContext, query: DraftListQuery, secret: str) -> DraftList:
    assert_reader(ctx.session, ctx.tenant_id)
    filters = _filters(
        ctx,
        status=query.status,
        start=query.start,
        end=query.end,
        limit=query.limit,
    )
    position = _position(secret, query.cursor, _DRAFTS, filters)
    stmt = (
        select(InvestigationDraft, DraftApproval)
        .outerjoin(
            DraftApproval,
            and_(
                DraftApproval.tenant_id == InvestigationDraft.tenant_id,
                DraftApproval.draft_id == InvestigationDraft.id,
            ),
        )
        .where(InvestigationDraft.tenant_id == ctx.tenant_id)
    )
    if query.status is not None:
        stmt = stmt.where(InvestigationDraft.status == query.status)
    stmt = _window(stmt, InvestigationDraft.created_at, query.start, query.end)
    stmt = _before(stmt, InvestigationDraft.created_at, InvestigationDraft.id, position)
    stmt = stmt.order_by(InvestigationDraft.created_at.desc(), InvestigationDraft.id.desc())
    rows = _fetch(ctx.session, stmt, query.limit)
    visible, page = _page(rows, query.limit, lambda row: _cursor(secret, _DRAFTS, filters, row[0]))
    return DraftList(data=[_draft_summary(draft, approval) for draft, approval in visible], page=page)


def _cursor(secret: str, resource: str, filters: dict, row) -> str:
    return encode_cursor(secret, resource=resource, filters=filters, sort_at=row.created_at, row_id=row.id)


def _run_summary(run: AgentRun, draft: InvestigationDraft | None) -> RunSummary:
    return RunSummary(
        id=run.id,
        tenant_id=run.tenant_id,
        alert_id=run.alert_id,
        question=run.question,
        status=run.status,
        error_code=run.error_code,
        error_message=run.error_message,
        requested_by=run.requested_by,
        draft_id=None if draft is None else draft.id,
        draft_status=None if draft is None else draft.status,
        draft_title=None if draft is None else draft.title,
        draft_severity=None if draft is None else draft.severity,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _draft_summary(draft: InvestigationDraft, approval: DraftApproval | None) -> DraftSummary:
    if draft.source_of_truth:
        raise RuntimeError("investigation draft cannot be a source of truth")
    return DraftSummary(
        id=draft.id,
        tenant_id=draft.tenant_id,
        run_id=draft.run_id,
        status=draft.status,
        title=draft.title,
        summary=draft.summary,
        severity=draft.severity,
        source_of_truth=False,
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
