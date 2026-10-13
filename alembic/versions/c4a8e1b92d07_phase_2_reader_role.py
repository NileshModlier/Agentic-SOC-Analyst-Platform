"""phase 2 read-only database role

Revision ID: c4a8e1b92d07
Revises: 9f0fe331d361
Create Date: 2026-10-06 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4a8e1b92d07"
down_revision: Union[str, Sequence[str], None] = "9f0fe331d361"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables the read API is allowed to see. Operational tables (outbox, receipts,
# dead letters) are intentionally absent.
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
)

# source_records.payload stays ungranted so a faulty query cannot return raw bytes.
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
    op.execute(
        """
        DO $$ BEGIN
          CREATE ROLE soc_reader NOLOGIN NOSUPERUSER NOBYPASSRLS;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO soc_reader")
    tables = ", ".join(READ_TABLES)
    op.execute(f"GRANT SELECT ON TABLE {tables} TO soc_reader")
    columns = ", ".join(SOURCE_RECORD_COLUMNS)
    op.execute(f"GRANT SELECT ({columns}) ON TABLE source_records TO soc_reader")


def downgrade() -> None:
    tables = ", ".join((*READ_TABLES, "source_records"))
    op.execute(f"REVOKE ALL ON TABLE {tables} FROM soc_reader")
    op.execute("REVOKE USAGE ON SCHEMA public FROM soc_reader")
    op.execute("DROP ROLE IF EXISTS soc_reader")
