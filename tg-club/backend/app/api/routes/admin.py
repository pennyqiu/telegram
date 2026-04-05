from datetime import date, datetime, UTC

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    AdminContext, verify_admin_token, require_super_admin, create_admin_token,
)
from app.core.database import get_db
from app.models.admin_user import AdminUser, AdminRole
from app.models.club import Club
from app.models.player import Player, PlayerStatus
from app.models.transfer import Transfer, TransferType, Retirement

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 内容编辑路由：admin + editor 都可访问
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin_token)],
)

public_router = APIRouter(prefix="/admin", tags=["admin"])


# ══════════════════════════════════════════════════════════════════
# 登录（不需要鉴权，覆盖 router 级别的依赖）
# ══════════════════════════════════════════════════════════════════

class LoginBody(BaseModel):
    username: str
    password: str


@public_router.post("/auth/login")
async def admin_login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AdminUser).where(AdminUser.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not pwd_ctx.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.last_login_at = datetime.now(UTC)
    return {
        "token":    create_admin_token(user.username, user.role),
        "username": user.username,
        "role":     user.role,
    }


# ── 当前登录人信息 ────────────────────────────────────────────────

@router.get("/auth/me", dependencies=[])
async def admin_me(
    ctx: AdminContext = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).where(AdminUser.username == ctx.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404)
    return {"username": user.username, "role": user.role, "last_login_at": user.last_login_at}


# ══════════════════════════════════════════════════════════════════
# 账号管理（仅超级管理员）
# ══════════════════════════════════════════════════════════════════

class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = AdminRole.editor

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in (AdminRole.admin, AdminRole.editor):
            raise ValueError("role 只能是 admin 或 editor")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("密码长度不能少于 8 位")
        return v


class UpdateUserBody(BaseModel):
    is_active: bool | None = None
    role: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v and v not in (AdminRole.admin, AdminRole.editor):
            raise ValueError("role 只能是 admin 或 editor")
        return v


class ChangePasswordBody(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("密码长度不能少于 8 位")
        return v


@router.get("/users", dependencies=[Depends(require_super_admin)])
async def list_admin_users(db: AsyncSession = Depends(get_db)):
    """列出所有管理账号（仅超级管理员）"""
    result = await db.execute(select(AdminUser).order_by(AdminUser.created_at))
    users = result.scalars().all()
    return {"data": [
        {
            "id":            u.id,
            "username":      u.username,
            "role":          u.role,
            "is_active":     u.is_active,
            "created_by":    u.created_by,
            "last_login_at": u.last_login_at,
            "created_at":    u.created_at,
        }
        for u in users
    ]}


@router.post("/users", status_code=201, dependencies=[Depends(require_super_admin)])
async def create_admin_user(
    body: CreateUserBody,
    ctx: AdminContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建新的管理账号（仅超级管理员）"""
    existing = await db.execute(select(AdminUser).where(AdminUser.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"用户名「{body.username}」已存在")

    user = AdminUser(
        username=body.username,
        password_hash=pwd_ctx.hash(body.password),
        role=body.role,
        created_by=ctx.username,
    )
    db.add(user)
    await db.flush()
    return {"data": {"id": user.id, "username": user.username, "role": user.role}}


@router.put("/users/{user_id}", dependencies=[Depends(require_super_admin)])
async def update_admin_user(
    user_id: int,
    body: UpdateUserBody,
    ctx: AdminContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """修改账号状态或角色（仅超级管理员）"""
    user = await db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 不允许超级管理员降级自己
    if user.username == ctx.username and body.role == AdminRole.editor:
        raise HTTPException(status_code=400, detail="不能降级自己的账号")

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role is not None:
        user.role = body.role
    return {"data": {"id": user.id, "username": user.username, "role": user.role, "is_active": user.is_active}}


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_super_admin)])
async def reset_admin_password(
    user_id: int,
    body: ChangePasswordBody,
    db: AsyncSession = Depends(get_db),
):
    """重置任意账号密码（仅超级管理员）"""
    user = await db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = pwd_ctx.hash(body.new_password)
    return {"ok": True}


@router.delete("/users/{user_id}", dependencies=[Depends(require_super_admin)])
async def delete_admin_user(
    user_id: int,
    ctx: AdminContext = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除账号（不能删除自己）"""
    user = await db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == ctx.username:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    await db.delete(user)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# 内容管理（admin + editor 均可）
# ══════════════════════════════════════════════════════════════════

class ClubBody(BaseModel):
    name: str
    short_name: str | None = None
    league_id: int | None = None
    country: str | None = None
    founded_year: int | None = None
    stadium: str | None = None
    stadium_capacity: int | None = None
    description: str | None = None
    access_tier: str = "basic"


@router.get("/clubs")
async def admin_list_clubs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Club).order_by(Club.id.desc()))
    clubs = result.scalars().all()
    return {"data": [
        {
            "id": c.id, "name": c.name, "short_name": c.short_name,
            "country": c.country, "founded_year": c.founded_year,
            "stadium": c.stadium, "status": c.status, "access_tier": c.access_tier,
        }
        for c in clubs
    ]}


@router.post("/clubs", status_code=201)
async def admin_create_club(body: ClubBody, db: AsyncSession = Depends(get_db)):
    club = Club(**body.model_dump())
    db.add(club)
    await db.flush()
    return {"data": {"id": club.id}}


@router.put("/clubs/{club_id}")
async def admin_update_club(club_id: int, body: ClubBody, db: AsyncSession = Depends(get_db)):
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(club, k, v)
    return {"data": {"id": club.id}}


@router.delete("/clubs/{club_id}")
async def admin_delete_club(club_id: int, db: AsyncSession = Depends(get_db)):
    club = await db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404)
    await db.delete(club)
    return {"ok": True}


class PlayerBody(BaseModel):
    name: str
    name_en: str | None = None
    current_club_id: int | None = None
    birth_date: date | None = None
    nationality: str | None = None
    position: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    preferred_foot: str | None = None
    bio: str | None = None
    jersey_number: int | None = None
    tags: list[str] = []
    rating: float | None = None
    access_tier: str = "basic"


@router.get("/players")
async def admin_list_players(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Player).order_by(Player.id.desc()))
    players = result.scalars().all()
    return {"data": [{"id": p.id, "name": p.name, "position": p.position, "status": p.status} for p in players]}


@router.post("/players", status_code=201)
async def admin_create_player(body: PlayerBody, db: AsyncSession = Depends(get_db)):
    player = Player(**body.model_dump())
    db.add(player)
    await db.flush()
    return {"data": {"id": player.id}}


@router.put("/players/{player_id}")
async def admin_update_player(player_id: int, body: PlayerBody, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(player, k, v)
    return {"data": {"id": player.id}}


@router.delete("/players/{player_id}")
async def admin_delete_player(player_id: int, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404)
    await db.delete(player)
    return {"ok": True}


class TransferBody(BaseModel):
    player_id: int
    from_club_id: int | None = None
    to_club_id: int | None = None
    type: TransferType
    transfer_date: date
    fee_display: str | None = None
    fee_stars: int = 0
    description: str | None = None


@router.get("/transfers")
async def admin_list_transfers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Transfer).order_by(Transfer.transfer_date.desc(), Transfer.id.desc())
    )
    transfers = result.scalars().all()
    return {"data": [
        {
            "id": t.id, "player_id": t.player_id,
            "from_club_id": t.from_club_id, "to_club_id": t.to_club_id,
            "type": t.type, "transfer_date": str(t.transfer_date),
            "fee_display": t.fee_display, "fee_stars": t.fee_stars,
        }
        for t in transfers
    ]}


@router.post("/transfers", status_code=201)
async def admin_create_transfer(body: TransferBody, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, body.player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    transfer = Transfer(**body.model_dump())
    db.add(transfer)
    player.current_club_id = body.to_club_id
    await db.flush()
    return {"data": {"id": transfer.id}}


class RetirementBody(BaseModel):
    player_id: int
    retired_at: date
    last_club_id: int | None = None
    career_summary: str | None = None
    achievements: list[str] = []


@router.post("/retirements", status_code=201)
async def admin_retire_player(body: RetirementBody, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, body.player_id)
    if not player:
        raise HTTPException(status_code=404)
    player.status = PlayerStatus.retired
    player.retired_at = body.retired_at
    player.current_club_id = None
    retirement = Retirement(**body.model_dump())
    db.add(retirement)
    await db.flush()
    return {"data": {"player_id": player.id}}
