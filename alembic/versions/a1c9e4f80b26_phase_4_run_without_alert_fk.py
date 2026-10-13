"""Allow a failed run to name an alert that is not stored.

Revision ID: a1c9e4f80b26
Revises: f8a0c2d64b17
Create Date: 2026-10-06 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1c9e4f80b26"
down_revision: Union[str, Sequence[str], None] = "f8a0c2d64b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS fk_agent_runs_alert")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_runs
        ADD CONSTRAINT fk_agent_runs_alert
        FOREIGN KEY (tenant_id, alert_id)
        REFERENCES alerts (tenant_id, id)
        ON DELETE RESTRICT
        """
    )
