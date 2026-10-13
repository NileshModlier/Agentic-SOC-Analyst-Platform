"""Engine and session construction."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def database_now(session: Session) -> datetime:
    """Wall clock from PostgreSQL so intake timestamps match outbox readiness checks."""
    value = session.scalar(text("SELECT clock_timestamp()"))
    if not isinstance(value, datetime):
        raise RuntimeError("database clock query did not return a timestamp")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
