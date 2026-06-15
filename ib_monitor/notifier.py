"""
Telegram 通知推送模块

消息分为三类：
  - 🟢 正常日报（每日健康检查）
  - 🟡 预警（接近红线）
  - 🔴 告警（触发红线，需立即处理）
"""

import logging
from enum import Enum

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARN = "warn"
    RED = "red"


_LEVEL_EMOJI = {
    AlertLevel.INFO: "✅",
    AlertLevel.WARN: "⚠️",
    AlertLevel.RED: "🚨",
}

_bot: Bot | None = None


def _get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=config.TELEGRAM.bot_token)
    return _bot


async def send_alert(
    title: str,
    body: str,
    level: AlertLevel = AlertLevel.INFO,
) -> None:
    """发送一条告警消息"""
    emoji = _LEVEL_EMOJI[level]
    text = f"{emoji} <b>{title}</b>\n\n{body}"
    await _send(text)


async def send_daily_report(
    nlv: float,
    excess_liquidity: float,
    excess_liquidity_pct: float,
    unrealized_pnl: float,
    concentration_lines: list[str],
    gamma_lines: list[str],
    cc_lines: list[str] | None = None,
    stock_lines: list[str] | None = None,
    spym_lines: list[str] | None = None,
) -> None:
    """发送每日账户健康报告"""
    from datetime import datetime
    import pytz

    beijing = pytz.timezone("Asia/Shanghai")
    now = datetime.now(beijing).strftime("%Y-%m-%d %H:%M")

    el_emoji = "✅" if excess_liquidity_pct >= 0.50 else ("⚠️" if excess_liquidity_pct >= 0.40 else "🚨")
    pnl_emoji = "📈" if unrealized_pnl >= 0 else "📉"

    conc_block  = "\n".join(concentration_lines) if concentration_lines else "  无需关注"
    gamma_block = "\n".join(gamma_lines) if gamma_lines else "  无到期≤14天的ATM空头期权 ✅"
    cc_block    = "\n".join(cc_lines) if cc_lines else "  所有CC Delta正常 ✅"
    stock_block = "\n".join(stock_lines) if stock_lines else "  暂无数据"
    spym_block  = "\n".join(spym_lines) if spym_lines else "  暂无SPYM持仓"

    text = (
        f"📊 <b>东线战场健康检查</b>  <code>{now}</code>\n"
        f"{'─' * 32}\n"
        f"💰 账户净值 (NLV)：<b>${nlv:,.0f}</b>\n"
        f"{el_emoji} 剩余流动性：<b>${excess_liquidity:,.0f}</b> "
        f"(<b>{excess_liquidity_pct:.1%}</b>)\n"
        f"{pnl_emoji} 未实现盈亏：<b>${unrealized_pnl:+,.0f}</b>\n"
        f"{'─' * 32}\n"
        f"<b>📌 集中度监控</b>\n{conc_block}\n"
        f"{'─' * 32}\n"
        f"<b>⏰ Gamma 警戒期权</b>\n{gamma_block}\n"
        f"{'─' * 32}\n"
        f"<b>📈 CC 展期 / 止盈状态</b>\n{cc_block}\n"
        f"{'─' * 32}\n"
        f"<b>🧩 标的凑整状态</b>\n{stock_block}\n"
        f"{'─' * 32}\n"
        f"<b>🏦 SPYM 积攒进度</b>\n{spym_block}\n"
        f"{'─' * 32}\n"
        f"<i>⚠️ 本消息为只读监控，不执行任何交易操作。</i>"
    )
    await _send(text)


async def send_connection_status(connected: bool, detail: str = "") -> None:
    """发送 IB Gateway 连接状态变化通知"""
    if connected:
        text = f"🟢 <b>IB Gateway 已连接</b>\n{detail}"
    else:
        text = f"🔴 <b>IB Gateway 连接断开</b>\n{detail}\n\n<i>监控程序将自动尝试重连...</i>"
    await _send(text)


async def _send(text: str) -> None:
    try:
        bot = _get_bot()
        await bot.send_message(
            chat_id=config.TELEGRAM.alert_chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        logger.info("Telegram 消息已发送")
    except TelegramError as e:
        logger.error("Telegram 发送失败: %s", e)
