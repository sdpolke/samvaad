"""add exotel to WorkflowRunMode

Revision ID: b1c2d3e4f5a6
Revises: 2f638891cbb6
Create Date: 2026-05-22 11:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "2f638891cbb6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # WorkflowRunMode is stored as varchar in the database, not a PostgreSQL enum.
    # Adding EXOTEL to the Python Enum class (api/enums.py) is sufficient.
    # No DDL change needed.
    pass


def downgrade() -> None:
    pass
