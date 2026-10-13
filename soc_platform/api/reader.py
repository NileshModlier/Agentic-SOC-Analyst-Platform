"""Bind each request to the read-only role and one tenant.

SET LOCAL lasts for the transaction only. The connection returns to the pool
as the login role after rollback. The login role is the table owner and would
bypass row-level security, so every query refuses to run unless current_user
is a tenant-scoped role and soc.tenant_id matches the request. The public read
API binds soc_reader. Investigation workflows bind soc_agent, which can write
draft workspace tables and cannot write canonical records.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from soc_platform.api.errors import ApiError, TenantNotFound
from soc_platform.models import Tenant

READER_ROLE = "soc_reader"
AGENT_ROLE = "soc_agent"
SCOPED_ROLES = frozenset({READER_ROLE, AGENT_ROLE})


@dataclass(frozen=True)
class ReadContext:
    session: Session
    tenant_id: UUID


def bind_reader(session: Session, tenant_id: UUID) -> None:
    session.execute(text("SET LOCAL ROLE soc_reader"))
    session.execute(text("SET LOCAL row_security = on"))
    session.execute(
        text("SELECT set_config('soc.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def bind_agent(session: Session, tenant_id: UUID) -> None:
    session.execute(text("SET LOCAL ROLE soc_agent"))
    session.execute(text("SET LOCAL row_security = on"))
    session.execute(
        text("SELECT set_config('soc.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def assert_reader(session: Session, tenant_id: UUID) -> None:
    role = session.scalar(text("SELECT current_user"))
    scope = session.scalar(text("SELECT current_setting('soc.tenant_id', true)"))
    if role not in SCOPED_ROLES or scope != str(tenant_id):
        raise RuntimeError("refusing to read outside a tenant-scoped database role")


def assert_agent(session: Session, tenant_id: UUID) -> None:
    role = session.scalar(text("SELECT current_user"))
    scope = session.scalar(text("SELECT current_setting('soc.tenant_id', true)"))
    if role != AGENT_ROLE or scope != str(tenant_id):
        raise RuntimeError("refusing to write drafts outside the soc_agent tenant scope")


def open_reader(session: Session, tenant_id: UUID) -> Iterator[ReadContext]:
    try:
        bind_reader(session, tenant_id)
        visible = session.scalar(select(Tenant.id).where(Tenant.id == tenant_id))
        if visible is None:
            raise TenantNotFound
        assert_reader(session, tenant_id)
        yield ReadContext(session=session, tenant_id=tenant_id)
    finally:
        session.rollback()
        session.close()


def reader_session(request: Request) -> Iterator[ReadContext]:
    """Open a read-only session for the tenant named on the request.

    The route declares ``tenant`` so it appears in OpenAPI. This dependency
    reads that same value and does not declare a second query parameter.
    Parse the tenant before opening a connection so an invalid request does
    not take a pooled session.
    """
    tenant_id = tenant_id_from_request(request)
    session = request.app.state.session_factory()
    yield from open_reader(session, tenant_id)


def tenant_id_from_request(request: Request) -> UUID:
    raw = request.query_params.get("tenant")
    if raw is None or not raw.strip():
        raise ApiError(
            422,
            "validation_error",
            "Request parameters are invalid.",
            [{"loc": ["tenant"], "message": "Field required"}],
        )
    try:
        return UUID(raw)
    except ValueError:
        raise ApiError(
            422,
            "validation_error",
            "Request parameters are invalid.",
            [{"loc": ["tenant"], "message": "Input should be a valid UUID."}],
        ) from None
