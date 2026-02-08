"""callout rework: smart_wallets, token_snapshots, new columns

Revision ID: 007
Revises: 006
Create Date: 2026-02-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create smart_wallets table
    op.create_table(
        "smart_wallets",
        sa.Column("wallet_address", sa.String(44), nullable=False),
        sa.Column("label", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("total_trades", sa.Integer(), server_default="0", nullable=False),
        sa.Column("winning_trades", sa.Integer(), server_default="0", nullable=False),
        sa.Column("win_rate", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("total_pnl", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("avg_entry_mcap", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("tokens_traded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reputation_score", sa.Float(), server_default="0.0", nullable=False),
        sa.PrimaryKeyConstraint("wallet_address"),
    )

    # Create token_snapshots table
    op.create_table(
        "token_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_address", sa.String(44), nullable=False),
        sa.Column("price", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("volume", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("market_cap", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("buy_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sell_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("holder_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_snapshots_token_address", "token_snapshots", ["token_address"])

    # Add new columns to scanned_tokens
    op.add_column("scanned_tokens", sa.Column("social_mention_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("social_velocity", sa.Float(), server_default="0.0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("rugcheck_score", sa.Float(), nullable=True))
    op.add_column("scanned_tokens", sa.Column("early_buyer_smart_count", sa.Integer(), server_default="0", nullable=False))

    # Add new columns to callouts
    op.add_column("callouts", sa.Column("score_breakdown", sa.JSON(), nullable=True))
    op.add_column("callouts", sa.Column("security_score", sa.Float(), nullable=True))
    op.add_column("callouts", sa.Column("social_mentions", sa.Integer(), nullable=True))
    op.add_column("callouts", sa.Column("early_smart_buyers", sa.Integer(), nullable=True))
    op.add_column("callouts", sa.Column("volume_velocity", sa.Float(), nullable=True))


def downgrade() -> None:
    # Drop columns from callouts
    op.drop_column("callouts", "volume_velocity")
    op.drop_column("callouts", "early_smart_buyers")
    op.drop_column("callouts", "social_mentions")
    op.drop_column("callouts", "security_score")
    op.drop_column("callouts", "score_breakdown")

    # Drop columns from scanned_tokens
    op.drop_column("scanned_tokens", "early_buyer_smart_count")
    op.drop_column("scanned_tokens", "rugcheck_score")
    op.drop_column("scanned_tokens", "social_velocity")
    op.drop_column("scanned_tokens", "social_mention_count")

    # Drop tables
    op.drop_index("ix_token_snapshots_token_address", table_name="token_snapshots")
    op.drop_table("token_snapshots")
    op.drop_table("smart_wallets")
