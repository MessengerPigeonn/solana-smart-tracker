"""add copy trade tables

Revision ID: 005
Revises: 004
Create Date: 2026-02-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "copy_trade_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("signal_types", sa.JSON(), nullable=True),
        sa.Column("max_trade_sol", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("max_daily_sol", sa.Float(), nullable=False, server_default=sa.text("5.0")),
        sa.Column("slippage_bps", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("take_profit_pct", sa.Float(), nullable=True),
        sa.Column("stop_loss_pct", sa.Float(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("min_score", sa.Float(), nullable=False, server_default=sa.text("75.0")),
        sa.Column("max_rug_risk", sa.Float(), nullable=True),
        sa.Column("min_liquidity", sa.Float(), nullable=False, server_default=sa.text("5000.0")),
        sa.Column("min_market_cap", sa.Float(), nullable=False, server_default=sa.text("10000.0")),
        sa.Column("skip_print_scan", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trading_wallet_pubkey", sa.String(44), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_copy_trade_configs_user_id", "copy_trade_configs", ["user_id"])

    op.create_table(
        "trading_wallets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("public_key", sa.String(44), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("encryption_iv", sa.String(44), nullable=False),
        sa.Column("balance_sol", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("balance_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("public_key"),
    )
    op.create_index("ix_trading_wallets_user_id", "trading_wallets", ["user_id"])

    op.create_table(
        "copy_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("callout_id", sa.Integer(), sa.ForeignKey("callouts.id"), nullable=False),
        sa.Column("token_address", sa.String(44), nullable=False),
        sa.Column("token_symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.Enum("buy", "sell", name="tradeside"), nullable=False),
        sa.Column("sol_amount", sa.Float(), nullable=False),
        sa.Column("token_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("price_at_execution", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("slippage_bps", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("tx_signature", sa.String(128), nullable=True),
        sa.Column("tx_status", sa.Enum("pending", "confirmed", "failed", name="txstatus"), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("jupiter_route", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("parent_trade_id", sa.Integer(), sa.ForeignKey("copy_trades.id"), nullable=True),
        sa.Column("sell_trigger", sa.Enum("take_profit", "stop_loss", "manual", "trailing_stop", name="selltrigger"), nullable=True),
        sa.Column("pnl_sol", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copy_trades_user_id", "copy_trades", ["user_id"])
    op.create_index("ix_copy_trades_callout_id", "copy_trades", ["callout_id"])
    op.create_index("ix_copy_trades_token_address", "copy_trades", ["token_address"])


def downgrade() -> None:
    op.drop_table("copy_trades")
    op.drop_table("trading_wallets")
    op.drop_table("copy_trade_configs")
    op.execute("DROP TYPE IF EXISTS tradeside")
    op.execute("DROP TYPE IF EXISTS txstatus")
    op.execute("DROP TYPE IF EXISTS selltrigger")
