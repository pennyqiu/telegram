"""
14-Day Gamma 死亡警戒线扫描

规则：
  - 空头期权（position < 0）的 DTE ≤ 14 天
  - 且 |delta| 在 [0.30, 0.70] 范围（接近 ATM）
  - 满足以上条件即触发 Gamma 死亡警戒告警
  - 建议无条件平仓或向后展期（Roll）
"""

import logging
from dataclasses import dataclass

from ib_client import PositionSnapshot
from notifier import send_alert, AlertLevel
import config

logger = logging.getLogger(__name__)


@dataclass
class GammaWatchdogResult:
    symbol: str
    expiry: str
    strike: float
    right: str
    position: float
    dte: int
    delta: float
    gamma: float
    market_value: float

    def summary_line(self) -> str:
        direction = "Put" if self.right == "P" else "Call"
        return (
            f"  🔥 {self.symbol} ${self.strike:.0f}{direction} "
            f"到期{self.expiry[4:6]}/{self.expiry[6:8]} "
            f"DTE={self.dte} "
            f"Delta={self.delta:+.2f} "
            f"Gamma={self.gamma:.4f} "
            f"仓位={self.position:.0f}"
        )


_alerted_contracts: set[str] = set()   # 已告警的合约，避免每分钟重复发


async def check_gamma_watchdog(
    positions: list[PositionSnapshot],
) -> list[GammaWatchdogResult]:
    """扫描所有空头期权，检测 Gamma 死亡警戒仓位"""
    global _alerted_contracts

    dangerous: list[GammaWatchdogResult] = []
    newly_dangerous: list[GammaWatchdogResult] = []

    for p in positions:
        if p.sec_type != "OPT":
            continue
        if p.position >= 0:
            continue   # 只关注空头期权

        abs_delta = abs(p.delta)
        is_atm = config.RISK.gamma_delta_min <= abs_delta <= config.RISK.gamma_delta_max
        is_near_expiry = p.dte <= config.RISK.gamma_dte_threshold

        if not (is_atm and is_near_expiry):
            continue

        result = GammaWatchdogResult(
            symbol=p.symbol,
            expiry=p.expiry,
            strike=p.strike,
            right=p.right,
            position=p.position,
            dte=p.dte,
            delta=p.delta,
            gamma=p.gamma,
            market_value=p.market_value,
        )
        dangerous.append(result)

        contract_key = f"{p.symbol}_{p.expiry}_{p.strike}_{p.right}"
        if contract_key not in _alerted_contracts:
            newly_dangerous.append(result)
            _alerted_contracts.add(contract_key)

    # 清理已到期合约的告警记录，防止 set 无限增长
    active_keys = {
        f"{p.symbol}_{p.expiry}_{p.strike}_{p.right}"
        for p in positions if p.sec_type == "OPT"
    }
    _alerted_contracts &= active_keys

    if newly_dangerous:
        await _send_alert(newly_dangerous)

    return dangerous


async def _send_alert(items: list[GammaWatchdogResult]) -> None:
    lines = [r.summary_line() for r in items]
    body = "\n".join(lines)
    body += (
        "\n\n<b>必须采取的行动：</b>\n"
        "• 无条件平仓（BTC）或向后展期（Roll）\n"
        "• 优先平仓近月空头期权，<b>不要等待到期</b>\n"
        "• 量化交易员绝不将命运交由末日 Gamma 随机游走支配"
    )

    count = len(items)
    await send_alert(
        title=f"☠️ Gamma 死亡警戒！{count} 个空头期权即将到期",
        body=body,
        level=AlertLevel.RED,
    )
