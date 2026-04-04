from datetime import datetime, timedelta, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.models.plan import Plan
from app.models.subscription import Subscription, SubscriptionStatus
from app.core.redis import redis_client


class SubscriptionService:

    async def activate_from_third_party(
        self, db: AsyncSession, user: User, plan: Plan
    ) -> Subscription:
        """微信/支付宝支付成功后激活或续期订阅（无 tg_charge_id）"""
        from sqlalchemy import select as _select
        now = datetime.now(UTC)
        # 尝试找到同套餐的现有订阅来续期
        existing = await self.get_active(db, user.id)
        if existing and existing.plan_id == plan.id:
            base = max(existing.expires_at, now)
            existing.expires_at = base + self._cycle_delta(plan.billing_cycle)
            existing.status = SubscriptionStatus.active
            await self._invalidate_cache(user.id)
            return existing
        # 否则新建
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.active,
            started_at=now,
            expires_at=now + self._cycle_delta(plan.billing_cycle),
        )
        db.add(sub)
        await db.flush()
        await self._invalidate_cache(user.id)
        return sub

    async def get_active(self, db: AsyncSession, user_id: int) -> Subscription | None:
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_([
                    SubscriptionStatus.active, SubscriptionStatus.trialing,
                    SubscriptionStatus.expiring, SubscriptionStatus.grace,
                    SubscriptionStatus.cancelled,
                ]),
                Subscription.expires_at > datetime.now(UTC),
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_by_telegram_id(self, db: AsyncSession, telegram_id: int) -> Subscription | None:
        result = await db.execute(
            select(Subscription)
            .join(User, Subscription.user_id == User.id)
            .where(
                User.telegram_id == telegram_id,
                Subscription.status.in_([
                    SubscriptionStatus.active, SubscriptionStatus.trialing,
                    SubscriptionStatus.expiring, SubscriptionStatus.grace,
                    SubscriptionStatus.cancelled,
                ]),
                Subscription.expires_at > datetime.now(UTC),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_active(self, db: AsyncSession, user_id: int) -> bool:
        cache_key = f"sub:active:{user_id}"
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return cached == "1"
        sub = await self.get_active(db, user_id)
        await redis_client.set(cache_key, "1" if sub else "0", ex=300)
        return sub is not None

    async def create_pending(self, db: AsyncSession, user: User, plan: Plan) -> Subscription:
        sub = Subscription(user_id=user.id, plan_id=plan.id, status=SubscriptionStatus.pending)
        db.add(sub)
        await db.flush()
        return sub

    async def activate(
        self, db: AsyncSession, sub_id: int, charge_id: str, stars_amount: int
    ) -> Subscription:
        sub = await db.get(Subscription, sub_id)
        plan = await db.get(Plan, sub.plan_id)
        now = datetime.now(UTC)

        sub.status = SubscriptionStatus.active
        sub.started_at = now
        sub.expires_at = now + self._cycle_delta(plan.billing_cycle)
        sub.tg_charge_id = charge_id

        await self._invalidate_cache(sub.user_id)
        return sub

    async def handle_renewal(
        self, db: AsyncSession, sub_id: int, charge_id: str, stars_amount: int
    ) -> Subscription:
        sub = await db.get(Subscription, sub_id)
        plan = await db.get(Plan, sub.plan_id)
        base = max(sub.expires_at, datetime.now(UTC))
        sub.expires_at = base + self._cycle_delta(plan.billing_cycle)
        sub.status = SubscriptionStatus.active
        sub.grace_ends_at = None
        await self._invalidate_cache(sub.user_id)
        return sub

    async def get_tier_by_telegram_id(self, db: AsyncSession, telegram_id: int) -> str:
        """给外部系统（tg-club）查询订阅等级用"""
        sub = await self.get_active_by_telegram_id(db, telegram_id)
        if not sub:
            return "free"
        return sub.tier

    async def _invalidate_cache(self, user_id: int):
        await redis_client.delete(f"sub:active:{user_id}")

    @staticmethod
    def _cycle_delta(cycle: str) -> timedelta:
        return {"monthly": timedelta(days=30), "quarterly": timedelta(days=90), "yearly": timedelta(days=365)}.get(cycle, timedelta(days=30))


subscription_service = SubscriptionService()
