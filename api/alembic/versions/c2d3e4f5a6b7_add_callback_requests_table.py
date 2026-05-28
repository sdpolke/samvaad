"""add callback_requests table

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-22 11:01:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "callback_requests",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            sa.Integer(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lead_name", sa.String(), nullable=True),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("callback_date", sa.String(), nullable=False),
        sa.Column("callback_time", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_callback_requests_organization_id",
        "callback_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_callback_requests_campaign_id",
        "callback_requests",
        ["campaign_id"],
    )
    op.create_index(
        "ix_callback_requests_status",
        "callback_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_callback_requests_status", table_name="callback_requests")
    op.drop_index("ix_callback_requests_campaign_id", table_name="callback_requests")
    op.drop_index(
        "ix_callback_requests_organization_id", table_name="callback_requests"
    )
    op.drop_table("callback_requests")
