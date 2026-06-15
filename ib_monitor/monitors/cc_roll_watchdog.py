"""
Covered Call 展期监控 + 50% 止盈扫描

规则一：Delta 展期触发（SOP 模块 2.1）
  - 默认：空头 Call 的 Delta 飙升至 ≥ 0.40 时，必须向后向上展期
  - NVDA：Delta ≥ 0.35 时触发（更激进防御）

规则二：50% 权利金止盈（SOP GOOG 规则，适用所有 CC）
  - 当前期权价格 ≤ 开仓权利金 × (1 - PROFIT_TAKE_PCT) 时
  - 即：已盈利超过初始权利金的 50%，立即 BTC 平仓并重置

注意：止盈规则需要预先在 data/cc_premiums.json 中记录开仓权利金。
"""

import logging
from dataclasses import dataclass

from ib_client import PositionSnapshot
from notifier import send_alert, AlertLevel
from data.premium_store import get_premium, make_key, remove_expired
import config

logger = logging.getLogger(__name__)


@dataclass
class CCRollResult:
    symbol: str
    expiry: str
    strike: float
    right: str
    position: float
    dte: int
    delta: float
    current_price: float
    trigger_reason: str          # "delta_roll" | "profit_take"
    roll_delta_threshold: float  # 触发展期的 delta 阈值
    initial_premium: float = 0.0
    profit_pct: float = 0.0

    def summary_line(self) -> str:
        if self.trigger_reason == "delta_roll":
            return (
                f"  📈 {self.symbol} ${self.strike:.0f}C "
                f"到期{self.expiry[4:6]}/{self.expiry[6:8]} "
                f"DTE={self.dte} "
                f"Delta={self.delta:+.2f}（触发线{self.roll_delta_threshold:.2f}）"
                f" → 必须展期！"
            )
        else:
            return (
                f"  💰 {self.symbol} ${self.strike:.0f}C "
                f"到期{self.expiry[4:6]}/{self.expiry[6:8]} "
                f"DTE={self.dte} "
                f"已盈利{self.profit_pct:.0%}（初始${self.initial_premium:.2f}→当前${self.current_price:.2f}）"
                f" → 建议BTC止盈！"
            )


_alerted_roll: set[str] = set()       # 已发过展期告警的合约
_alerted_profit: set[str] = set()     # 已发过止盈告警的合约


async def check_cc_roll(positions: list[PositionSnapshot]) -> list[CCRollResult]:
    """扫描所有空头 Call，检查展期触发和止盈条件"""
    global _alerted_roll, _alerted_profit

    need_roll: list[CCRollResult] = []
    need_profit_take: list[CCRollResult] = []
    active_keys: set[str] = set()

    for p in positions:
        if p.sec_type != "OPT":
            continue
        if p.position >= 0:
            continue          # 只关注空头
        if p.right != "C":
            continue          # 只关注 Call（Covered Call）

        contract_key = make_key(p.symbol, p.expiry, p.strike, p.right)
        active_keys.add(contract_key)

        # ── 规则一：Delta 展期触发 ─────────────────────────────────
        roll_threshold = config.CC_ROLL.symbol_delta.get(
            p.symbol, config.CC_ROLL.default_delta
        )
        abs_delta = abs(p.delta)

        if abs_delta >= roll_threshold:
            result = CCRollResult(
                symbol=p.symbol,
                expiry=p.expiry,
                strike=p.strike,
                right=p.right,
                position=p.position,
                dte=p.dte,
                delta=p.delta,
                current_price=p.market_price,
                trigger_reason="delta_roll",
                roll_delta_threshold=roll_threshold,
            )
            need_roll.append(result)

            if contract_key not in _alerted_roll:
                _alerted_roll.add(contract_key)
                await _send_roll_alert(result)

        # ── 规则二：50% 止盈扫描 ──────────────────────────────────
        initial_premium = get_premium(p.symbol, p.expiry, p.strike, p.right)
        if initial_premium and initial_premium > 0 and p.market_price > 0:
            profit_pct = (initial_premium - p.market_price) / initial_premium
            if profit_pct >= config.CC_ROLL.profit_take_pct:
                result = CCRollResult(
                    symbol=p.symbol,
                    expiry=p.expiry,
                    strike=p.strike,
                    right=p.right,
                    position=p.position,
                    dte=p.dte,
                    delta=p.delta,
                    current_price=p.market_price,
                    trigger_reason="profit_take",
                    roll_delta_threshold=roll_threshold,
                    initial_premium=initial_premium,
                    profit_pct=profit_pct,
                )
                need_profit_take.append(result)

                if contract_key not in _alerted_profit:
                    _alerted_profit.add(contract_key)
                    await _send_profit_take_alert(result)

    # 清理已不在持仓中的合约告警记录和权利金记录
    _alerted_roll &= active_keys
    _alerted_profit &= active_keys
    remove_expired(active_keys)

    return need_roll + need_profit_take


async def _send_roll_alert(r: CCRollResult) -> None:
    await send_alert(
        title=f"📈 {r.symbol} CC 触发展期！Delta={r.delta:+.2f}",
        body=(
            f"合约：<b>{r.symbol} ${r.strike:.0f} Call</b> "
            f"到期 {r.expiry[4:6]}/{r.expiry[6:8]}（DTE={r.dte}）\n"
            f"当前 Delta：<b>{r.delta:+.2f}</b>（触发阈值：{r.roll_delta_threshold:.2f}）\n"
            f"持仓：{abs(r.position):.0f} 张（空头）\n\n"
            f"<b>SOP 操作指令：</b>\n"
            f"• 立即向后（更晚到期）+ 向上（更高行权价）展期\n"
            f"• 目标：Delta 回落至 0.15-0.20 区间\n"
            f"• 使用限价单，挂中价（Mid-Price）等待撮合\n"
            f"• 确保展期后权利金净收入 > 0（不倒贴）"
        ),
        level=AlertLevel.RED,
    )


async def _send_profit_take_alert(r: CCRollResult) -> None:
    await send_alert(
        title=f"💰 {r.symbol} CC 已达 {r.profit_pct:.0%} 止盈线！",
        body=(
            f"合约：<b>{r.symbol} ${r.strike:.0f} Call</b> "
            f"到期 {r.expiry[4:6]}/{r.expiry[6:8]}（DTE={r.dte}）\n"
            f"开仓权利金：<b>${r.initial_premium:.2f}</b>\n"
            f"当前期权价格：<b>${r.current_price:.2f}</b>\n"
            f"已盈利：<b>{r.profit_pct:.0%}</b>（触发线：{config.CC_ROLL.profit_take_pct:.0%}）\n\n"
            f"<b>SOP 操作指令：</b>\n"
            f"• 立即 BTC（Buy-to-Close）平仓\n"
            f"• 锁定权利金收益，重置仓位\n"
            f"• 若DTE仍较长，重新开一张更高行权价的 CC"
        ),
        level=AlertLevel.INFO,
    )
