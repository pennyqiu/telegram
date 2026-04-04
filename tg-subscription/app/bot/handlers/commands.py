from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import user_service
from app.services.subscription_service import subscription_service
from app.core.config import settings


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with context.bot_data["db_factory"]() as db:
        user = await user_service.get_or_create(db, {
            "id": update.effective_user.id,
            "first_name": update.effective_user.first_name,
            "username": update.effective_user.username,
        })

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("订阅中心", web_app=WebAppInfo(url=settings.mini_app_url))
    ]])
    await update.message.reply_text(
        f"你好 {user.first_name}！\n\n点击下方按钮进入订阅中心，查看套餐或管理订阅。",
        reply_markup=keyboard,
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with context.bot_data["db_factory"]() as db:
        user = await user_service.get_by_telegram_id(db, update.effective_user.id)
        if not user:
            await update.message.reply_text("请先发送 /start 初始化账号。")
            return
        sub = await subscription_service.get_active(db, user.id)

    if not sub:
        await update.message.reply_text(
            "您当前没有有效订阅。\n\n",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("查看套餐", web_app=WebAppInfo(url=settings.mini_app_url))
            ]])
        )
        return

    await update.message.reply_text(
        f"当前套餐：{sub.plan.name}\n"
        f"有效期至：{sub.expires_at.strftime('%Y-%m-%d')}\n"
        f"自动续费：{'开启' if sub.status.value != 'cancelled' else '已关闭'}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("管理订阅", web_app=WebAppInfo(url=settings.mini_app_url))
        ]])
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start  - 打开订阅中心\n"
        "/status - 查看当前订阅状态\n"
        "/help   - 显示此帮助"
    )
