"""
标的凑整状态追踪 + SPYM 积攒进度 + VOO Swap 触发提醒

功能一：CC 资格面板
  - 监控 MSFT/NVDA/TSM/GOOG/META/QQQM 的当前股数
  - 标注是否已满足 100 股 CC 开仓条件
  - 缺口不足时提示还需多少股

功能二：SPYM 积攒进度
  - 实时追踪 SPYM 当前股数 vs 844 股目标
  - 计算完成百分比和预估还需被行权几次 Put

功能三：VOO Swap 触发提醒
  - SPYM 达到 844 股时，发送一次性 Telegram 提醒
  - 内含置换操作的完整 SOP 指令
"""

import logging
from dataclasses import dataclass, field

from ib_client import PositionSnapshot
from notifier import send_alert, AlertLevel
import config

logger = logging.getLogger(__name__)


@dataclass
class StockStatus:
    symbol: str
    current_shares: float
    target_shares: int         # 激活CC所需股数
    cc_contracts: int          # 可开的CC张数（current_shares // target_shares）
    gap: float                 # 缺口股数（负数=超出目标）
    cc_eligible: bool

    def summary_line(self) -> str:
        if self.cc_eligible:
            extra = self.current_shares - self.cc_contracts * self.target_shares
            return (
                f"  ✅ {self.symbol}：{self.current_shares:.0f}股 "
                f"→ 可开{self.cc_contracts}张CC"
                + (f"（余{extra:.0f}股裸多）" if extra > 0 else "")
            )
        else:
            return (
                f"  ⚠️ {self.symbol}：{self.current_shares:.0f}股 "
                f"→ 差{self.gap:.0f}股，CC未激活"
            )


@dataclass
class SpymProgress:
    current: float
    target: int
    pct: float
    gap: float
    voo_eligible: bool         # 是否已达到 VOO Swap 阈值

    def summary_line(self) -> str:
        bar_filled = int(self.pct * 20)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        if self.voo_eligible:
            return (
                f"  🎯 SPYM：{self.current:.0f}/{self.target}股 [{bar}] {self.pct:.1%}\n"
                f"  🔔 已达标！可执行 VOO Swap！"
            )
        else:
            return (
                f"  📊 SPYM：{self.current:.0f}/{self.target}股 [{bar}] {self.pct:.1%}\n"
                f"  还差 {self.gap:.0f} 股（约需被行权 {int(self.gap / 100) + 1} 次 Put）"
            )


@dataclass
class PositionTrackingResult:
    stock_statuses: list[StockStatus] = field(default_factory=list)
    spym: SpymProgress | None = None


_voo_swap_alerted = False   # VOO Swap 提醒只发一次


async def check_position_tracker(
    positions: list[PositionSnapshot],
) -> PositionTrackingResult:
    """检查标的凑整状态和SPYM积攒进度"""
    global _voo_swap_alerted

    # 统计各标的股数
    stock_shares: dict[str, float] = {}
    for p in positions:
        if p.sec_type == "STK":
            stock_shares[p.symbol] = stock_shares.get(p.symbol, 0) + p.position

    result = PositionTrackingResult()

    # ── CC 资格面板 ───────────────────────────────────────────────
    for symbol, target in config.POSITION_TARGETS.cc_targets.items():
        if symbol == "SPYM":
            continue   # SPYM 单独处理
        current = stock_shares.get(symbol, 0)
        cc_contracts = int(current // target)
        gap = max(0, target - (current % target)) if current < target else 0
        eligible = current >= target

        status = StockStatus(
            symbol=symbol,
            current_shares=current,
            target_shares=target,
            cc_contracts=cc_contracts,
            gap=gap,
            cc_eligible=eligible,
        )
        result.stock_statuses.append(status)

    # 按：已激活优先，缺口从小到大
    result.stock_statuses.sort(key=lambda s: (not s.cc_eligible, s.gap))

    # ── SPYM 积攒进度 ─────────────────────────────────────────────
    spym_current = stock_shares.get("SPYM", 0)
    spym_target = config.POSITION_TARGETS.spym_target
    spym_pct = min(spym_current / spym_target, 1.0) if spym_target > 0 else 0
    spym_gap = max(0, spym_target - spym_current)
    spym_eligible = spym_current >= spym_target

    result.spym = SpymProgress(
        current=spym_current,
        target=spym_target,
        pct=spym_pct,
        gap=spym_gap,
        voo_eligible=spym_eligible,
    )

    # ── VOO Swap 触发提醒 ─────────────────────────────────────────
    if spym_eligible and not _voo_swap_alerted:
        _voo_swap_alerted = True
        voo_shares = round(spym_current * config.POSITION_TARGETS.spym_to_voo_ratio)
        await send_alert(
            title="🎯 SPYM 已达 844 股！可执行 VOO Swap！",
            body=(
                f"SPYM 当前持仓：<b>{spym_current:.0f} 股</b>（目标 {spym_target} 股）\n\n"
                f"<b>VOO Swap SOP 完整指令：</b>\n"
                f"① 在交易时间内，市价/算法单 <b>卖出全部 {spym_current:.0f} 股 SPYM</b>\n"
                f"② 立即 <b>买入 {voo_shares} 股 VOO</b>（超低管理费0.03%底仓）\n"
                f"③ 买入 VOO 后，立即挂出 <b>1张 XSP (Mini-SPX) Call</b>\n"
                f"   参数：DTE 35天，Delta 0.15-0.20\n\n"
                f"<b>风控说明：</b>\n"
                f"• SPYM 与 VOO 均跟踪标普500，PM/TIMS 视为等额内部调仓\n"
                f"• 日内不会冻结额外保证金\n"
                f"• 完成后实现：超低管理费 + XSP顶级流动性 + Section 1256税务减免"
            ),
            level=AlertLevel.INFO,
        )

    return result
