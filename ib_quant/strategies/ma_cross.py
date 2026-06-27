"""
示例策略：双均线交叉（MA Cross）

逻辑（教学示例，非投资建议）：
  - 维护每个标的最近 N 个轮询周期的中间价，计算短期/长期均线。
  - 短均线上穿长均线（金叉）→ 买入信号；下穿（死叉）→ 卖出信号。
  - 每次只下固定数量 ORDER_QTY，真实下单与否由 DRY_RUN / 护栏决定。

注意：示例用「轮询价格」近似 K 线，仅用于跑通链路。
真实策略应使用 reqHistoricalData 拉取标准 K 线，并加入更严谨的风控。
"""

import logging
from collections import defaultdict, deque

from .base import Strategy, StrategyContext, register_strategy

logger = logging.getLogger(__name__)


@register_strategy("ma_cross")
class MACrossStrategy(Strategy):
    SHORT = 5
    LONG = 20
    ORDER_QTY = 1

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        # symbol -> 价格序列
        self._prices: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.LONG))
        # symbol -> 上一周期短均线是否在长均线之上（用于检测穿越）
        self._above: dict[str, bool] = {}

    async def on_bar(self, ctx: StrategyContext) -> None:
        quotes = await ctx.quotes(ctx.universe)
        positions = {p.symbol: p.position for p in await ctx.positions()}

        for symbol in ctx.universe:
            q = quotes.get(symbol)
            if not q or q.mid <= 0:
                continue

            series = self._prices[symbol]
            series.append(q.mid)
            if len(series) < self.LONG:
                continue  # 数据不足，等待积累

            short_ma = sum(list(series)[-self.SHORT:]) / self.SHORT
            long_ma = sum(series) / len(series)
            now_above = short_ma > long_ma
            was_above = self._above.get(symbol)
            self._above[symbol] = now_above

            if was_above is None:
                continue  # 首次只记录状态，不触发

            held = positions.get(symbol, 0)

            # 金叉：买入
            if now_above and not was_above:
                await ctx.signal(self.name, symbol, "BUY",
                                 f"金叉 短MA={short_ma:.2f} > 长MA={long_ma:.2f}")
                await ctx.buy(symbol, self.ORDER_QTY)

            # 死叉：若有多头持仓则卖出平仓
            elif not now_above and was_above and held > 0:
                qty = min(self.ORDER_QTY, held)
                await ctx.signal(self.name, symbol, "SELL",
                                 f"死叉 短MA={short_ma:.2f} < 长MA={long_ma:.2f}")
                await ctx.sell(symbol, qty)
