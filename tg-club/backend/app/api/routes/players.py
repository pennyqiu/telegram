from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.dependencies import get_tier
from app.services.player_service import player_service
from app.services.subscription_client import can_access

router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
async def list_players(
    position: str | None = Query(None),
    club_id: int | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    tier: str = Depends(get_tier),
    db: AsyncSession = Depends(get_db),
):
    return await player_service.list_players(
        db, tier, position=position, club_id=club_id, status=status, search=search, page=page
    )


@router.get("/free-agents")
async def list_free_agents(
    position: str | None = Query(None),
    tier: str = Depends(get_tier),
    db: AsyncSession = Depends(get_db),
):
    if not can_access(tier, "basic"):
        raise HTTPException(status_code=403, detail="Basic subscription required")
    return await player_service.list_players(db, tier, status="free_agent", position=position)


@router.get("/{player_id}")
async def get_player(
    player_id: int,
    tier: str = Depends(get_tier),
    db: AsyncSession = Depends(get_db),
):
    data = await player_service.get_player(db, player_id, tier)
    if not data:
        raise HTTPException(status_code=404, detail="Player not found")
    return {"data": data}


@router.get("/{player_id}/similar")
async def get_similar_players(
    player_id: int,
    tier: str = Depends(get_tier),
    db: AsyncSession = Depends(get_db),
):
    if not can_access(tier, "pro"):
        raise HTTPException(status_code=403, detail="Pro subscription required")
    result = await player_service.get_similar(db, player_id)
    return {"data": result}
