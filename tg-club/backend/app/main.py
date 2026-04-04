from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.api.routes import clubs, players, admin

_bot_app: Application | None = None


async def _seed_super_admin():
    """首次启动时若 admin_users 表为空，自动创建 .env 配置的超级管理员账号"""
    from sqlalchemy import select
    from passlib.context import CryptContext
    from app.models.admin_user import AdminUser, AdminRole

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(AdminUser))).scalars().first()
        if count is None:
            admin_user = AdminUser(
                username=settings.admin_username,
                password_hash=pwd_ctx.hash(settings.admin_password),
                role=AdminRole.admin,
                created_by="system",
            )
            db.add(admin_user)
            await db.commit()
            print(f"[seed] 超级管理员账号已创建: {settings.admin_username}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_app

    # 初始化数据库表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 首次启动自动创建超级管理员（从 .env 读取）
    await _seed_super_admin()

    # 初始化 Telegram Bot（可选，配置了 token 才启动）
    if settings.bot_enabled:
        from app.bot.handlers import (
            cmd_start, cmd_help, cmd_clubs, cmd_players, cmd_search,
            cmd_stats, handle_callback,
        )

        _bot_app = Application.builder().token(settings.club_bot_token).build()
        _bot_app.bot_data["db_factory"] = AsyncSessionLocal

        _bot_app.add_handler(CommandHandler("start",   cmd_start))
        _bot_app.add_handler(CommandHandler("help",    cmd_help))
        _bot_app.add_handler(CommandHandler("clubs",   cmd_clubs))
        _bot_app.add_handler(CommandHandler("players", cmd_players))
        _bot_app.add_handler(CommandHandler("search",  cmd_search))
        _bot_app.add_handler(CommandHandler("stats",   cmd_stats))
        _bot_app.add_handler(CallbackQueryHandler(handle_callback))

        await _bot_app.initialize()
        await _bot_app.bot.set_webhook(
            url=settings.club_bot_webhook_url,
            secret_token=settings.club_bot_webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        # 设置 Bot 命令菜单
        await _bot_app.bot.set_my_commands([
            BotCommand("start",   "打开主菜单"),
            BotCommand("clubs",   "浏览俱乐部"),
            BotCommand("players", "浏览球员"),
            BotCommand("search",  "搜索俱乐部/球员"),
            BotCommand("stats",   "系统统计（管理员）"),
            BotCommand("help",    "显示帮助"),
        ])
        await _bot_app.start()

    yield

    if _bot_app:
        await _bot_app.stop()
        await _bot_app.shutdown()


app = FastAPI(title="TG Club System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clubs.router,  prefix="/api/v1")
app.include_router(players.router, prefix="/api/v1")
app.include_router(admin.router,  prefix="/api/v1")


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    """接收 Telegram 推送的 Bot 事件"""
    if not _bot_app:
        return {"ok": False, "reason": "bot not initialized"}
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.club_bot_webhook_secret:
        return {"ok": False, "reason": "invalid secret"}
    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "bot": "enabled" if _bot_app else "disabled"}
