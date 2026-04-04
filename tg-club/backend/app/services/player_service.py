from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.player import Player, PlayerStatus
from app.services.subscription_client import can_access


class PlayerService:

    def filter_by_tier(self, player: Player, tier: str) -> dict:
        base = {
            "id": player.id,
            "name": player.name,
            "position": player.position,
            "nationality": player.nationality,
            "status": player.status,
            "current_club_id": player.current_club_id,
            "current_club_name": player.current_club.name if player.current_club else None,
        }
        if not can_access(tier, player.access_tier):
            base["_locked"] = True
            base["_required_tier"] = player.access_tier
            return base

        base.update({
            "photo_url": player.photo_url,
            "birth_date": player.birth_date.isoformat() if player.birth_date else None,
            "height_cm": player.height_cm,
            "weight_kg": player.weight_kg,
            "preferred_foot": player.preferred_foot,
            "jersey_number": player.jersey_number,
            "rating": float(player.rating) if player.rating else None,
            "tags": player.tags,
        })

        if can_access(tier, "pro"):
            base.update({
                "bio": player.bio,
                "market_value": player.market_value,
            })

        return base

    async def list_players(
        self, db: AsyncSession, tier: str,
        position: str | None = None,
        club_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        page: int = 1, size: int = 20,
    ) -> dict:
        q = select(Player)
        if position:
            q = q.where(Player.position == position)
        if club_id:
            q = q.where(Player.current_club_id == club_id)
        if status:
            q = q.where(Player.status == status)
        if search:
            q = q.where(or_(Player.name.ilike(f"%{search}%"), Player.name_en.ilike(f"%{search}%")))
        q = q.offset((page - 1) * size).limit(size)
        result = await db.execute(q)
        players = result.scalars().all()
        return {"data": [self.filter_by_tier(p, tier) for p in players]}

    async def get_player(self, db: AsyncSession, player_id: int, tier: str) -> dict | None:
        player = await db.get(Player, player_id)
        if not player:
            return None
        data = self.filter_by_tier(player, tier)
        if can_access(tier, "pro") and not data.get("_locked"):
            transfer_limit = None
        elif can_access(tier, "basic"):
            transfer_limit = 1
        else:
            transfer_limit = 0

        if transfer_limit != 0:
            transfers = player.transfers[:transfer_limit] if transfer_limit else player.transfers
            data["transfers"] = [
                {
                    "id": t.id,
                    "type": t.type,
                    "from_club": t.from_club.name if t.from_club else None,
                    "to_club": t.to_club.name if t.to_club else None,
                    "transfer_date": t.transfer_date.isoformat(),
                    "fee_display": t.fee_display,
                }
                for t in transfers
            ]
        return data

    async def get_similar(self, db: AsyncSession, player_id: int, limit: int = 5) -> list[dict]:
        source = await db.get(Player, player_id)
        if not source:
            return []

        result = await db.execute(
            select(Player).where(
                Player.id != player_id,
                Player.position == source.position,
                Player.status == PlayerStatus.active,
            ).limit(50)
        )
        candidates = result.scalars().all()

        def score(p: Player) -> float:
            s = 0.4
            if source.height_cm and p.height_cm and abs(source.height_cm - p.height_cm) < 5:
                s += 0.1
            if source.birth_date and p.birth_date:
                age_diff = abs((source.birth_date - p.birth_date).days / 365)
                if age_diff < 3:
                    s += 0.1
            if source.rating and p.rating and abs(float(source.rating) - float(p.rating)) < 1:
                s += 0.2
            common = set(source.tags or []) & set(p.tags or [])
            denom = max(len(source.tags or []), len(p.tags or []), 1)
            s += (len(common) / denom) * 0.2
            return s

        ranked = sorted(candidates, key=score, reverse=True)[:limit]
        return [{"id": p.id, "name": p.name, "position": p.position, "photo_url": p.photo_url} for p in ranked]


player_service = PlayerService()
