"""Bind a workflow request to soc_agent and commit only workspace writes."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import select

from soc_platform.agents.context import RunContext
from soc_platform.api.errors import TenantNotFound
from soc_platform.api.reader import assert_agent, bind_agent, tenant_id_from_request
from soc_platform.models import Tenant


def agent_session(request: Request) -> Iterator[RunContext]:
    tenant_id = tenant_id_from_request(request)
    session = request.app.state.session_factory()
    try:
        bind_agent(session, tenant_id)
        visible = session.scalar(select(Tenant.id).where(Tenant.id == tenant_id))
        if visible is None:
            raise TenantNotFound
        assert_agent(session, tenant_id)
        context = RunContext(
            session=session,
            tenant_id=tenant_id,
            run_id=tenant_id,
            cursor_secret=request.app.state.settings.api_cursor_secret,
            tools=None,
        )
        yield context
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
