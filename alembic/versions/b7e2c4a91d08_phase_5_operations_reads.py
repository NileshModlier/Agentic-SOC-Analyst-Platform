"""Phase 5 console reads for intake operations.

Revision ID: b7e2c4a91d08
Revises: a1c9e4f80b26
Create Date: 2026-10-06 23:10:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b7e2c4a91d08"
down_revision: Union[str, Sequence[str], None] = "a1c9e4f80b26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEAD_LETTER_COLUMNS = (
    "id",
    "tenant_id",
    "source_record_id",
    "outbox_event_id",
    "stage",
    "reason_code",
    "error_message",
    "attempt_count",
    "payload_sha256",
    "created_at",
    "resolved_at",
)

OUTBOX_COLUMNS = (
    "id",
    "tenant_id",
    "aggregate_type",
    "aggregate_id",
    "event_type",
    "status",
    "attempts",
    "last_error",
    "created_at",
    "published_at",
)


def upgrade() -> None:
    dead = ", ".join(DEAD_LETTER_COLUMNS)
    outbox = ", ".join(OUTBOX_COLUMNS)
    op.execute(f"GRANT SELECT ({dead}) ON TABLE dead_letters TO soc_reader")
    op.execute(f"GRANT SELECT ({outbox}) ON TABLE outbox_events TO soc_reader")
    op.execute("GRANT SELECT ON TABLE ingest_receipts TO soc_reader")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON TABLE ingest_receipts FROM soc_reader")
    op.execute("REVOKE ALL ON TABLE outbox_events FROM soc_reader")
    op.execute("REVOKE ALL ON TABLE dead_letters FROM soc_reader")
