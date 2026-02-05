"""add repinned_at to callouts

Revision ID: 004
Revises: 003
Create Date: 2026-02-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("callouts", sa.Column("repinned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("callouts", "repinned_at")
