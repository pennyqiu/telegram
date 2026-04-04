import enum
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PaymentChannel(str, enum.Enum):
    wechat = "wechat"
    alipay = "alipay"


class PaymentOrderStatus(str, enum.Enum):
    pending  = "pending"
    paid     = "paid"
    failed   = "failed"
    expired  = "expired"
    refunded = "refunded"


class PaymentOrder(Base):
    """微信 / 支付宝 支付订单（Stars 走 Telegram 原生通道，不在此表）"""
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 业务关联
    out_trade_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id:      Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    plan_id:      Mapped[str] = mapped_column(String(64), ForeignKey("plans.id"), nullable=False)
    subscription_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("subscriptions.id"))

    # 支付渠道
    channel: Mapped[str] = mapped_column(String(16), nullable=False)   # wechat / alipay
    amount_fen: Mapped[int] = mapped_column(Integer, nullable=False)   # 人民币，单位：分

    # 第三方返回
    trade_no:  Mapped[str | None] = mapped_column(String(128))         # 第三方流水号
    code_url:  Mapped[str | None] = mapped_column(String(512))         # 微信：二维码链接；支付宝：支付页 URL

    # 状态
    status:     Mapped[str]             = mapped_column(String(16), default=PaymentOrderStatus.pending)
    paid_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # 订单过期时间

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship()
    plan: Mapped["Plan"] = relationship()
