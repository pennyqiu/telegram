"""
策略基类与注册表

所有策略继承 Strategy，并用 @register_strategy("name") 注册。
调度器每个周期调用 strategy.on_bar(ctx)，策略在其中：
  1. 读取行情 / 持仓（通过 ctx.client）
  2. 计算信号
  3. 需要交易时调用 ctx.buy() / ctx.sell()（自动经过安全护栏）

策略本身不直接接触下单细节，所有订单都流经 IBTradingClient 的护栏。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from hooks import emit, Event

logger = logging.getLogger(__name__)


@dataclass
class StrategyContext:
    """提供给策略的运行时上下文。"""
    client: "object"          # IBTradingClient（避免循环导入用 object 标注）
    universe: list[str]

    async def quote(self, symbol: str):
        return await self.client.get_quote(symbol)

    async def quotes(self, symbols: list[str]):
        return await self.client.get_quotes(symbols)

    async def positions(self):
        return await self.client.get_positions() or []

    async def buy(self, symbol: str, qty: float, limit: float | None = None):
        if limit:
            return await self.client.place_limit_order(symbol, "BUY", qty, limit)
        return await self.client.place_market_order(symbol, "BUY", qty)

    async def sell(self, symbol: str, qty: float, limit: float | None = None):
        if limit:
            return await self.client.place_limit_order(symbol, "SELL", qty, limit)
        return await self.client.place_market_order(symbol, "SELL", qty)

    async def signal(self, strategy: str, symbol: str, signal: str, reason: str = ""):
        """发布一条策略信号事件（会触达 Telegram / 邮箱）。"""
        await emit(Event.SIGNAL, {
            "strategy": strategy, "symbol": symbol,
            "signal": signal, "reason": reason,
        })


class Strategy(ABC):
    name: str = "base"

    def __init__(self, params: dict | None = None):
        self.params = params or {}

    @abstractmethod
    async def on_bar(self, ctx: StrategyContext) -> None:
        """每个调度周期被调用一次。"""
        ...


# ── 注册表 ────────────────────────────────────────────────────────────

_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(name: str):
    def deco(cls: type[Strategy]):
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return deco


def build_strategies(names: list[str]) -> list[Strategy]:
    """按名字实例化策略；导入 strategies 包时各策略已完成注册。"""
    instances = []
    for n in names:
        cls = _REGISTRY.get(n)
        if cls is None:
            logger.warning("未知策略：%s（已注册：%s）", n, list(_REGISTRY))
            continue
        instances.append(cls())
        logger.info("已加载策略：%s", n)
    return instances
