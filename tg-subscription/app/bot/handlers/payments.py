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
            is_onetime = sub.plan.billing_cycle == "one_time"
            if is_onetime:
                text = (
                    f"🎉 购买成功！\n\n"
                    f"课程：{sub.plan.name}\n"
                    f"有效期：永久\n\n"
                    f"稍后将发送课程访问链接，请留意私信。"
                )
            else:
                text = (
                    f"✅ 订阅成功！\n"
                    f"套餐：{sub.plan.name}\n"
                    f"有效期至：{sub.expires_at.strftime('%Y-%m-%d')}\n\n"
                    f"前往付费频道申请加入，Bot 将自动审核通过。"
                )

    await context.bot.send_message(update.effective_user.id, text)
    # 付费成功后发送课程访问链接
    if not payment.is_recurring:
        await _send_course_access(context.bot, update.effective_user.id, sub.plan)


async def _send_course_access(bot, telegram_id: int, plan):
    """付款成功后私信课程访问地址"""
    from app.core.config import settings
    if not settings.course_url:
        return
    is_onetime = plan.billing_cycle == "one_time"
    validity_note = "永久有效，无需续费。" if is_onetime else "订阅有效期内可访问。"
    await bot.send_message(
        chat_id=telegram_id,
        text=(
            f"🎓 *课程访问地址*\n\n"
            f"点击下方链接即可开始学习《美股系统学习》完整课程：\n\n"
            f"👉 {settings.course_url}\n\n"
            f"_{validity_note}_\n\n"
            f"💡 建议在浏览器中打开并收藏，课程进度自动保存到本地。"
        ),
        parse_mode="Markdown",
    )
