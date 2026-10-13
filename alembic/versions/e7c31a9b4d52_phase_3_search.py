"""Phase 3 search projections.

Revision ID: e7c31a9b4d52
Revises: c4a8e1b92d07
Create Date: 2026-10-06 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session

revision: str = "e7c31a9b4d52"
down_revision: Union[str, Sequence[str], None] = "c4a8e1b92d07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEARCH_TABLES = (
    "event_search_documents",
    "alert_search_documents",
    "security_entities",
    "event_entities",
)


def upgrade() -> None:
    from soc_platform.models.search import (
        AlertSearchDocument,
        EventEntity,
        EventSearchDocument,
        SecurityEntity,
    )

    bind = op.get_bind()
    EventSearchDocument.__table__.create(bind)
    AlertSearchDocument.__table__.create(bind)
    SecurityEntity.__table__.create(bind)
    EventEntity.__table__.create(bind)
    for table in SEARCH_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id::text = current_setting('soc.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('soc.tenant_id', true))
            """
        )
    tables = ", ".join(SEARCH_TABLES)
    op.execute(f"GRANT SELECT ON TABLE {tables} TO soc_reader")
    # Join the Alembic transaction with a savepoint. Do not commit or close:
    # Session.commit() would commit the migration transaction before the version
    # stamp, and Session.close() would roll that transaction back.
    session = Session(bind=bind, join_transaction_mode="create_savepoint")
    from soc_platform.search.project import rebuild_search

    rebuild_search(session)
    session.flush()


def downgrade() -> None:
    tables = ", ".join(SEARCH_TABLES)
    op.execute(f"REVOKE ALL ON TABLE {tables} FROM soc_reader")
    op.drop_table("event_entities")
    op.drop_table("alert_search_documents")
    op.drop_table("event_search_documents")
    op.drop_table("security_entities")
