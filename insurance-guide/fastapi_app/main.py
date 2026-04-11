import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = "hk-insurance-guide-2024-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── 用户数据库（实际项目可替换为数据库） ──────────────────────────────
USERS_DB = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("admin123"),
        "display_name": "管理员",
    },
    "demo": {
        "username": "demo",
        "hashed_password": pwd_context.hash("demo2024"),
        "display_name": "演示账号",
    },
}

# ── 受保护页面列表 ──────────────────────────────────────────────────
PROTECTED_PAGES = {
    "irr-calculator.html",
    "needs-assessment.html",
    "dividend-rates.html",
}


# ── Pydantic 模型 ────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


# ── Token 工具 ───────────────────────────────────────────────────────
def create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ── FastAPI 应用 ─────────────────────────────────────────────────────
app = FastAPI(title="HK Insurance Guide API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API：登录 ────────────────────────────────────────────────────────
@app.post("/api/login")
async def login(req: LoginRequest):
    user = USERS_DB.get(req.username)
    if not user or not pwd_context.verify(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(req.username)
    return {
        "token": token,
        "username": req.username,
        "display_name": user["display_name"],
        "expires_hours": ACCESS_TOKEN_EXPIRE_HOURS,
    }


# ── API：验证 Token ──────────────────────────────────────────────────
@app.get("/api/verify")
async def verify(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供 Token")
    username = decode_token(auth.removeprefix("Bearer ").strip())
    if not username or username not in USERS_DB:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    user = USERS_DB[username]
    return {"username": username, "display_name": user["display_name"]}


# ── API：受保护页面列表（供前端判断） ────────────────────────────────
@app.get("/api/protected-pages")
async def protected_pages():
    return {"pages": list(PROTECTED_PAGES)}


# ── 静态文件：挂载整个 insurance-guide 目录 ────────────────────────
# 注意：必须在 API 路由注册后再挂载，防止静态文件拦截 /api/* 请求
app.mount("/", StaticFiles(directory="insurance-guide", html=True), name="static")
