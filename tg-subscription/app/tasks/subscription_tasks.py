from datetime import datetime, timedelta, UTC
from celery import shared_task
from app.tasks.celery_app import celery_app


@celery_app.task(name="check_expiring_subscriptions")
def check_expiring_subscriptions():
    from app.core.database import AsyncSessionLocal
    from app.models.subscription import Subscription, SubscriptionStatus
    import asyncio

    async def _run():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            threshold = datetime.now(UTC) + timedelta(days=3)
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.active,
                    Subscription.expires_at <= threshold,
                    Subscription.expires_at > datetime.now(UTC),
                )
            )
            subs = result.scalars().all()
            for sub in subs:
                # 买断套餐永久有效，不发到期提醒
                from app.models.plan import Plan
                plan = await db.get(Plan, sub.plan_id)
                if plan and plan.billing_cycle == "one_time":
                    continue
                send_expiry_reminder.delay(sub.id)
                sub.status = SubscriptionStatus.expiring
            await db.commit()
        return len(subs)

    return asyncio.run(_run())


@celery_app.task(name="expire_subscriptions")
def expire_subscriptions():
    from app.core.database import AsyncSessionLocal
    from app.models.subscription import Subscription, SubscriptionStatus
    import asyncio

    async def _run():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            now = datetime.now(UTC)
            # active/expiring → grace
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status.in_([SubscriptionStatus.active, SubscriptionStatus.expiring]),
                    Subscription.expires_at <= now,
                )
            )
            for sub in result.scalars().all():
                sub.status = SubscriptionStatus.grace
                sub.grace_ends_at = now + timedelta(days=3)

            # grace → expired
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.grace,
                    Subscription.grace_ends_at <= now,
                )
            )
            for sub in result.scalars().all():
                sub.status = SubscriptionStatus.expired
                remove_channel_access.delay(sub.user_id, sub.plan_id)

            await db.commit()

    asyncio.run(_run())


@celery_app.task(name="send_expiry_reminder")
def send_expiry_reminder(sub_id: int):
    from app.core.database import AsyncSessionLocal
    from app.models.subscription import Subscription
    from app.bot import get_bot
    import asyncio

    async def _run():
        async with AsyncSessionLocal() as db:
            sub = await db.get(Subscription, sub_id)
            if not sub:
                return
            bot = get_bot()
            await bot.send_message(
                sub.user.telegram_id,
                f"您的 {sub.plan.name} 将于 3 天后到期。\n\n"
                f"Telegram 自动续费已开启，到期将自动扣除 {sub.plan.stars_price} Stars。\n"
                f"如需取消，请前往 Telegram 设置 → 订阅。"
            )

    asyncio.run(_run())


@celery_app.task(name="remove_channel_access")
def remove_channel_access(user_id: int, plan_id: str):
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.models.plan import Plan
    from app.bot import get_bot
    import asyncio, json

    async def _run():
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            plan = await db.get(Plan, plan_id)
            if not user or not plan:
                return
            # 买断套餐永久有效，不执行移出
            if plan.billing_cycle == "one_time":
                return
            bot = get_bot()
            for channel_id in plan.channels:
                try:
                    await bot.ban_chat_member(int(channel_id), user.telegram_id)
                    await asyncio.sleep(0.5)
                    await bot.unban_chat_member(int(channel_id), user.telegram_id)
                except Exception:
                    pass

    asyncio.run(_run())
