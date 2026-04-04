import enum
from sqlalchemy import BigInteger, Boolean, String, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class SubscriptionStatus(str, enum.Enum):
    pending = "pending"
    trialing = "trialing"
    active = "active"
    expiring = "expiring"
    grace = "grace"
    paused = "paused"
    cancelled = "cancelled"
    expired = "expired"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("plans.id"), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(String(20), default=SubscriptionStatus.pending)

    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    tg_charge_id: Mapped[str | None] = mapped_column(String(128))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship(back_populates="subscriptions")
    payments: Mapped[list["Payment"]] = relationship(back_populates="subscription")

    @property
    def is_active(self) -> bool:
        return self.status in (
            SubscriptionStatus.active,
            SubscriptionStatus.trialing,
            SubscriptionStatus.expiring,
            SubscriptionStatus.grace,
            SubscriptionStatus.cancelled,
        )

    @property
    def tier(self) -> str:
        """返回订阅等级，供外部系统调用"""
        if not self.is_active:
            return "free"
        return self.plan_id.split("_")[1] if "_" in self.plan_id else "basic"
