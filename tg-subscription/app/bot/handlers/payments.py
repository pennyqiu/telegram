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
    # 付费成功后发送课程访问链接（含自动生成的账号）
    if not payment.is_recurring:
        await _send_course_access(context.bot, update.effective_user.id, sub.user_id, sub.plan)


async def _provision_and_send(bot, telegram_id: int, user_id: int, display_name: str, plan) -> None:
    """调用内部 API 生成课程账号，然后发送给用户"""
    from app.core.config import settings
    import httpx

    if not settings.course_url:
        return

    # 调用内部 provision 接口生成账号
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://localhost:8000/api/v1/course/provision",
            json={"telegram_id": telegram_id, "display_name": display_name},
            headers={"X-Api-Key": settings.internal_api_key},
            timeout=10,
        )

    if resp.status_code != 200:
        # provision 失败时退回发静态链接
        await bot.send_message(
            chat_id=telegram_id,
            text=f"🎓 课程地址：{settings.course_url}\n\n如遇登录问题请联系客服。",
        )
        return

    data = resp.json()
    login    = data["login"]
    password = data["password"]
    is_onetime = plan.billing_cycle == "one_time"
    validity = "永久有效，无需续费。" if is_onetime else f"订阅有效期内可访问。"

    await bot.send_message(
        chat_id=telegram_id,
        text=(
            f"🎓 *课程访问信息*\n\n"
            f"地址：{settings.course_url}\n\n"
            f"用户名：`{login}`\n"
            f"密码：`{password}`\n\n"
            f"_{validity}_\n"
            f"_请妥善保存，密码仅展示一次。_\n\n"
            f"💡 建议在浏览器中打开并收藏，课程进度自动保存。"
        ),
        parse_mode="Markdown",
    )


async def _send_course_access(bot, telegram_id: int, user_id: int, plan):
    """付款成功后生成账号并私信课程访问信息"""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        display_name = user.first_name if user else f"用户{telegram_id}"

    await _provision_and_send(bot, telegram_id, user_id, display_name, plan)
