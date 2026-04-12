from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.dependencies import get_current_user, verify_internal_api_key
from app.services.subscription_service import subscription_service
from app.services.user_service import user_service
from app.models.user import User
from app.models.plan import Plan
from app.bot import get_bot

router = APIRouter(prefix="/payments", tags=["payments"])


class CreateInvoiceRequest(BaseModel):
    plan_id: str


@router.post("/invoice")
async def create_invoice(
    body: CreateInvoiceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.get(Plan, body.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    sub = await subscription_service.create_pending(db, user, plan)

    is_onetime = plan.billing_cycle == "one_time"
    bot = get_bot()
    link = await bot.create_invoice_link(
        title=plan.name,
        description=plan.description or ("一次付款，永久访问" if is_onetime else f"{plan.name}，每月自动续费"),
        payload=f"sub_{plan.id}_{sub.id}",
        currency="XTR",
        prices=[{"label": plan.name, "amount": plan.stars_price}],
        # 买断不传 subscription_period，Telegram 不会设为自动续费
        subscription_period=2592000 if plan.billing_cycle == "monthly" else None,
    )
    return {"data": {"invoice_link": link, "subscription_id": sub.id}}


# ── 对外接口：供 tg-club 查询订阅等级 ─────────────────────────────
@router.get("/verify-tier")
async def verify_subscription_tier(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    """仅供内部服务调用（需 X-Api-Key 头）"""
    tier = await subscription_service.get_tier_by_telegram_id(db, telegram_id)
    return {"telegram_id": telegram_id, "tier": tier}
