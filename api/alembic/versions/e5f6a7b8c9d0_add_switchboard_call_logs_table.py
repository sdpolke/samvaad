"""add switchboard_call_logs table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "switchboard_call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_run_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("ledger", sa.JSON(), nullable=False),
        sa.Column("caller_name", sa.String(), nullable=True),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("disposition", sa.String(), nullable=True),
        sa.Column("after_hours", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("end_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", name="uq_switchboard_call_logs_run"),
    )
    op.create_index(
        "ix_switchboard_call_logs_org_id",
        "switchboard_call_logs",
        ["organization_id"],
    )
    op.create_index(
        "ix_switchboard_call_logs_created_at",
        "switchboard_call_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_switchboard_call_logs_intent",
        "switchboard_call_logs",
        ["intent"],
    )
    op.create_index(
        "ix_switchboard_call_logs_disposition",
        "switchboard_call_logs",
        ["disposition"],
    )


def downgrade() -> None:
    op.drop_index("ix_switchboard_call_logs_disposition", "switchboard_call_logs")
    op.drop_index("ix_switchboard_call_logs_intent", "switchboard_call_logs")
    op.drop_index("ix_switchboard_call_logs_created_at", "switchboard_call_logs")
    op.drop_index("ix_switchboard_call_logs_org_id", "switchboard_call_logs")
    op.drop_table("switchboard_call_logs")
