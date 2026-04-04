from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.club import Club
from app.services.subscription_client import can_access


class ClubService:

    def filter_by_tier(self, club: Club, tier: str) -> dict:
        base = {
            "id": club.id,
            "name": club.name,
            "short_name": club.short_name,
            "logo_url": club.logo_url,
            "country": club.country,
            "league_name": club.league.name if club.league else None,
            "status": club.status,
        }
        if not can_access(tier, club.access_tier):
            base["_locked"] = True
            base["_required_tier"] = club.access_tier
            return base

        base.update({
            "founded_year": club.founded_year,
            "stadium": club.stadium,
            "stadium_capacity": club.stadium_capacity,
            "description": club.description,
        })
        return base

    async def list_clubs(
        self, db: AsyncSession, tier: str,
        league_id: int | None = None,
        search: str | None = None,
        page: int = 1, size: int = 20,
    ) -> dict:
        from app.models.club import ClubStatus
        q = select(Club).where(Club.status == ClubStatus.active)
        if league_id:
            q = q.where(Club.league_id == league_id)
        if search:
            q = q.where(or_(Club.name.ilike(f"%{search}%"), Club.short_name.ilike(f"%{search}%")))
        q = q.offset((page - 1) * size).limit(size)
        result = await db.execute(q)
        clubs = result.scalars().all()
        return {"data": [self.filter_by_tier(c, tier) for c in clubs]}

    async def get_club(self, db: AsyncSession, club_id: int, tier: str) -> dict | None:
        club = await db.get(Club, club_id)
        if not club:
            return None
        data = self.filter_by_tier(club, tier)
        if not data.get("_locked") and can_access(tier, "basic"):
            data["players"] = [
                {"id": p.id, "name": p.name, "position": p.position, "photo_url": p.photo_url}
                for p in club.players if p.status == "active"
            ]
        return data


club_service = ClubService()
