"""
课程访问凭证 API

端点：
  POST /api/v1/course/auth        验证课程用户名+密码，返回 JWT token
  POST /api/v1/course/provision   内部接口：付款后为用户生成/重置课程账号
"""

from __future__ import annotations

import hashlib
import os
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_internal_api_key
from app.core.database import get_db
from app.models.course_credential import CourseCredential

router = APIRouter(prefix="/course", tags=["course"])

# ── 工具 ──────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """SHA-256 哈希，与前端保持一致"""
    return hashlib.sha256(password.encode()).hexdigest()


def _gen_password(length: int = 10) -> str:
    """生成随机密码：字母+数字，易读（去掉易混淆字符 0/O/I/l）"""
    alphabet = string.ascii_letters.replace("O", "").replace("I", "").replace("l", "") + "23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _make_session_token(user_login: str) -> str:
    """生成不可猜测的 session token"""
    return secrets.token_urlsafe(32)


# ── 验证账号（前端调用）────────────────────────────────────────────

class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    ok: bool
    token: str | None = None
    display_name: str | None = None
    error: str | None = None


@router.post("/auth", response_model=AuthResponse)
async def course_auth(
    body: AuthRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CourseCredential).where(CourseCredential.login == body.username.strip().lower())
    )
    cred = result.scalar_one_or_none()

    if not cred or cred.password_hash != _hash_password(body.password):
        # 故意不区分"用户不存在"和"密码错误"，防止枚举
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not cred.is_active:
        raise HTTPException(status_code=403, detail="账号已停用，请联系客服")

    # 更新最后登录时间
    cred.last_login_at = datetime.now(timezone.utc)

    # 颁发 session token（存回数据库，供注销/重置使用）
    token = _make_session_token(cred.login)
    cred.session_token = token

    return AuthResponse(ok=True, token=token, display_name=cred.display_name)


# ── 生成/重置账号（仅内部调用，付款后由 Bot handler 触发）──────────

class ProvisionRequest(BaseModel):
    telegram_id: int
    display_name: str


class ProvisionResponse(BaseModel):
    login: str
    password: str      # 明文，只在生成时返回一次，之后不再可见


@router.post("/provision", response_model=ProvisionResponse)
async def provision_credential(
    body: ProvisionRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    """付款成功后为用户创建课程账号（幂等：已存在则重置密码）"""
    login = f"tg_{body.telegram_id}"

    result = await db.execute(
        select(CourseCredential).where(CourseCredential.login == login)
    )
    cred = result.scalar_one_or_none()

    password = _gen_password()
    pw_hash = _hash_password(password)

    if cred:
        # 已有账号：重置密码（用户重新购买 / 找回密码场景）
        cred.password_hash = pw_hash
        cred.is_active = True
        cred.display_name = body.display_name
    else:
        cred = CourseCredential(
            login=login,
            password_hash=pw_hash,
            display_name=body.display_name,
            telegram_id=body.telegram_id,
        )
        db.add(cred)

    # 注意：密码明文只在这里返回一次，数据库只存哈希
    return ProvisionResponse(login=login, password=password)
