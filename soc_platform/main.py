"""Application composition root.

Search uses PostgreSQL full text search. Investigation agents draft cited
claims for a person to approve. Intake remains an in-process call. The process
that moves the outbox is ``python -m soc_platform.outbox.relay``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis import Redis

from soc_platform import __version__
from soc_platform.api.agent_routes import router as agent_router
from soc_platform.api.errors import install_error_handlers
from soc_platform.api.operations_routes import router as operations_router
from soc_platform.api.routes import router
from soc_platform.api.search_routes import router as search_router
from soc_platform.config import Settings, get_settings
from soc_platform.db.session import create_db_engine, create_session_factory
from soc_platform.ingestion.pipeline import ingest, replay
from soc_platform.observability import (
    configure_observability,
    install_http_observability,
    instrument_redis_client,
    instrument_sqlalchemy,
    register_api_collectors,
    unregister_api_collectors,
)

DESCRIPTION = """
Read-only API for tenant-scoped security records and investigation search.

Read requests set the database role `soc_reader` and the row-level security
tenant scope. That role can SELECT the read models, search projections,
investigation drafts, connector receipts, and intake metadata. It cannot read
raw source payloads, outbox payloads, or dead-letter bytes, and it cannot write.

Investigation runs set `soc_agent`. That role can SELECT the same records and
can insert or update only the draft workspace: runs, memory, drafts, claims,
citations, and approvals. It cannot write alerts, events, findings, cases,
investigations, or evidence. Agents are not a source of truth. Every claim is
rendered from a stored row and rejected when the citation does not match.
A person must approve a draft. Approval does not promote the draft into a
finding. The workflow has no internet access.

Search is PostgreSQL full text search over the projected rows. There is no
Elasticsearch or OpenSearch index, and Redis is not used for search or agents.

Operations reads return connector receipt counts, dead-letter metadata, and
publication status. They do not return raw source bytes or outbox payloads.
Replay remains an operator command. The security operations console is a
separate application and is not served by this process.

There is no caller authentication in this phase. A request names one tenant and
cannot read another tenant's rows.

Collection filters apply only where the resource has that attribute:

- `tenant` is required on every operation
- `source` filters events, alerts, and evidence
- `severity` filters events, alerts, findings, and cases
- `alert_status` filters alerts
- `case_status` filters cases
- `investigation_status` filters investigations
- `event_type` filters events by OCSF class name
- `start` and `end` filter each collection's own time column

Search accepts `q`, `severity`, `source`, `status`, `event_type`, and a time
range. Event status is the OCSF outcome. Alert status is the workflow status.
Facets describe the event corpus and each facet omits its own filter.

Collections and search pages use an opaque cursor. The default page size is 50
and the maximum is 100. Facets are not paginated.
"""

TAGS = [
    {"name": "Events", "description": "Canonical security events projected from immutable source records."},
    {"name": "Alerts", "description": "Detections. This API does not change workflow status."},
    {"name": "Findings", "description": "Analyst or platform conclusions."},
    {"name": "Investigations", "description": "Units of analysis."},
    {"name": "Cases", "description": "Incident containers."},
    {"name": "Evidence", "description": "Custody records. Raw source bytes are not returned."},
    {
        "name": "Search",
        "description": "PostgreSQL full-text discovery across events, alerts, and entities.",
    },
    {
        "name": "Agents",
        "description": "Cited investigation drafts. Human approval does not change canonical records.",
    },
    {
        "name": "Operations",
        "description": "Intake health, dead-letter metadata, and publication status. Payloads are omitted.",
    },
]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_observability(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(resolved.database_url)
        instrument_sqlalchemy(engine)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        # Redis belongs to the outbox relay and to readiness. Read, search, and agent routes do not use it.
        app.state.redis = instrument_redis_client(Redis.from_url(resolved.redis_url))
        collectors = register_api_collectors(engine, app.state.redis) if resolved.metrics_enabled else []
        try:
            yield
        finally:
            unregister_api_collectors(collectors)
            app.state.redis.close()
            engine.dispose()

    app = FastAPI(
        title="Agentic SOC Analyst Platform",
        version=__version__,
        summary="Security operations, search, cited drafts, and intake reads",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = resolved
    app.state.ingest = ingest
    app.state.replay = replay
    app.include_router(router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(operations_router, prefix="/api/v1")
    install_error_handlers(app)
    install_http_observability(app)
    return app
