import enum
from sqlalchemy import BigInteger, Boolean, Integer, String, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subscriptions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    tg_charge_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[PaymentStatus] = mapped_column(String(20), default=PaymentStatus.pending)

    paid_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    billing_period_start: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    billing_period_end: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subscription: Mapped["Subscription"] = relationship(back_populates="payments")
    user: Mapped["User"] = relationship(back_populates="payments")
