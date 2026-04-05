import hmac
import hashlib
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl
from datetime import datetime, timedelta, UTC

from fastapi import Header, HTTPException, Depends
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.subscription_client import get_user_tier


# ── Mini App 用户认证 ──────────────────────────────────────────────

async def get_tg_user(x_init_data: str = Header(default="")) -> dict:
    """验证 Mini App initData，返回 Telegram 用户信息。
    initData 为空时返回游客用户（id=0），享有 free tier 权限。
    """
    if not x_init_data:
        return {"id": 0, "first_name": "Guest"}
    params = dict(parse_qsl(x_init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    bot_token = settings.club_bot_token
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData")
    return json.loads(params.get("user", "{}") or "{}")


async def get_tier(tg_user: dict = Depends(get_tg_user)) -> str:
    return await get_user_tier(int(tg_user["id"]))


# ── 管理后台 JWT 认证（含角色） ────────────────────────────────────

@dataclass
class AdminContext:
    username: str
    role: str       # "admin" | "editor"

    @property
    def is_super_admin(self) -> bool:
        return self.role == "admin"


def create_admin_token(username: str, role: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "exp":  datetime.now(UTC) + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")


def verify_admin_token(authorization: str = Header(...)) -> AdminContext:
    """验证 JWT，返回包含 username + role 的 AdminContext"""
    try:
        token = authorization.removeprefix("Bearer ")
        payload = jwt.decode(token, settings.admin_jwt_secret, algorithms=["HS256"])
        return AdminContext(username=payload["sub"], role=payload.get("role", "editor"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_super_admin(ctx: AdminContext = Depends(verify_admin_token)) -> AdminContext:
    """只有 admin 角色才能访问，editor 会收到 403"""
    if not ctx.is_super_admin:
        raise HTTPException(status_code=403, detail="仅超级管理员可执行此操作")
    return ctx
