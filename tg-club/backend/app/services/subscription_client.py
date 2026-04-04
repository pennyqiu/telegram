"""
订阅系统客户端 —— tg-club 与 tg-subscription 的唯一耦合点。
通过 HTTP 调用订阅系统的内部 API 查询用户订阅等级，不共享代码也不共享数据库。
"""
import httpx
from app.core.config import settings
from app.core.redis import redis_client

TIER_CACHE_TTL = 300  # 5 分钟缓存


async def get_user_tier(telegram_id: int) -> str:
    """
    查询 telegram_id 对应的订阅等级。
    返回值：'free' | 'basic' | 'pro'
    """
    cache_key = f"club:tier:{telegram_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.subscription_service_url}/api/v1/payments/verify-tier",
                params={"telegram_id": telegram_id},
                headers={"X-Api-Key": settings.subscription_internal_api_key},
            )
            resp.raise_for_status()
            tier = resp.json().get("tier", "free")
    except Exception:
        tier = "free"

    await redis_client.set(cache_key, tier, ex=TIER_CACHE_TTL)
    return tier


def can_access(tier: str, required: str) -> bool:
    """判断当前订阅等级是否满足访问要求"""
    order = {"free": 0, "basic": 1, "pro": 2}
    return order.get(tier, 0) >= order.get(required, 0)
