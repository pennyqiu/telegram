from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal, get_db
from app.api.routes import influencer
from app.api.routes import podcast_audio

_bot_app = None


def get_bot():
    return _bot_app.bot if _bot_app else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_app

    # 数据库初始化（仅当 database_url 配置时）
    if engine:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("DB init skipped: %s", e)

    # Telegram Bot 初始化（仅当 token 配置时）
    if settings.telegram_bot_token:
        try:
            from telegram import Update, MenuButtonWebApp, WebAppInfo
            from telegram.ext import (
                Application, CommandHandler, PreCheckoutQueryHandler,
                MessageHandler, ChatJoinRequestHandler, filters,
            )
            from app.bot.handlers.commands import start_command, status_command, help_command
            from app.bot.handlers.payments import pre_checkout_handler, successful_payment_handler
            from app.bot.handlers.join_requests import handle_join_request

            _bot_app = (
                Application.builder()
                .token(settings.telegram_bot_token)
                .build()
            )
            _bot_app.bot_data["db_factory"] = AsyncSessionLocal
            _bot_app.add_handler(CommandHandler("start", start_command))
            _bot_app.add_handler(CommandHandler("status", status_command))
            _bot_app.add_handler(CommandHandler("help", help_command))
            _bot_app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
            _bot_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
            _bot_app.add_handler(ChatJoinRequestHandler(handle_join_request))
            await _bot_app.initialize()
            if settings.telegram_webhook_url:
                await _bot_app.bot.set_webhook(
                    url=settings.telegram_webhook_url,
                    secret_token=settings.telegram_webhook_secret,
                    allowed_updates=["message", "callback_query", "pre_checkout_query", "chat_join_request"],
                )
            if settings.mini_app_url:
                from telegram import MenuButtonWebApp, WebAppInfo
                await _bot_app.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="订阅中心", web_app=WebAppInfo(url=settings.mini_app_url))
                )
            await _bot_app.start()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Telegram bot init skipped: %s", e)
            _bot_app = None

    # 加载其余路由（支付等，仅当配置存在时）
    if settings.telegram_bot_token:
        try:
            from app.api.routes import plans, subscriptions, payments, third_party_pay
            app.include_router(plans.router,            prefix="/api/v1")
            app.include_router(subscriptions.router,    prefix="/api/v1")
            app.include_router(payments.router,         prefix="/api/v1")
            app.include_router(third_party_pay.router,  prefix="/api/v1")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Payment routes skipped: %s", e)

    yield

    if _bot_app:
        await _bot_app.stop()
        await _bot_app.shutdown()


app = FastAPI(title="TG Subscription Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 核心路由：始终加载
app.include_router(influencer.router,    prefix="/api/v1")
app.include_router(podcast_audio.router, prefix="/api/v1")


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    if not _bot_app:
        return {"ok": False, "error": "bot not configured"}
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.telegram_webhook_secret:
        return {"ok": False}
    from telegram import Update
    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return {"ok": True}


@app.post("/webhooks/wechat")
async def wechat_notify_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    from app.api.routes.third_party_pay import wechat_notify
    return await wechat_notify(request, db)


@app.post("/webhooks/alipay")
async def alipay_notify_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    from app.api.routes.third_party_pay import alipay_notify
    return await alipay_notify(request, db)


@app.post("/webhooks/xunhupay")
async def xunhupay_notify_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    """虎皮椒聚合支付回调（微信+支付宝统一入口）"""
    from app.api.routes.third_party_pay import xunhupay_notify
    return await xunhupay_notify(request, db)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "bot": "enabled" if _bot_app else "disabled",
        "db": "enabled" if engine else "disabled",
    }
