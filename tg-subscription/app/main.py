from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update, MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, PreCheckoutQueryHandler,
    MessageHandler, ChatJoinRequestHandler, filters,
)
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal, get_db
from app.bot.handlers.commands import start_command, status_command, help_command
from app.bot.handlers.payments import pre_checkout_handler, successful_payment_handler
from app.bot.handlers.join_requests import handle_join_request
from app.api.routes import plans, subscriptions, payments
from app.api.routes import third_party_pay

_bot_app: Application | None = None


def get_bot():
    return _bot_app.bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    await _bot_app.bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.telegram_webhook_secret,
        allowed_updates=["message", "callback_query", "pre_checkout_query", "chat_join_request"],
    )
    await _bot_app.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="订阅中心", web_app=WebAppInfo(url=settings.mini_app_url))
    )
    await _bot_app.start()
    yield
    await _bot_app.stop()
    await _bot_app.shutdown()


app = FastAPI(title="TG Subscription Service", lifespan=lifespan)
app.include_router(plans.router,            prefix="/api/v1")
app.include_router(subscriptions.router,    prefix="/api/v1")
app.include_router(payments.router,         prefix="/api/v1")
app.include_router(third_party_pay.router,  prefix="/api/v1")


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.telegram_webhook_secret:
        return {"ok": False}
    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return {"ok": True}


@app.post("/webhooks/wechat")
async def wechat_webhook(request: Request):
    """微信支付异步通知"""
    async for db in get_db():
        return await third_party_pay.wechat_notify(request, db)


@app.post("/webhooks/alipay")
async def alipay_webhook(request: Request):
    """支付宝异步通知"""
    async for db in get_db():
        return await third_party_pay.alipay_notify(request, db)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "wechat_pay": "enabled" if settings.wechat_enabled else "disabled",
        "alipay": "enabled" if settings.alipay_enabled else "disabled",
    }
