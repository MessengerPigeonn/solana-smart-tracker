"""add bundle detection fields to scanned_tokens and callouts

Revision ID: 009
Revises: 008
Create Date: 2026-02-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ScannedToken bundle fields
    op.add_column("scanned_tokens", sa.Column("bundle_pct", sa.Float(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("bundle_held_pct", sa.Float(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("bundle_wallet_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("bundle_risk", sa.String(10), server_default="none", nullable=False))

    # Callout bundle fields
    op.add_column("callouts", sa.Column("bundle_pct", sa.Float(), nullable=True))
    op.add_column("callouts", sa.Column("bundle_held_pct", sa.Float(), nullable=True))
    op.add_column("callouts", sa.Column("bundle_risk", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("callouts", "bundle_risk")
    op.drop_column("callouts", "bundle_held_pct")
    op.drop_column("callouts", "bundle_pct")

    op.drop_column("scanned_tokens", "bundle_risk")
    op.drop_column("scanned_tokens", "bundle_wallet_count")
    op.drop_column("scanned_tokens", "bundle_held_pct")
    op.drop_column("scanned_tokens", "bundle_pct")
