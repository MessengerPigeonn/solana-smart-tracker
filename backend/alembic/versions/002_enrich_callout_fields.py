"""add enrichment fields to callouts

Revision ID: 002
Revises: 001
Create Date: 2026-02-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("callouts", sa.Column("token_name", sa.String(100), nullable=True))
    op.add_column("callouts", sa.Column("market_cap", sa.Float(), nullable=True))
    op.add_column("callouts", sa.Column("volume_24h", sa.Float(), nullable=True))
    op.add_column("callouts", sa.Column("liquidity", sa.Float(), nullable=True))
    op.add_column("callouts", sa.Column("holder_count", sa.Integer(), nullable=True))
    op.add_column("callouts", sa.Column("rug_risk_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("callouts", "rug_risk_score")
    op.drop_column("callouts", "holder_count")
    op.drop_column("callouts", "liquidity")
    op.drop_column("callouts", "volume_24h")
    op.drop_column("callouts", "market_cap")
    op.drop_column("callouts", "token_name")
