"""
IB 交易客户端（可下单）

与 ib_monitor/ib_client.py 的根本区别：
  - ib_monitor 是【只读】，Gateway 层 READ_ONLY_API=yes，代码不引入 Order。
  - 本模块【可下单】，因此在代码层叠加多重安全护栏（config.GUARDS）：
      1. DRY_RUN：默认只记录订单，不真实发送给 IB。
      2. 实盘闸门：TRADING_MODE=live 必须配合 ALLOW_LIVE=true。
      3. 白名单 / 单笔金额 / 单标的持仓 / 单日笔数 上限。
  请务必先在模拟盘（paper）+ DRY_RUN 跑通，再逐步放开。

覆盖用户要求的全部 API 操作：
  - 登录流程            -> connect()
  - 拉取股票列表        -> resolve_universe() / scan_market()
  - 查询价格            -> get_quote() / get_quotes()
  - 下单买卖            -> place_market_order() / place_limit_order()
  - 周期性检查数据      -> get_account_snapshot() / get_positions()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from ib_async import (
    IB, Stock, Contract, Ticker, Order, MarketOrder, LimitOrder, Trade,
    Position, AccountValue,
)

import config
from hooks import emit, Event

logger = logging.getLogger(__name__)

_API_TIMEOUT = 30


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class Quote:
    symbol: str
    last: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    ts: datetime = field(default_factory=datetime.now)

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last or self.close


@dataclass
class PositionInfo:
    symbol: str
    sec_type: str
    position: float
    avg_cost: float
    market_price: float = 0.0
    market_value: float = 0.0


@dataclass
class AccountSnapshot:
    net_liquidation: float = 0.0
    available_funds: float = 0.0
    buying_power: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class OrderResult:
    accepted: bool
    dry_run: bool
    symbol: str
    action: str          # BUY / SELL
    quantity: float
    order_type: str      # MKT / LMT
    limit_price: float = 0.0
    order_id: int = 0
    status: str = ""
    reason: str = ""     # 被拒绝时的原因


class OrderRejected(Exception):
    """订单被本地护栏拒绝时抛出"""


# ── 交易客户端 ─────────────────────────────────────────────────────────

class IBTradingClient:
    def __init__(self):
        self._ib = IB()
        self._connected = False
        self.last_successful_check: Optional[datetime] = None
        # 单日下单计数（按自然日重置），用于 max_daily_orders 护栏
        self._order_count_date: date = date.today()
        self._orders_today: int = 0

    # ── 连接 / 登录流程 ───────────────────────────────────────────────

    async def connect(self) -> None:
        """
        登录流程：
          实际的账号密码 + 2FA 登录由 IB Gateway / TWS 完成（见 docs/02-api-deployment.md），
          本客户端只通过本地 socket 连接已登录的 Gateway。
          connect() 即「拿到操作权限」的入口。
        """
        config.assert_live_allowed()  # 实盘安全闸门
        while True:
            try:
                await self._ib.connectAsync(
                    host=config.IB.host,
                    port=config.IB.port,
                    clientId=config.IB.client_id,
                    readonly=False,   # 交易模式：允许下单
                )
                self._connected = True
                mode = "实盘 LIVE" if config.is_live() else "模拟盘 PAPER"
                logger.info(
                    "已连接 IB Gateway %s:%s (clientId=%s, 模式=%s, DRY_RUN=%s)",
                    config.IB.host, config.IB.port, config.IB.client_id,
                    mode, config.GUARDS.dry_run,
                )
                self._ib.disconnectedEvent += self._on_disconnect
                # 绑定成交回调：任何订单状态变化都会触发 hook 通知
                self._ib.orderStatusEvent += self._on_order_status
                self._ib.execDetailsEvent += self._on_exec_details
                await emit(Event.CONNECTED, {
                    "mode": mode, "dry_run": config.GUARDS.dry_run,
                    "account": config.IB.account,
                })
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
        logger.warning("IB Gateway 连接断开，将自动重连...")
        asyncio.create_task(self.connect())

    def is_connected(self) -> bool:
        return self._connected and self._ib.isConnected()

    # ── 成交 / 状态回调（hook 触达来源） ──────────────────────────────

    def _on_order_status(self, trade: Trade) -> None:
        st = trade.orderStatus
        asyncio.create_task(emit(Event.ORDER_STATUS, {
            "symbol": trade.contract.symbol,
            "action": trade.order.action,
            "quantity": trade.order.totalQuantity,
            "status": st.status,
            "filled": st.filled,
            "remaining": st.remaining,
            "avg_fill_price": st.avgFillPrice,
            "order_id": trade.order.orderId,
        }))

    def _on_exec_details(self, trade: Trade, fill) -> None:
        asyncio.create_task(emit(Event.ORDER_FILLED, {
            "symbol": trade.contract.symbol,
            "action": fill.execution.side,
            "shares": fill.execution.shares,
            "price": fill.execution.price,
            "time": str(fill.execution.time),
            "order_id": trade.order.orderId,
        }))

    # ── 拉取股票列表 ──────────────────────────────────────────────────

    async def resolve_universe(self, symbols: list[str]) -> list[Stock]:
        """
        将一组股票代码解析为可交易的合约（qualifyContracts）。
        这是「拉取股票列表」最常用的方式：从配置的标的池得到合法合约。
        """
        if not self.is_connected():
            logger.error("未连接，无法解析合约")
            return []
        contracts = [Stock(sym, "SMART", "USD") for sym in symbols]
        try:
            qualified = await asyncio.wait_for(
                self._ib.qualifyContractsAsync(*contracts),
                timeout=_API_TIMEOUT,
            )
            ok = [c for c in qualified if c.conId]
            logger.info("解析标的池：%d/%d 成功", len(ok), len(symbols))
            return ok
        except Exception as e:
            logger.error("解析合约失败: %s", e)
            return []

    async def scan_market(
        self,
        scan_code: str = "TOP_PERC_GAIN",
        location: str = "STK.US.MAJOR",
        max_rows: int = 20,
    ) -> list[str]:
        """
        市场扫描器：动态「拉取股票列表」（如涨幅榜、成交量榜等）。
        scan_code 常见值：TOP_PERC_GAIN / TOP_PERC_LOSE / MOST_ACTIVE / HOT_BY_VOLUME
        需要市场数据权限，否则返回空列表。
        """
        if not self.is_connected():
            return []
        try:
            from ib_async import ScannerSubscription
            sub = ScannerSubscription(
                instrument="STK",
                locationCode=location,
                scanCode=scan_code,
                numberOfRows=max_rows,
            )
            data = await asyncio.wait_for(
                self._ib.reqScannerDataAsync(sub, []),
                timeout=_API_TIMEOUT,
            )
            symbols = [row.contractDetails.contract.symbol for row in data]
            logger.info("市场扫描 %s 返回 %d 个标的", scan_code, len(symbols))
            return symbols
        except Exception as e:
            logger.warning("市场扫描失败（可能无市场数据权限）: %s", e)
            return []

    # ── 查询价格 ──────────────────────────────────────────────────────

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """批量查询价格（快照模式，高效）。"""
        result: dict[str, Quote] = {}
        if not self.is_connected() or not symbols:
            return result
        contracts = [Stock(sym, "SMART", "USD") for sym in symbols]
        try:
            tickers: list[Ticker] = await asyncio.wait_for(
                self._ib.reqTickersAsync(*contracts),
                timeout=_API_TIMEOUT,
            )
            for c, t in zip(contracts, tickers):
                result[c.symbol] = Quote(
                    symbol=c.symbol,
                    last=_safe(t.last),
                    bid=_safe(t.bid),
                    ask=_safe(t.ask),
                    close=_safe(t.close),
                    volume=_safe(t.volume),
                )
            self.last_successful_check = datetime.now()
        except Exception as e:
            logger.error("查询价格失败: %s", e)
        return result

    async def get_quote(self, symbol: str) -> Optional[Quote]:
        quotes = await self.get_quotes([symbol])
        return quotes.get(symbol)

    # ── 账户 / 持仓（周期性检查数据） ─────────────────────────────────

    async def get_account_snapshot(self) -> Optional[AccountSnapshot]:
        if not self.is_connected():
            return None
        try:
            values: list[AccountValue] = await asyncio.wait_for(
                self._ib.reqAccountSummaryAsync(
                    group="All",
                    tags="NetLiquidation,AvailableFunds,BuyingPower,UnrealizedPnL,RealizedPnL",
                ),
                timeout=_API_TIMEOUT,
            )
            snap = AccountSnapshot()
            for v in values:
                if v.account != config.IB.account or v.currency != "USD":
                    continue
                match v.tag:
                    case "NetLiquidation":
                        snap.net_liquidation = float(v.value)
                    case "AvailableFunds":
                        snap.available_funds = float(v.value)
                    case "BuyingPower":
                        snap.buying_power = float(v.value)
                    case "UnrealizedPnL":
                        snap.unrealized_pnl = float(v.value)
                    case "RealizedPnL":
                        snap.realized_pnl = float(v.value)
            self.last_successful_check = datetime.now()
            return snap
        except Exception as e:
            logger.error("获取账户快照失败: %s", e)
            return None

    async def get_positions(self) -> Optional[list[PositionInfo]]:
        if not self.is_connected():
            return None
        try:
            positions: list[Position] = await asyncio.wait_for(
                self._ib.reqPositionsAsync(), timeout=_API_TIMEOUT,
            )
            result = []
            for pos in positions:
                if pos.account != config.IB.account or pos.position == 0:
                    continue
                result.append(PositionInfo(
                    symbol=pos.contract.symbol,
                    sec_type=pos.contract.secType,
                    position=pos.position,
                    avg_cost=pos.avgCost,
                ))
            return result
        except Exception as e:
            logger.error("获取持仓失败: %s", e)
            return None

    async def get_position_value(self, symbol: str) -> float:
        """获取某标的当前持仓市值（USD），用于持仓上限护栏。"""
        positions = await self.get_positions() or []
        held = next((p for p in positions if p.symbol == symbol), None)
        if not held:
            return 0.0
        quote = await self.get_quote(symbol)
        price = quote.mid if quote else held.avg_cost
        return abs(held.position) * price

    # ── 下单买卖（带安全护栏） ────────────────────────────────────────

    async def place_market_order(
        self, symbol: str, action: str, quantity: float,
    ) -> OrderResult:
        """市价下单。action = 'BUY' | 'SELL'"""
        return await self._place(symbol, action, quantity, "MKT")

    async def place_limit_order(
        self, symbol: str, action: str, quantity: float, limit_price: float,
    ) -> OrderResult:
        """限价下单。"""
        return await self._place(symbol, action, quantity, "LMT", limit_price)

    async def _place(
        self, symbol: str, action: str, quantity: float,
        order_type: str, limit_price: float = 0.0,
    ) -> OrderResult:
        symbol = symbol.upper()
        action = action.upper()

        # —— 护栏校验 ——————————————————————————————————————————————
        try:
            await self._check_guards(symbol, action, quantity, order_type, limit_price)
        except OrderRejected as e:
            logger.warning("订单被护栏拒绝 %s %s %s: %s", action, quantity, symbol, e)
            result = OrderResult(
                accepted=False, dry_run=config.GUARDS.dry_run, symbol=symbol,
                action=action, quantity=quantity, order_type=order_type,
                limit_price=limit_price, status="REJECTED", reason=str(e),
            )
            await emit(Event.ORDER_REJECTED, _order_payload(result))
            return result

        # —— DRY_RUN：只记录不发送 ——————————————————————————————————
        if config.GUARDS.dry_run:
            logger.info("[DRY_RUN] 模拟下单 %s %s %s @ %s",
                        action, quantity, symbol, order_type)
            self._orders_today += 1
            result = OrderResult(
                accepted=True, dry_run=True, symbol=symbol, action=action,
                quantity=quantity, order_type=order_type, limit_price=limit_price,
                status="DRY_RUN",
            )
            await emit(Event.ORDER_SUBMITTED, _order_payload(result))
            return result

        # —— 真实发送 ——————————————————————————————————————————————
        contract = Stock(symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)
        if order_type == "LMT":
            order: Order = LimitOrder(action, quantity, limit_price)
        else:
            order = MarketOrder(action, quantity)
        order.account = config.IB.account

        trade = self._ib.placeOrder(contract, order)
        self._orders_today += 1
        logger.info("已提交订单 #%s %s %s %s", order.orderId, action, quantity, symbol)
        result = OrderResult(
            accepted=True, dry_run=False, symbol=symbol, action=action,
            quantity=quantity, order_type=order_type, limit_price=limit_price,
            order_id=order.orderId, status=trade.orderStatus.status or "Submitted",
        )
        await emit(Event.ORDER_SUBMITTED, _order_payload(result))
        return result

    async def _check_guards(
        self, symbol: str, action: str, quantity: float,
        order_type: str, limit_price: float,
    ) -> None:
        g = config.GUARDS

        if action not in ("BUY", "SELL"):
            raise OrderRejected(f"非法 action: {action}")
        if quantity <= 0:
            raise OrderRejected(f"非法数量: {quantity}")

        # 白名单
        if g.symbol_whitelist and symbol not in g.symbol_whitelist:
            raise OrderRejected(f"{symbol} 不在白名单 {g.symbol_whitelist}")

        # 单日笔数
        today = date.today()
        if today != self._order_count_date:
            self._order_count_date = today
            self._orders_today = 0
        if self._orders_today >= g.max_daily_orders:
            raise OrderRejected(
                f"已达单日下单上限 {g.max_daily_orders} 笔，今日不再下单"
            )

        # 估算订单名义金额
        if order_type == "LMT" and limit_price > 0:
            est_price = limit_price
        else:
            quote = await self.get_quote(symbol)
            est_price = quote.mid if quote else 0.0
        if est_price <= 0:
            raise OrderRejected(f"{symbol} 无法获取有效价格，拒绝市价单以防失控")

        notional = est_price * quantity
        if notional > g.max_order_notional:
            raise OrderRejected(
                f"单笔名义金额 ${notional:,.0f} 超过上限 ${g.max_order_notional:,.0f}"
            )

        # 单标的累计持仓上限（仅对买入方向校验）
        if action == "BUY":
            current_value = await self.get_position_value(symbol)
            if current_value + notional > g.max_position_notional:
                raise OrderRejected(
                    f"{symbol} 持仓将达 ${current_value + notional:,.0f}，"
                    f"超过单标的上限 ${g.max_position_notional:,.0f}"
                )


def _safe(v) -> float:
    """ib_async 在无行情时返回 nan，统一转 0。"""
    try:
        f = float(v)
        return f if f == f and f > 0 else 0.0   # f==f 过滤 nan
    except (TypeError, ValueError):
        return 0.0


def _order_payload(r: OrderResult) -> dict:
    return {
        "symbol": r.symbol, "action": r.action, "quantity": r.quantity,
        "order_type": r.order_type, "limit_price": r.limit_price,
        "dry_run": r.dry_run, "status": r.status, "reason": r.reason,
        "order_id": r.order_id,
    }
