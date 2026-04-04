from datetime import datetime, UTC
from telegram import Update
from telegram.ext import ContextTypes
from app.services.subscription_service import subscription_service
from app.services.user_service import user_service
from app.models.payment import Payment, PaymentStatus
from app.core.redis import redis_client


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    try:
        parts = query.invoice_payload.split("_")
        plan_id = "_".join(parts[1:-1])
        async with context.bot_data["db_factory"]() as db:
            from app.models.plan import Plan
            plan = await db.get(Plan, plan_id)
        if not plan or not plan.is_active:
            await query.answer(ok=False, error_message="该套餐已下架，请重新选择。")
            return
        await query.answer(ok=True)
    except Exception:
        await query.answer(ok=False, error_message="验证失败，请稍后重试。")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    charge_id = payment.telegram_payment_charge_id

    if await redis_client.exists(f"payment:processed:{charge_id}"):
        return
    await redis_client.set(f"payment:processed:{charge_id}", "1", ex=2592000)

    parts = payment.invoice_payload.split("_")
    sub_id = int(parts[-1])

    async with context.bot_data["db_factory"]() as db:
        if payment.is_recurring:
            sub = await subscription_service.handle_renewal(db, sub_id, charge_id, payment.total_amount)
            text = "自动续费成功！感谢您的持续支持。"
        else:
            sub = await subscription_service.activate(db, sub_id, charge_id, payment.total_amount)
            pmt = Payment(
                subscription_id=sub.id,
                user_id=sub.user_id,
                stars_amount=payment.total_amount,
                tg_charge_id=charge_id,
                is_recurring=False,
                status=PaymentStatus.paid,
                paid_at=datetime.now(UTC),
            )
            db.add(pmt)
            text = (
                f"订阅成功！\n"
                f"套餐：{sub.plan.name}\n"
                f"有效期至：{sub.expires_at.strftime('%Y-%m-%d')}\n\n"
                f"前往付费频道申请加入，Bot 将自动审核通过。"
            )

    await context.bot.send_message(update.effective_user.id, text)
