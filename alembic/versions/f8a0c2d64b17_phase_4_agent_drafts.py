"""Phase 4 agent workspace and soc_agent role.

Revision ID: f8a0c2d64b17
Revises: e7c31a9b4d52
Create Date: 2026-10-06 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f8a0c2d64b17"
down_revision: Union[str, Sequence[str], None] = "e7c31a9b4d52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WORKSPACE_TABLES = (
    "agent_runs",
    "agent_memories",
    "investigation_drafts",
    "draft_claims",
    "draft_citations",
    "draft_approvals",
)

READ_TABLES = (
    "tenants",
    "canonical_events",
    "alerts",
    "findings",
    "investigations",
    "security_cases",
    "evidence",
    "evidence_links",
    "finding_alerts",
    "investigation_alerts",
    "event_search_documents",
    "alert_search_documents",
    "security_entities",
    "event_entities",
)

SOURCE_RECORD_COLUMNS = (
    "id",
    "tenant_id",
    "source_kind",
    "content_type",
    "content_sha256",
    "byte_size",
    "external_id",
    "received_at",
)


def upgrade() -> None:
    from soc_platform.models.agent import (
        AgentMemory,
        AgentRun,
        DraftApproval,
        DraftCitation,
        DraftClaim,
        InvestigationDraft,
    )

    bind = op.get_bind()
    AgentRun.__table__.create(bind)
    AgentMemory.__table__.create(bind)
    InvestigationDraft.__table__.create(bind)
    DraftClaim.__table__.create(bind)
    DraftCitation.__table__.create(bind)
    DraftApproval.__table__.create(bind)
    for table in WORKSPACE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id::text = current_setting('soc.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('soc.tenant_id', true))
            """
        )
    op.execute(
        """
        DO $$ BEGIN
          CREATE ROLE soc_agent NOLOGIN NOSUPERUSER NOBYPASSRLS;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO soc_agent")
    workspace = ", ".join(WORKSPACE_TABLES)
    readable = ", ".join(READ_TABLES)
    columns = ", ".join(SOURCE_RECORD_COLUMNS)
    op.execute(f"GRANT SELECT ON TABLE {workspace} TO soc_reader")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE {workspace} TO soc_agent")
    op.execute(f"GRANT SELECT ON TABLE {readable} TO soc_agent")
    op.execute(f"GRANT SELECT ({columns}) ON TABLE source_records TO soc_agent")


def downgrade() -> None:
    workspace = ", ".join(WORKSPACE_TABLES)
    readable = ", ".join((*READ_TABLES, "source_records"))
    op.execute(f"REVOKE ALL ON TABLE {workspace} FROM soc_reader")
    op.execute(f"REVOKE ALL ON TABLE {workspace} FROM soc_agent")
    op.execute(f"REVOKE ALL ON TABLE {readable} FROM soc_agent")
    op.execute("REVOKE USAGE ON SCHEMA public FROM soc_agent")
    for table in reversed(WORKSPACE_TABLES):
        op.drop_table(table)
    op.execute("DROP ROLE IF EXISTS soc_agent")
