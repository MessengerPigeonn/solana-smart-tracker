"""add take_profit_tiers to copy_trade_configs

Revision ID: 008
Revises: 007
Create Date: 2026-02-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("copy_trade_configs", sa.Column("take_profit_tiers", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("copy_trade_configs", "take_profit_tiers")
