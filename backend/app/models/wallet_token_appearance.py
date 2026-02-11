from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class WalletTokenAppearance(Base):
    __tablename__ = "wallet_token_appearances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    token_address: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    appeared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # early_buyer / deployer / bundler
