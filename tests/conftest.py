"""Integration fixtures. Schema comes from Alembic, and each test rolls back."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from soc_platform.domain.enums import TenantStatus
from soc_platform.models import Tenant

DEFAULT_URL = "postgresql+psycopg://soc:soc@localhost:5434/soc"


def _database_url() -> str:
    return os.environ.get("SOC_TEST_DATABASE_URL", os.environ.get("SOC_DATABASE_URL", DEFAULT_URL))


@pytest.fixture(scope="session")
def engine() -> Engine:
    url = _database_url()
    os.environ["SOC_DATABASE_URL"] = url
    candidate = create_engine(url, pool_pre_ping=True)
    try:
        with candidate.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        candidate.dispose()
        pytest.skip(f"PostgreSQL is not available at {url}: {exc}")

    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    yield candidate
    candidate.dispose()


@pytest.fixture
def session(engine: Engine):
    connection = engine.connect()
    transaction = connection.begin()
    bound = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield bound
    finally:
        bound.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def tenant(session: Session) -> Tenant:
    return _make_tenant(session)


@pytest.fixture
def tenant_factory() -> Callable[[Session], Tenant]:
    return _make_tenant


def _make_tenant(session: Session) -> Tenant:
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    row = Tenant(
        slug=f"tenant-{uuid4().hex[:12]}",
        name="Test tenant",
        status=TenantStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row
