from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes
from app.services.subscription_service import subscription_service
from app.services.user_service import user_service
from app.core.redis import redis_client
from app.core.config import settings


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    telegram_id = request.from_user.id
    channel_id = request.chat.id

    cache_key = f"sub:active:tg:{telegram_id}"
    cached = await redis_client.get(cache_key)

    if cached is None:
        async with context.bot_data["db_factory"]() as db:
            user = await user_service.get_by_telegram_id(db, telegram_id)
            has_sub = bool(user and await subscription_service.has_active(db, user.id))
        await redis_client.set(cache_key, "1" if has_sub else "0", ex=300)
    else:
        has_sub = cached == "1"

    if has_sub:
        await context.bot.approve_chat_join_request(channel_id, telegram_id)
    else:
        await context.bot.decline_chat_join_request(channel_id, telegram_id)
        await context.bot.send_message(
            telegram_id,
            "访问该频道需要有效订阅。",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("查看订阅套餐", web_app=WebAppInfo(url=settings.mini_app_url))
            ]])
        )
