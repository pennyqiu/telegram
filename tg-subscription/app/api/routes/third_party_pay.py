"""
第三方支付路由（微信支付 + 支付宝）

端点一览：
  POST /api/v1/pay/create          创建支付订单（wechat / alipay）
  GET  /api/v1/pay/status/{no}     轮询支付状态
  GET  /api/v1/pay/qrcode/{no}     获取微信二维码图片（PNG）
  POST /webhooks/wechat            微信支付异步通知（在 main.py 挂载）
  POST /webhooks/alipay            支付宝异步通知（在 main.py 挂载）
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.payment_order import PaymentOrder, PaymentOrderStatus, PaymentChannel
from app.models.plan import Plan
from app.models.user import User
from app.services import wechat_pay, alipay_service, xunhupay_service
from app.services.subscription_service import subscription_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pay", tags=["third-party-pay"])


# ── 辅助 ─────────────────────────────────────────────────────────

def _make_out_trade_no(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


async def _activate_subscription(db: AsyncSession, order: PaymentOrder):
    """支付成功后激活或续期订阅"""
    plan = await db.get(Plan, order.plan_id)
    user = await db.get(User, order.user_id)
    if not plan or not user:
        return
    sub = await subscription_service.activate_from_third_party(db, user, plan)
    order.subscription_id = sub.id

    # 主动通知用户
    try:
        from app.main import get_bot
        bot = get_bot()
        expires = sub.expires_at.strftime("%Y-%m-%d")
        channel_name = "微信支付" if order.channel == "wechat" else "支付宝"
        await bot.send_message(
            chat_id=user.telegram_id,
            text=(
                f"✅ 支付成功！\n\n"
                f"套餐：{plan.name}\n"
                f"渠道：{channel_name}\n"
                f"有效期至：{expires}\n\n"
                f"感谢订阅，尽情享用吧！"
            ),
        )
        # 发送课程账号（含自动生成的用户名+密码）
        if settings.course_url:
            from app.bot.handlers.payments import _provision_and_send
            await _provision_and_send(
                bot,
                telegram_id=user.telegram_id,
                user_id=user.id,
                display_name=user.first_name,
                plan=plan,
            )
    except Exception as e:
        logger.warning("通知用户失败: %s", e)


# ── 创建支付订单 ────────────────────────────────────────────────

class CreatePayRequest(BaseModel):
    plan_id: str
    channel: str   # "wechat" | "alipay"


@router.post("/create")
async def create_payment(
    body: CreatePayRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.channel not in (PaymentChannel.wechat, PaymentChannel.alipay):
        raise HTTPException(status_code=400, detail="channel 只支持 wechat / alipay")

    plan = await db.get(Plan, body.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="套餐不存在")
    if not plan.cny_price_fen:
        raise HTTPException(status_code=400, detail="该套餐未开通人民币支付")

    out_trade_no = _make_out_trade_no(body.channel[:2])
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    order = PaymentOrder(
        out_trade_no=out_trade_no,
        user_id=user.id,
        plan_id=plan.id,
        channel=body.channel,
        amount_fen=plan.cny_price_fen,
        expires_at=expires_at,
    )

    description = f"{plan.name}订阅"
    return_url = f"{settings.mini_app_url}/pay/result?no={out_trade_no}"

    # ── 虎皮椒聚合支付（优先）────────────────────────────────────
    if settings.xunhupay_enabled:
        result = xunhupay_service.create_order(
            out_trade_no=out_trade_no,
            amount_fen=plan.cny_price_fen,
            subject=description,
            channel=body.channel,
            notify_url=settings.xunhupay_notify_url,
            return_url=return_url,
        )
        order.code_url = result.get("code_url") or result.get("pay_url")
        db.add(order)
        if body.channel == PaymentChannel.wechat:
            return {"data": {
                "channel": "wechat",
                "out_trade_no": out_trade_no,
                "amount_fen": plan.cny_price_fen,
                "amount_cny": f"¥{plan.cny_price_fen / 100:.2f}",
                "expires_at": expires_at.isoformat(),
                # 前端通过 /pay/qrcode/{out_trade_no} 获取二维码
            }}
        else:
            return {"data": {
                "channel": "alipay",
                "out_trade_no": out_trade_no,
                "amount_fen": plan.cny_price_fen,
                "amount_cny": f"¥{plan.cny_price_fen / 100:.2f}",
                "pay_url": result.get("pay_url"),
                "expires_at": expires_at.isoformat(),
            }}

    # ── 官方直连支付（需商户账号）────────────────────────────────
    if body.channel == PaymentChannel.wechat:
        code_url = wechat_pay.create_native_order(
            out_trade_no=out_trade_no,
            amount_fen=plan.cny_price_fen,
            description=description,
        )
        order.code_url = code_url
        db.add(order)
        return {"data": {
            "channel": "wechat",
            "out_trade_no": out_trade_no,
            "amount_fen": plan.cny_price_fen,
            "amount_cny": f"¥{plan.cny_price_fen / 100:.2f}",
            "expires_at": expires_at.isoformat(),
            # 前端通过 /pay/qrcode/{out_trade_no} 获取二维码图片
        }}

    else:  # alipay
        return_url = f"{settings.mini_app_url}/pay/result?no={out_trade_no}"
        pay_url = alipay_service.create_wap_pay_url(
            out_trade_no=out_trade_no,
            amount_fen=plan.cny_price_fen,
            subject=description,
            return_url=return_url,
        )
        order.code_url = pay_url
        db.add(order)
        return {"data": {
            "channel": "alipay",
            "out_trade_no": out_trade_no,
            "amount_fen": plan.cny_price_fen,
            "amount_cny": f"¥{plan.cny_price_fen / 100:.2f}",
            "pay_url": pay_url,
            "expires_at": expires_at.isoformat(),
        }}


# ── 轮询支付状态 ────────────────────────────────────────────────

@router.get("/status/{out_trade_no}")
async def get_payment_status(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentOrder).where(PaymentOrder.out_trade_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 若本地已是终态，直接返回
    if order.status in (PaymentOrderStatus.paid, PaymentOrderStatus.failed, PaymentOrderStatus.expired):
        return {"data": {"status": order.status, "out_trade_no": out_trade_no}}

    # 超时检查
    if order.expires_at and datetime.now(timezone.utc) > order.expires_at:
        order.status = PaymentOrderStatus.expired
        return {"data": {"status": "expired", "out_trade_no": out_trade_no}}

    # 主动向第三方查询（减少轮询对第三方的压力，可配合前端 5s 一次）
    try:
        if settings.xunhupay_enabled:
            # 虎皮椒统一查询（微信/支付宝均走这里）
            resp = xunhupay_service.query_order(out_trade_no)
            if resp.get("trade_status") == "TRADE_SUCCESS":
                order.status = PaymentOrderStatus.paid
                order.trade_no = resp.get("trade_no")
                order.paid_at = datetime.now(timezone.utc)
                await _activate_subscription(db, order)
        elif order.channel == PaymentChannel.wechat:
            resp = wechat_pay.query_order(out_trade_no)
            if resp.get("trade_state") == "SUCCESS":
                order.status = PaymentOrderStatus.paid
                order.trade_no = resp.get("transaction_id")
                order.paid_at = datetime.now(timezone.utc)
                await _activate_subscription(db, order)
        else:
            resp = alipay_service.query_order(out_trade_no)
            if resp.get("trade_status") == "TRADE_SUCCESS":
                order.status = PaymentOrderStatus.paid
                order.trade_no = resp.get("trade_no")
                order.paid_at = datetime.now(timezone.utc)
                await _activate_subscription(db, order)
    except Exception as e:
        logger.warning("主动查询第三方失败: %s", e)

    return {"data": {"status": order.status, "out_trade_no": out_trade_no}}


# ── 微信二维码图片接口 ───────────────────────────────────────────

@router.get("/qrcode/{out_trade_no}")
async def get_wechat_qrcode(
    out_trade_no: str,
    db: AsyncSession = Depends(get_db),
):
    """返回 PNG 格式的微信支付二维码图片"""
    result = await db.execute(
        select(PaymentOrder).where(PaymentOrder.out_trade_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    if not order or order.channel != PaymentChannel.wechat or not order.code_url:
        raise HTTPException(status_code=404)

    try:
        import qrcode
        qr = qrcode.make(order.code_url)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/png")
    except ImportError:
        # 未安装 qrcode 库时直接返回 code_url 让前端自己生成
        raise HTTPException(status_code=501, detail="qrcode library not installed")


# ── 微信支付异步通知（Webhook） ────────────────────────────────

async def wechat_notify(request: Request, db: AsyncSession):
    headers = dict(request.headers)
    body = await request.body()
    data = wechat_pay.decode_notification(headers, body)
    if not data:
        return Response(content='{"code":"FAIL"}', media_type="application/json")

    out_trade_no = data.get("out_trade_no")
    if not out_trade_no:
        return Response(content='{"code":"FAIL"}', media_type="application/json")

    async with db:
        result = await db.execute(
            select(PaymentOrder).where(PaymentOrder.out_trade_no == out_trade_no)
        )
        order = result.scalar_one_or_none()
        if order and order.status == PaymentOrderStatus.pending:
            order.status = PaymentOrderStatus.paid
            order.trade_no = data.get("transaction_id")
            order.paid_at = datetime.now(timezone.utc)
            await _activate_subscription(db, order)
            await db.commit()

    return Response(content='{"code":"SUCCESS"}', media_type="application/json")


# ── 支付宝异步通知（Webhook） ──────────────────────────────────

async def alipay_notify(request: Request, db: AsyncSession):
    form = await request.form()
    data = dict(form)
    if not alipay_service.verify_notification(data):
        return Response(content="fail")

    out_trade_no = data.get("out_trade_no")
    trade_status = data.get("trade_status")

    if trade_status == "TRADE_SUCCESS" and out_trade_no:
        async with db:
            result = await db.execute(
                select(PaymentOrder).where(PaymentOrder.out_trade_no == out_trade_no)
            )
            order = result.scalar_one_or_none()
            if order and order.status == PaymentOrderStatus.pending:
                order.status = PaymentOrderStatus.paid
                order.trade_no = data.get("trade_no")
                order.paid_at = datetime.now(timezone.utc)
                await _activate_subscription(db, order)
                await db.commit()

    return Response(content="success")


# ── 虎皮椒异步通知（Webhook，微信+支付宝统一） ────────────────────

async def xunhupay_notify(request: Request, db: AsyncSession):
    """
    虎皮椒异步通知（POST form）
    配置回调地址：https://你的域名/webhooks/xunhupay
    """
    form = await request.form()
    data = dict(form)

    parsed = xunhupay_service.extract_notification(data)
    if not parsed:
        return Response(content="fail")

    out_trade_no = parsed.get("out_trade_no")
    if parsed.get("trade_status") == "TRADE_SUCCESS" and out_trade_no:
        result = await db.execute(
            select(PaymentOrder).where(PaymentOrder.out_trade_no == out_trade_no)
        )
        order = result.scalar_one_or_none()
        if order and order.status == PaymentOrderStatus.pending:
            order.status = PaymentOrderStatus.paid
            order.trade_no = parsed.get("trade_no")
            order.paid_at = datetime.now(timezone.utc)
            await _activate_subscription(db, order)
            await db.commit()

    return Response(content="success")
