from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TrackedWallet(Base):
    __tablename__ = "tracked_wallets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(44), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="tracked_wallets")

    __table_args__ = (
        UniqueConstraint("user_id", "wallet_address", name="uq_user_wallet"),
    )
