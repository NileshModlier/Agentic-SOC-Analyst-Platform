"""Database timing and optional SQLAlchemy spans for engines this process owns."""

from __future__ import annotations

import logging
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from soc_platform.observability.metrics import record_db_query, sql_operation

logger = logging.getLogger(__name__)

_LISTENER = False
_ENGINES: set[int] = set()


def install_sql_metrics() -> None:
    global _LISTENER
    if _LISTENER:
        return
    _LISTENER = True
    event.listen(Engine, "before_cursor_execute", _before_cursor)
    event.listen(Engine, "after_cursor_execute", _after_cursor)
    event.listen(Engine, "handle_error", _on_error)


def instrument_sqlalchemy(engine: Engine) -> None:
    """Attach query spans once. A second engine still gets the duration histogram."""
    install_sql_metrics()
    global _ENGINES
    if _ENGINES:
        return
    _ENGINES.add(id(engine))
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=False)
    except Exception:
        logger.warning("sqlalchemy tracing was not attached", exc_info=True)


def _before_cursor(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
    try:
        conn.info["soc_query_started"] = time.perf_counter()
    except Exception:
        logger.debug("db timer was not started", exc_info=True)


def _after_cursor(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
    _finish(conn, statement)


def _on_error(exception_context) -> None:  # noqa: ANN001
    connection = getattr(exception_context, "connection", None)
    if connection is not None:
        _finish(connection, getattr(exception_context, "statement", "") or "")


def _finish(conn, statement: object) -> None:
    try:
        started = conn.info.pop("soc_query_started", None)
        if started is None:
            return
        record_db_query(sql_operation(statement), time.perf_counter() - started)
    except Exception:
        logger.debug("db metric failed", exc_info=True)
