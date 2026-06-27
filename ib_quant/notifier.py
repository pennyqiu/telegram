"""
多通道通知：Telegram + 邮箱

本模块在导入时把通知处理器注册进 hooks 总线（register）。
业务代码只需 emit(Event.XXX, payload)，消息就会自动推送到所有已启用的通道。

通道：
  - Telegram：复用 ib_monitor 的同一个 Bot（或独立 Bot），HTML 格式。
  - 邮箱：通过 SMTP 异步发送（aiosmtplib），适合作为 Telegram 之外的冗余触达。

要新增触达通道（如企业微信、Server酱、短信），
只需写一个 async handler 并 register(None, handler)，无需改动任何业务代码。
"""

import logging

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from hooks import Event, register

logger = logging.getLogger(__name__)


# ── 文案渲染：把事件 payload 渲染成人类可读消息 ───────────────────────

_EVENT_TITLE = {
    Event.CONNECTED: "🟢 已连接 IB",
    Event.DISCONNECTED: "🔴 IB 连接断开",
    Event.SIGNAL: "📡 策略信号",
    Event.ORDER_SUBMITTED: "📨 订单已提交",
    Event.ORDER_STATUS: "🔄 订单状态",
    Event.ORDER_FILLED: "✅ 订单成交",
    Event.ORDER_REJECTED: "⛔ 订单被拒绝",
    Event.DAILY_REPORT: "📊 每日报告",
    Event.ERROR: "🚨 异常告警",
}


def _render(event: Event, payload: dict) -> tuple[str, str]:
    """返回 (title, body) 纯文本（body 可含简单 HTML 标签）。"""
    title = _EVENT_TITLE.get(event, event.value)

    if event in (Event.ORDER_SUBMITTED, Event.ORDER_REJECTED):
        tag = "🧪 模拟(DRY_RUN)" if payload.get("dry_run") else "💵 真实"
        otype = payload.get("order_type", "")
        price = payload.get("limit_price") or 0
        price_str = f" @ ${price}" if otype == "LMT" and price else " @ 市价"
        body = (
            f"{tag}\n"
            f"标的：<b>{payload.get('symbol')}</b>\n"
            f"方向：<b>{payload.get('action')}</b>  数量：<b>{payload.get('quantity')}</b>"
            f"{price_str}\n"
            f"状态：{payload.get('status')}"
        )
        if payload.get("reason"):
            body += f"\n原因：<code>{payload['reason']}</code>"
        return title, body

    if event == Event.ORDER_FILLED:
        body = (
            f"标的：<b>{payload.get('symbol')}</b>\n"
            f"方向：{payload.get('action')}  成交：<b>{payload.get('shares')}</b> @ "
            f"<b>${payload.get('price')}</b>\n"
            f"时间：{payload.get('time')}"
        )
        return title, body

    if event == Event.SIGNAL:
        body = (
            f"策略：<b>{payload.get('strategy')}</b>\n"
            f"标的：<b>{payload.get('symbol')}</b>  信号：<b>{payload.get('signal')}</b>\n"
            f"说明：{payload.get('reason', '')}"
        )
        return title, body

    if event == Event.CONNECTED:
        body = (
            f"模式：<b>{payload.get('mode')}</b>\n"
            f"账户：<code>{payload.get('account')}</code>\n"
            f"DRY_RUN：{payload.get('dry_run')}"
        )
        return title, body

    if event == Event.DAILY_REPORT:
        return title, payload.get("text", "")

    if event == Event.ERROR:
        return title, payload.get("message", str(payload))

    # 兜底：直接序列化
    lines = [f"{k}：{v}" for k, v in payload.items()]
    return title, "\n".join(lines)


# ── Telegram 通道 ─────────────────────────────────────────────────────

_bot: Bot | None = None


def _get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=config.TELEGRAM.bot_token)
    return _bot


async def _telegram_handler(event: Event, payload: dict) -> None:
    if not config.TELEGRAM.enabled or not config.TELEGRAM.bot_token:
        return
    title, body = _render(event, payload)
    text = f"<b>{title}</b>\n\n{body}"
    try:
        await _get_bot().send_message(
            chat_id=config.TELEGRAM.chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except TelegramError as e:
        logger.error("Telegram 发送失败: %s", e)


# ── 邮箱通道 ──────────────────────────────────────────────────────────

# 默认只对重要事件发邮件，避免邮箱被状态流水淹没
_EMAIL_EVENTS = {
    Event.ORDER_SUBMITTED, Event.ORDER_FILLED,
    Event.ORDER_REJECTED, Event.ERROR, Event.DAILY_REPORT,
}


async def _email_handler(event: Event, payload: dict) -> None:
    if not config.EMAIL.enabled or event not in _EMAIL_EVENTS:
        return
    if not config.EMAIL.recipients:
        return

    import aiosmtplib
    from email.message import EmailMessage

    title, body = _render(event, payload)
    # 邮件正文用纯文本，去掉 HTML 标签
    plain = body.replace("<b>", "").replace("</b>", "")
    plain = plain.replace("<code>", "").replace("</code>", "")

    msg = EmailMessage()
    msg["From"] = config.EMAIL.sender
    msg["To"] = ", ".join(config.EMAIL.recipients)
    msg["Subject"] = f"[ib_quant] {title}"
    msg.set_content(plain)

    try:
        await aiosmtplib.send(
            msg,
            hostname=config.EMAIL.smtp_host,
            port=config.EMAIL.smtp_port,
            username=config.EMAIL.username,
            password=config.EMAIL.password,
            start_tls=config.EMAIL.use_tls,
        )
        logger.info("邮件已发送: %s", title)
    except Exception as e:
        logger.error("邮件发送失败: %s", e)


# ── 注册到 hooks 总线（导入即生效，订阅所有事件） ─────────────────────

def setup() -> None:
    """在 main.py 启动时调用，把通知处理器接入事件总线。"""
    register(None, _telegram_handler)
    register(None, _email_handler)
    logger.info(
        "通知通道已注册：Telegram=%s, Email=%s",
        config.TELEGRAM.enabled, config.EMAIL.enabled,
    )
