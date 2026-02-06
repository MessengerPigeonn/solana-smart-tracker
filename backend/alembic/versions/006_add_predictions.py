"""add predictions table

Revision ID: 006
Revises: 005
Create Date: 2026-02-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sport", sa.String(20), nullable=False),
        sa.Column("league", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("home_team", sa.String(100), nullable=False),
        sa.Column("away_team", sa.String(100), nullable=False),
        sa.Column("commence_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bet_type", sa.String(20), nullable=False),
        sa.Column("pick", sa.String(200), nullable=False),
        sa.Column("pick_detail", sa.JSON(), nullable=True),
        sa.Column("best_odds", sa.Float(), nullable=False),
        sa.Column("best_bookmaker", sa.String(50), nullable=False),
        sa.Column("implied_probability", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("edge", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("parlay_legs", sa.JSON(), nullable=True),
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("actual_score", sa.String(50), nullable=True),
        sa.Column("pnl_units", sa.Float(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictions_event_id", "predictions", ["event_id"])
    op.create_index("ix_predictions_sport", "predictions", ["sport"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])
    op.create_index("ix_predictions_result", "predictions", ["result"])


def downgrade() -> None:
    op.drop_table("predictions")
