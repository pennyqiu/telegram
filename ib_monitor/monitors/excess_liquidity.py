"""
剩余流动性（Excess Liquidity）监控

规则：
  - 剩余流动性 / NLV < 50%：黄色预警
  - 剩余流动性 / NLV < 40%：红色告警，当天禁止任何新开仓
"""

import logging
from dataclasses import dataclass

from ib_client import AccountSnapshot
from notifier import send_alert, AlertLevel
import config

logger = logging.getLogger(__name__)


@dataclass
class ExcessLiquidityResult:
    nlv: float
    excess_liquidity: float
    ratio: float
    is_red: bool
    is_warn: bool

    def summary_line(self) -> str:
        if self.is_red:
            emoji = "🚨"
        elif self.is_warn:
            emoji = "⚠️"
        else:
            emoji = "✅"
        return (
            f"{emoji} 剩余流动性：${self.excess_liquidity:,.0f} "
            f"({self.ratio:.1%} NLV)"
        )


_last_level: str = "ok"   # 避免重复发送相同级别告警


async def check_excess_liquidity(snap: AccountSnapshot) -> ExcessLiquidityResult:
    """检查剩余流动性，触发阈值时发送 Telegram 告警"""
    global _last_level

    if snap.net_liquidation <= 0:
        logger.warning("NLV 为 0，跳过剩余流动性检查")
        return ExcessLiquidityResult(0, 0, 0, False, False)

    ratio = snap.excess_liquidity / snap.net_liquidation
    is_red = ratio < config.RISK.excess_liquidity_red
    is_warn = ratio < config.RISK.excess_liquidity_warn

    result = ExcessLiquidityResult(
        nlv=snap.net_liquidation,
        excess_liquidity=snap.excess_liquidity,
        ratio=ratio,
        is_red=is_red,
        is_warn=is_warn,
    )

    current_level = "red" if is_red else ("warn" if is_warn else "ok")

    if current_level != _last_level:
        await _send_alert(result, current_level)
        _last_level = current_level

    return result


async def _send_alert(result: ExcessLiquidityResult, level: str) -> None:
    if level == "red":
        await send_alert(
            title="🔴 剩余流动性跌破红线！",
            body=(
                f"当前剩余流动性：<b>${result.excess_liquidity:,.0f}</b>（占NLV <b>{result.ratio:.1%}</b>）\n"
                f"账户净值 NLV：<b>${result.nlv:,.0f}</b>\n"
                f"红线阈值：<b>{config.RISK.excess_liquidity_red:.0%}</b>\n\n"
                f"<b>钢铁法则：立即停止所有新开仓！</b>\n"
                f"所有操作以释放保证金为唯一目的。"
            ),
            level=AlertLevel.RED,
        )
    elif level == "warn":
        await send_alert(
            title="⚠️ 剩余流动性预警",
            body=(
                f"当前剩余流动性：<b>${result.excess_liquidity:,.0f}</b>（占NLV <b>{result.ratio:.1%}</b>）\n"
                f"账户净值 NLV：<b>${result.nlv:,.0f}</b>\n"
                f"预警阈值：{config.RISK.excess_liquidity_warn:.0%}，红线：{config.RISK.excess_liquidity_red:.0%}\n\n"
                f"请注意控制仓位，避免继续消耗流动性。"
            ),
            level=AlertLevel.WARN,
        )
    else:
        await send_alert(
            title="✅ 剩余流动性恢复正常",
            body=(
                f"当前剩余流动性：<b>${result.excess_liquidity:,.0f}</b>（占NLV <b>{result.ratio:.1%}</b>）\n"
                f"已回升至安全区间（>{config.RISK.excess_liquidity_warn:.0%}）。"
            ),
            level=AlertLevel.INFO,
        )
