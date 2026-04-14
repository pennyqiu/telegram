from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal, get_db
from app.api.routes import influencer
from app.api.routes import podcast_audio
from app.api.routes import course

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

    # 播客索引自动恢复：若 Redis 索引为空但磁盘有 MP3，自动重建索引
    try:
        import logging, json
        from pathlib import Path
        import redis as redis_lib
        from app.core.config import settings
        from app.tasks.podcast_translator import REDIS_PODCAST_KEY, AUDIO_DIR

        _log = logging.getLogger(__name__)
        _r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        _raw = _r.get(REDIS_PODCAST_KEY)
        _episodes = json.loads(_raw) if _raw else []

        if not _episodes and AUDIO_DIR.exists():
            _mp3s = sorted(AUDIO_DIR.glob("*.mp3"))
            if _mp3s:
                _log.warning("启动时检测到 Redis 播客索引为空，磁盘有 %d 个 MP3，自动重建索引…", len(_mp3s))
                import re, html as _html, httpx as _httpx

                def _fetch_rss_titles():
                    mapping = {}
                    try:
                        resp = _httpx.get("https://rationalreminder.libsyn.com/rss", timeout=20, follow_redirects=True)
                        for item in re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL):
                            title_m = re.search(r"<title><!\[CDATA\[(.*?)]]></title>", item) or re.search(r"<title>(.*?)</title>", item)
                            link_m = re.search(r"<link>(.*?)</link>", item)
                            pub_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
                            enc_m = re.search(r'<enclosure[^>]+url="([^"]+)"', item)
                            if title_m and pub_m:
                                pub = pub_m.group(1).strip()
                                parts = pub.split()
                                if len(parts) >= 4:
                                    key = f"{parts[0].rstrip(',')}  {parts[1]} {parts[2]} {parts[3]}"
                                    mapping[key] = (
                                        _html.unescape(title_m.group(1).strip()),
                                        link_m.group(1).strip() if link_m else "https://rationalreminder.ca/podcast",
                                        enc_m.group(1) if enc_m else "",
                                    )
                    except Exception as exc:
                        _log.warning("RSS fetch failed during startup rebuild: %s", exc)
                    return mapping

                def _fetch_ep_title(num):
                    url = f"https://rationalreminder.ca/podcast/{num}"
                    try:
                        resp = _httpx.get(url, timeout=15, follow_redirects=True)
                        m = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE)
                        if m:
                            t = re.sub(r"\s*[—\-|]\s*Rational Reminder.*$", "", _html.unescape(m.group(1))).strip()
                            if t:
                                return t, url
                    except Exception:
                        pass
                    return f"Episode {num}", url

                _rss = _fetch_rss_titles()
                _rebuilt = []
                for _mp3 in _mp3s:
                    _n = _mp3.stem
                    _ep_m = re.search(r'ep(\d+)$', _n)
                    if _ep_m:
                        _num = int(_ep_m.group(1))
                        _title, _url = _fetch_ep_title(_num)
                        _date = f"ep{_num}"
                        _orig = ""
                    else:
                        _dp = re.sub(r'^rational_reminder_', '', _n).replace('_', ' ').strip()
                        _entry = _rss.get(_dp)
                        if _entry:
                            _title, _url, _orig = _entry
                        else:
                            _title = f"Rational Reminder — {_dp}"
                            _url = "https://rationalreminder.ca/podcast"
                            _orig = ""
                        _date = _dp
                    _rebuilt.append({
                        "id": _n, "source": "rational_reminder",
                        "source_name": "Rational Reminder",
                        "title": _title, "date": _date,
                        "original_url": _url, "original_mp3": _orig,
                        "mp3_file": _mp3.name, "summary_preview": "",
                        "created_at": "2026-04-12",
                    })

                _r.set(REDIS_PODCAST_KEY, json.dumps(_rebuilt, ensure_ascii=False))
                _log.info("启动自动重建完成：%d 集写入 Redis", len(_rebuilt))
    except Exception as _startup_err:
        import logging
        logging.getLogger(__name__).warning("播客索引自动重建失败（不影响启动）: %s", _startup_err)

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
app.include_router(course.router,        prefix="/api/v1")


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
