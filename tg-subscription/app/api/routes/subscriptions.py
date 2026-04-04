from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.services.subscription_service import subscription_service
from app.models.user import User

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/current")
async def get_current_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await subscription_service.get_active(db, user.id)
    if not sub:
        return {"data": None}
    return {"data": {
        "id": sub.id,
        "plan_id": sub.plan_id,
        "plan_name": sub.plan.name,
        "status": sub.status,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "tier": sub.tier,
    }}
