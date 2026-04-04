from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.dependencies import get_tier
from app.services.club_service import club_service

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("")
async def list_clubs(
    league_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    tier: str = Depends(get_tier),
    db: AsyncSession = Depends(get_db),
):
    return await club_service.list_clubs(db, tier, league_id=league_id, search=search, page=page)


@router.get("/{club_id}")
async def get_club(
    club_id: int,
    tier: str = Depends(get_tier),
    db: AsyncSession = Depends(get_db),
):
    data = await club_service.get_club(db, club_id, tier)
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Club not found")
    return {"data": data}
