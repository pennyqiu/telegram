"""
IB Gateway 只读连接层

安全说明：
  1. Gateway 侧：请在 IB Gateway → Configure → API → Settings 中勾选 "Read-Only API"
     开启后 Gateway 会在连接级别拒绝所有下单/撤单请求，与本代码逻辑无关。
  2. 代码侧：本模块仅调用只读 API 方法，不引入任何 Order 相关类。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ib_async import IB, Position, AccountValue, PortfolioItem, Contract, Ticker

import config

logger = logging.getLogger(__name__)

# 单次 API 调用超时（秒）——超时后抛异常而非无限等待
_API_TIMEOUT = 30


@dataclass
class AccountSnapshot:
    """账户快照，只包含风控所需字段"""
    net_liquidation: float = 0.0       # 账户净值 NLV
    excess_liquidity: float = 0.0      # 剩余流动性
    buying_power: float = 0.0          # 购买力
    unrealized_pnl: float = 0.0        # 未实现盈亏
    realized_pnl: float = 0.0          # 已实现盈亏


@dataclass
class PositionSnapshot:
    """持仓快照"""
    symbol: str
    sec_type: str                      # STK / OPT / FUT 等
    currency: str
    position: float                    # 持仓数量（负数为空头）
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    # 期权专用字段
    expiry: str = ""                   # 到期日 YYYYMMDD
    strike: float = 0.0
    right: str = ""                    # C / P
    dte: int = 0                       # 距到期天数
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    iv: float = 0.0


class IBReadOnlyClient:
    """
    IB Gateway 只读客户端。
    只暴露查询方法，不提供任何下单/撤单接口。
    """

    def __init__(self):
        self._ib = IB()
        self._connected = False
        self.last_successful_check: Optional[datetime] = None   # 心跳用：最近一次成功拉取数据的时间
        self._consecutive_failures: int = 0                     # 连续失败次数，用于通知降噪

    # ── 连接管理 ──────────────────────────────────────────────────

    async def connect(self) -> None:
        """连接到 IB Gateway，断线自动重连"""
        while True:
            try:
                await self._ib.connectAsync(
                    host=config.IB.host,
                    port=config.IB.port,
                    clientId=config.IB.client_id,
                    readonly=True,        # ib_async 层面标记只读
                )
                self._connected = True
                logger.info(
                    "已连接 IB Gateway %s:%s (clientId=%s, readonly=True)",
                    config.IB.host, config.IB.port, config.IB.client_id,
                )
                self._ib.disconnectedEvent += self._on_disconnect
                break
            except Exception as e:
                logger.warning("连接 IB Gateway 失败，30秒后重试: %s", e)
                await asyncio.sleep(30)

    async def disconnect(self) -> None:
        if self._connected:
            self._ib.disconnect()
            self._connected = False
            logger.info("已断开 IB Gateway 连接")

    def _on_disconnect(self) -> None:
        self._connected = False
        self._consecutive_failures += 1
        logger.warning("IB Gateway 连接断开，将自动重连...")
        asyncio.create_task(self.connect())

    def is_connected(self) -> bool:
        return self._connected and self._ib.isConnected()

    # ── 只读查询方法 ──────────────────────────────────────────────

    async def get_account_snapshot(self) -> Optional[AccountSnapshot]:
        """
        获取账户资金快照（NLV、剩余流动性等）。
        返回 None 表示获取失败，调用方应将此视为异常而非"账户正常"。
        """
        if not self.is_connected():
            logger.error("未连接 IB Gateway，无法获取账户数据")
            return None

        try:
            values: list[AccountValue] = await asyncio.wait_for(
                self._ib.reqAccountSummaryAsync(
                    group="All",
                    tags="NetLiquidation,ExcessLiquidity,BuyingPower,UnrealizedPnL,RealizedPnL",
                ),
                timeout=_API_TIMEOUT,
            )
            snap = AccountSnapshot()
            for v in values:
                if v.account != config.IB.account:
                    continue
                if v.currency != "USD":
                    continue
                match v.tag:
                    case "NetLiquidation":
                        snap.net_liquidation = float(v.value)
                    case "ExcessLiquidity":
                        snap.excess_liquidity = float(v.value)
                    case "BuyingPower":
                        snap.buying_power = float(v.value)
                    case "UnrealizedPnL":
                        snap.unrealized_pnl = float(v.value)
                    case "RealizedPnL":
                        snap.realized_pnl = float(v.value)

            # 数据有效性校验：NLV 为 0 是异常信号，不能当作正常数据使用
            if snap.net_liquidation <= 0:
                logger.error("账户快照 NLV=0，数据异常，丢弃本次结果")
                self._consecutive_failures += 1
                return None

            self._consecutive_failures = 0
            self.last_successful_check = datetime.now()
            return snap

        except asyncio.TimeoutError:
            logger.error("获取账户快照超时（>%ss）", _API_TIMEOUT)
            self._consecutive_failures += 1
            return None
        except Exception as e:
            logger.error("获取账户快照失败: %s", e)
            self._consecutive_failures += 1
            return None

    async def get_positions(self) -> Optional[list[PositionSnapshot]]:
        """
        获取所有持仓快照。
        返回 None 表示获取失败（区别于空列表——空列表意味着账户真的没有持仓）。
        调用方收到 None 时应中断本次检查，而非以"无持仓"处理。
        """
        if not self.is_connected():
            logger.error("未连接 IB Gateway，无法获取持仓数据")
            return None

        try:
            positions: list[Position] = await asyncio.wait_for(
                self._ib.reqPositionsAsync(),
                timeout=_API_TIMEOUT,
            )
            result = []
            for pos in positions:
                if pos.account != config.IB.account:
                    continue
                if pos.position == 0:
                    continue

                c = pos.contract
                snap = PositionSnapshot(
                    symbol=c.symbol,
                    sec_type=c.secType,
                    currency=c.currency,
                    position=pos.position,
                    avg_cost=pos.avgCost,
                    market_price=0.0,
                    market_value=0.0,
                    unrealized_pnl=0.0,
                )

                if c.secType == "OPT":
                    snap.expiry = c.lastTradeDateOrContractMonth
                    snap.strike = c.strike
                    snap.right = c.right
                    snap.dte = self._calc_dte(snap.expiry)

                result.append(snap)
            return result

        except asyncio.TimeoutError:
            logger.error("获取持仓超时（>%ss）", _API_TIMEOUT)
            return None
        except Exception as e:
            logger.error("获取持仓失败: %s", e)
            return None

    async def enrich_with_market_data(
        self, positions: list[PositionSnapshot]
    ) -> list[PositionSnapshot]:
        """
        批量补充市场价格和期权 Greeks。
        使用快照行情（不订阅实时流），避免占用市场数据行。
        """
        if not self.is_connected() or not positions:
            return positions

        contracts = []
        for p in positions:
            c = Contract()
            c.symbol = p.symbol
            c.secType = p.sec_type
            c.currency = p.currency
            c.exchange = "SMART"
            if p.sec_type == "OPT":
                c.lastTradeDateOrContractMonth = p.expiry
                c.strike = p.strike
                c.right = p.right
                c.multiplier = "100"
            contracts.append(c)

        try:
            # 快照行情，不需要持续订阅
            tickers: list[Ticker] = await self._ib.reqTickersAsync(*contracts)
            for p, ticker in zip(positions, tickers):
                if ticker.last and ticker.last > 0:
                    p.market_price = ticker.last
                elif ticker.close and ticker.close > 0:
                    p.market_price = ticker.close

                p.market_value = p.market_price * abs(p.position) * (
                    100 if p.sec_type == "OPT" else 1
                )
                p.unrealized_pnl = (p.market_price - p.avg_cost) * p.position * (
                    100 if p.sec_type == "OPT" else 1
                )

                if p.sec_type == "OPT" and ticker.modelGreeks:
                    g = ticker.modelGreeks
                    p.delta = g.delta or 0.0
                    p.gamma = g.gamma or 0.0
                    p.vega = g.vega or 0.0
                    p.theta = g.theta or 0.0
                    p.iv = g.impliedVol or 0.0
        except Exception as e:
            logger.warning("补充市场数据失败（非致命）: %s", e)

        return positions

    # ── 工具方法 ──────────────────────────────────────────────────

    @staticmethod
    def _calc_dte(expiry: str) -> int:
        """根据到期日字符串（YYYYMMDD）计算距今天数"""
        from datetime import date
        if not expiry or len(expiry) < 8:
            return 999
        try:
            exp_date = date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8]))
            return max(0, (exp_date - date.today()).days)
        except ValueError:
            return 999
