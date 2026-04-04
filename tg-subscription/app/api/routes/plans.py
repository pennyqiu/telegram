from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.plan import Plan

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("")
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order)
    )
    plans = result.scalars().all()
    return {"data": [
        {
            "id": p.id, "name": p.name, "description": p.description,
            "stars_price": p.stars_price, "billing_cycle": p.billing_cycle,
            "trial_days": p.trial_days, "features": p.features,
        }
        for p in plans
    ]}
