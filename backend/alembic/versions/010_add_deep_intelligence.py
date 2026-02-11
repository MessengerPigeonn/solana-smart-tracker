"""add deep intelligence fields

Revision ID: 010
Revises: 009
Create Date: 2026-02-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SmartWallet: reputation decay fields
    op.add_column("smart_wallets", sa.Column("recent_trades_7d", sa.Integer(), server_default="0", nullable=False))
    op.add_column("smart_wallets", sa.Column("recent_wins_7d", sa.Integer(), server_default="0", nullable=False))
    op.add_column("smart_wallets", sa.Column("recent_pnl_7d", sa.Float(), server_default="0", nullable=False))

    # ScannedToken: deployer + conviction fields
    op.add_column("scanned_tokens", sa.Column("deployer_address", sa.String(44), nullable=True))
    op.add_column("scanned_tokens", sa.Column("deployer_rug_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("deployer_token_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("scanned_tokens", sa.Column("early_buyer_hold_rate", sa.Float(), nullable=True))
    op.add_column("scanned_tokens", sa.Column("conviction_score", sa.Float(), nullable=True))

    # Callout: deployer + conviction fields
    op.add_column("callouts", sa.Column("deployer_rug_count", sa.Integer(), nullable=True))
    op.add_column("callouts", sa.Column("conviction_score", sa.Float(), nullable=True))

    # CopyTradeConfig: safety fields
    op.add_column("copy_trade_configs", sa.Column("skip_bundled_tokens", sa.Boolean(), server_default="1", nullable=False))
    op.add_column("copy_trade_configs", sa.Column("strict_safety", sa.Boolean(), server_default="1", nullable=False))

    # WalletTokenAppearance: new table for cross-token intelligence
    op.create_table(
        "wallet_token_appearances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wallet_address", sa.String(44), nullable=False, index=True),
        sa.Column("token_address", sa.String(44), nullable=False, index=True),
        sa.Column("appeared_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("wallet_token_appearances")

    op.drop_column("copy_trade_configs", "strict_safety")
    op.drop_column("copy_trade_configs", "skip_bundled_tokens")

    op.drop_column("callouts", "conviction_score")
    op.drop_column("callouts", "deployer_rug_count")

    op.drop_column("scanned_tokens", "conviction_score")
    op.drop_column("scanned_tokens", "early_buyer_hold_rate")
    op.drop_column("scanned_tokens", "deployer_token_count")
    op.drop_column("scanned_tokens", "deployer_rug_count")
    op.drop_column("scanned_tokens", "deployer_address")

    op.drop_column("smart_wallets", "recent_pnl_7d")
    op.drop_column("smart_wallets", "recent_wins_7d")
    op.drop_column("smart_wallets", "recent_trades_7d")
