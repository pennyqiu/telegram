"""
单只个股集中度监控（Concentration Penalty）

规则：
  - 单只个股市值 / NLV > 27%：黄色预警
  - 单只个股市值 / NLV > 30%：红色告警，禁止加仓，必须减少敞口
"""

import logging
from dataclasses import dataclass, field

from ib_client import PositionSnapshot, AccountSnapshot
from notifier import send_alert, AlertLevel
import config

logger = logging.getLogger(__name__)


@dataclass
class ConcentrationResult:
    symbol: str
    market_value: float
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
            f"{emoji} {self.symbol}：${self.market_value:,.0f} "
            f"({self.ratio:.1%} NLV)"
        )


_last_levels: dict[str, str] = {}   # symbol -> "ok" / "warn" / "red"


async def check_concentration(
    positions: list[PositionSnapshot],
    snap: AccountSnapshot,
) -> list[ConcentrationResult]:
    """检查所有股票仓位的集中度，触发阈值时发送告警"""
    global _last_levels

    if snap.net_liquidation <= 0:
        return []

    # 只统计股票仓位（STK），按 symbol 合并多条记录
    stock_values: dict[str, float] = {}
    for p in positions:
        if p.sec_type == "STK":
            stock_values[p.symbol] = stock_values.get(p.symbol, 0) + abs(p.market_value)

    results = []
    for symbol, market_value in stock_values.items():
        ratio = market_value / snap.net_liquidation
        is_red = ratio > config.RISK.concentration_red
        is_warn = ratio > config.RISK.concentration_warn

        result = ConcentrationResult(
            symbol=symbol,
            market_value=market_value,
            ratio=ratio,
            is_red=is_red,
            is_warn=is_warn,
        )
        results.append(result)

        current_level = "red" if is_red else ("warn" if is_warn else "ok")
        prev_level = _last_levels.get(symbol, "ok")

        if current_level != prev_level:
            await _send_alert(result, current_level, snap.net_liquidation)
            _last_levels[symbol] = current_level

    # 按占比从大到小排序，便于报告展示
    results.sort(key=lambda r: r.ratio, reverse=True)
    return results


async def _send_alert(
    result: ConcentrationResult, level: str, nlv: float
) -> None:
    if level == "red":
        await send_alert(
            title=f"🔴 {result.symbol} 集中度触发红线！",
            body=(
                f"<b>{result.symbol}</b> 市值：<b>${result.market_value:,.0f}</b>\n"
                f"占 NLV 比例：<b>{result.ratio:.2%}</b>（红线：{config.RISK.concentration_red:.0%}）\n"
                f"账户净值 NLV：<b>${nlv:,.0f}</b>\n\n"
                f"<b>绝对禁令：</b>\n"
                f"• 禁止增加任何 {result.symbol} 现货或卖出其 Put\n"
                f"• 必须通过卖出 Covered Call 引入负 Delta 对冲\n"
                f"• 压制集中度惩罚机制"
            ),
            level=AlertLevel.RED,
        )
    elif level == "warn":
        await send_alert(
            title=f"⚠️ {result.symbol} 集中度预警",
            body=(
                f"<b>{result.symbol}</b> 市值：<b>${result.market_value:,.0f}</b>\n"
                f"占 NLV 比例：<b>{result.ratio:.2%}</b>（预警：{config.RISK.concentration_warn:.0%}，红线：{config.RISK.concentration_red:.0%}）\n"
                f"账户净值 NLV：<b>${nlv:,.0f}</b>\n\n"
                f"请注意：距 TIMS 30% 惩罚性保证金红线仅剩 "
                f"{(config.RISK.concentration_red - result.ratio):.2%}。"
            ),
            level=AlertLevel.WARN,
        )
    else:
        await send_alert(
            title=f"✅ {result.symbol} 集中度恢复正常",
            body=(
                f"<b>{result.symbol}</b> 占 NLV 比例已降至 <b>{result.ratio:.2%}</b>，"
                f"低于预警线 {config.RISK.concentration_warn:.0%}。"
            ),
            level=AlertLevel.INFO,
        )
