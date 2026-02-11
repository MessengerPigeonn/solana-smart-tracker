"""add CTO tracking fields

Revision ID: 011
Revises: 010
Create Date: 2026-02-11 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CTOWallet: new table
    op.create_table(
        "cto_wallets",
        sa.Column("wallet_address", sa.String(44), primary_key=True),
        sa.Column("label", sa.String(30), server_default="cto_accumulator", nullable=False),
        sa.Column("successful_ctos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_accumulations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_entry_drop_pct", sa.Float(), server_default="0", nullable=False),
        sa.Column("best_revival_multiple", sa.Float(), server_default="0", nullable=False),
        sa.Column("helius_identity_type", sa.String(50), nullable=True),
        sa.Column("helius_identity_name", sa.String(100), nullable=True),
        sa.Column("funded_by", sa.String(44), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reputation_score", sa.Float(), server_default="0", nullable=False),
    )

    # ScannedToken: CTO tracking fields
    op.add_column("scanned_tokens", sa.Column("cto_wallet_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("is_faded", sa.Boolean(), nullable=True))
    op.add_column("scanned_tokens", sa.Column("social_cto_mentions", sa.Integer(), server_default="0", nullable=False))

    # Callout: CTO tracking fields
    op.add_column("callouts", sa.Column("cto_wallet_count", sa.Integer(), nullable=True))
    op.add_column("callouts", sa.Column("is_cto_revival", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("callouts", "is_cto_revival")
    op.drop_column("callouts", "cto_wallet_count")

    op.drop_column("scanned_tokens", "social_cto_mentions")
    op.drop_column("scanned_tokens", "is_faded")
    op.drop_column("scanned_tokens", "cto_wallet_count")

    op.drop_table("cto_wallets")
