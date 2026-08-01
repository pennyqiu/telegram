#!/usr/bin/env python3
"""
从 IB Gateway 拉取持仓，生成填好数据的持仓快照 Markdown。

只读：连接时 readonly=True，代码不引入任何 Order 相关类。
建议同时在 IB Gateway → Configure → API → Settings 里勾选 Read-Only API，
这样即使代码有问题，Gateway 也会在连接层拒绝下单。

支持多账户：不设置 IB_ACCOUNTS 时拉取该连接下的全部账户，
这正是复盘体系要求「合并口径」所需要的。

用法：
    export IB_HOST=127.0.0.1 IB_PORT=4001 IB_CLIENT_ID=20
    python generate_snapshot.py                     # 输出到 ../历史复盘/持仓快照-<今天>.md
    python generate_snapshot.py --stdout            # 打印到终端
    python generate_snapshot.py --account U1234567  # 只拉指定账户

生成的快照仍有需要手填的部分（投资逻辑、心态记录、规则卡阈值），
脚本会在这些位置留下明确标记。数据部分（持仓、期权名义、穿透暴露）全部自动算好。
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

try:
    from ib_async import IB, AccountValue, Contract, Position
except ImportError:
    sys.exit("缺少依赖：pip install ib_async")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("snapshot")

API_TIMEOUT = 30
HERE = Path(__file__).resolve().parent
WEIGHTS_FILE = HERE / "etf_weights.json"
OUTPUT_DIR = HERE.parent / "历史复盘"


@dataclass
class Pos:
    account: str
    symbol: str
    sec_type: str
    currency: str
    quantity: float
    avg_cost: float          # 股票为每股成本；期权已归一化为每股权利金
    price: float = 0.0
    expiry: str = ""
    strike: float = 0.0
    right: str = ""
    multiplier: float = 1.0

    @property
    def market_value(self) -> float:
        """空头为负值，便于直接与现金相加得到净值。"""
        return self.price * self.quantity * self.multiplier

    @property
    def cost_basis(self) -> float:
        return self.avg_cost * self.quantity * self.multiplier

    @property
    def unrealized(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pct(self) -> float:
        base = abs(self.cost_basis)
        return (self.unrealized / base * 100) if base else 0.0

    @property
    def notional(self) -> float:
        """卖出 Put 的潜在接货义务。其余头寸为 0。"""
        if self.sec_type == "OPT" and self.right.upper().startswith("P") and self.quantity < 0:
            return self.strike * abs(self.quantity) * self.multiplier
        return 0.0

    @property
    def dte(self) -> int:
        if len(self.expiry) < 8:
            return -1
        try:
            exp = date(int(self.expiry[:4]), int(self.expiry[4:6]), int(self.expiry[6:8]))
            return (exp - date.today()).days
        except ValueError:
            return -1

    @property
    def expiry_display(self) -> str:
        if len(self.expiry) < 8:
            return ""
        return f"{self.expiry[:4]}-{self.expiry[4:6]}-{self.expiry[6:8]}"


@dataclass
class Account:
    account_id: str
    net_liquidation: float = 0.0
    total_cash: float = 0.0
    excess_liquidity: float = 0.0
    maint_margin: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    positions: list = field(default_factory=list)


class Puller:
    def __init__(self, host: str, port: int, client_id: int, accounts: list):
        self.host, self.port, self.client_id = host, port, client_id
        self.wanted = set(accounts) if accounts else None
        self.ib = IB()

    async def __aenter__(self):
        await self.ib.connectAsync(
            host=self.host, port=self.port, clientId=self.client_id, readonly=True
        )
        logger.info("已连接 IB Gateway %s:%s（只读）", self.host, self.port)
        return self

    async def __aexit__(self, *exc):
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("已断开连接")

    def _keep(self, account_id: str) -> bool:
        return self.wanted is None or account_id in self.wanted

    async def fetch_accounts(self) -> dict:
        tags = ("NetLiquidation,TotalCashValue,ExcessLiquidity,"
                "MaintMarginReq,UnrealizedPnL,RealizedPnL")
        values = await asyncio.wait_for(
            self.ib.reqAccountSummaryAsync(group="All", tags=tags), timeout=API_TIMEOUT
        )
        out: dict = {}
        for v in values:
            if not self._keep(v.account) or v.currency not in ("USD", ""):
                continue
            acct = out.setdefault(v.account, Account(account_id=v.account))
            try:
                num = float(v.value)
            except ValueError:
                continue
            setattr(acct, {
                "NetLiquidation":  "net_liquidation",
                "TotalCashValue":  "total_cash",
                "ExcessLiquidity": "excess_liquidity",
                "MaintMarginReq":  "maint_margin",
                "UnrealizedPnL":   "unrealized_pnl",
                "RealizedPnL":     "realized_pnl",
            }.get(v.tag, "_ignored"), num)
        if not out:
            raise RuntimeError("未取到任何账户数据，检查 IB_ACCOUNTS 是否填对、Gateway 是否已登录")
        return out

    async def fetch_positions(self) -> list:
        raw: list = await asyncio.wait_for(self.ib.reqPositionsAsync(), timeout=API_TIMEOUT)
        result = []
        for p in raw:
            if not self._keep(p.account) or p.position == 0:
                continue
            c = p.contract
            mult = float(c.multiplier) if (c.secType == "OPT" and c.multiplier) else 1.0
            # IB 对期权返回的 avgCost 是每张合约的成本（已含乘数），归一化成每股权利金
            avg = p.avgCost / mult if c.secType == "OPT" else p.avgCost
            result.append(Pos(
                account=p.account, symbol=c.symbol, sec_type=c.secType,
                currency=c.currency, quantity=p.position, avg_cost=avg,
                expiry=c.lastTradeDateOrContractMonth or "",
                strike=c.strike or 0.0, right=c.right or "", multiplier=mult,
            ))
        return result

    async def fill_prices(self, positions: list) -> None:
        """股票批量取快照；期权逐个短暂订阅后立即取消，避免占用市场数据行。"""
        stocks = [p for p in positions if p.sec_type == "STK"]
        if stocks:
            contracts = []
            for p in stocks:
                c = Contract(symbol=p.symbol, secType="STK",
                             currency=p.currency, exchange="SMART")
                contracts.append(c)
            try:
                tickers = await asyncio.wait_for(
                    self.ib.reqTickersAsync(*contracts), timeout=API_TIMEOUT
                )
                for p, t in zip(stocks, tickers):
                    p.price = _pick_price(t)
            except Exception as e:
                logger.warning("股票行情获取失败（非致命）：%s", e)

        for p in (x for x in positions if x.sec_type == "OPT"):
            await self._fill_option_price(p)

    async def _fill_option_price(self, p: Pos) -> None:
        c = Contract(symbol=p.symbol, secType="OPT", currency=p.currency,
                     exchange="SMART", lastTradeDateOrContractMonth=p.expiry,
                     strike=p.strike, right=p.right, multiplier=str(int(p.multiplier)))
        ticker = None
        try:
            ticker = self.ib.reqMktData(c, genericTickList="13", snapshot=False)
            for _ in range(25):                      # 最多等 5 秒
                await asyncio.sleep(0.2)
                if _pick_price(ticker) > 0:
                    break
            p.price = _pick_price(ticker)
            if p.price <= 0:
                logger.warning("%s %s%s 无行情（盘后？），价格记为 0，请手工补",
                               p.symbol, p.strike, p.right)
        except Exception as e:
            logger.warning("期权行情失败 %s %s%s：%s", p.symbol, p.strike, p.right, e)
        finally:
            if ticker is not None:
                try:
                    self.ib.cancelMktData(c)
                except Exception:
                    pass


def _pick_price(ticker) -> float:
    for attr in ("last", "close", "markPrice"):
        v = getattr(ticker, attr, None)
        if v and v == v and v > 0:                   # v == v 过滤 nan
            return float(v)
    bid, ask = getattr(ticker, "bid", 0), getattr(ticker, "ask", 0)
    if bid and ask and bid > 0 and ask > 0:
        return (bid + ask) / 2
    return 0.0


# ── 穿透计算 ────────────────────────────────────────────────────────────

def compute_lookthrough(positions: list, weights: dict) -> tuple:
    """返回 (单标的穿透暴露 dict, 行业穿透暴露 dict)。"""
    etfs = weights.get("etfs", {})
    indexes = weights.get("indexes", {})
    direct_sectors = weights.get("direct_sectors", {})

    by_symbol: dict = defaultdict(float)
    by_sector: dict = defaultdict(float)

    for p in positions:
        if p.sec_type != "STK" or p.quantity <= 0:
            continue
        mv = p.market_value
        cfg = etfs.get(p.symbol)
        if cfg:
            for sym, w in indexes.get(cfg["index"], {}).items():
                by_symbol[_merge_share_class(sym)] += mv * w
            for sector, w in cfg.get("sectors", {}).items():
                by_sector[sector] += mv * w
        else:
            by_symbol[_merge_share_class(p.symbol)] += mv
            sector = direct_sectors.get(p.symbol)
            if sector:
                by_sector[sector] += mv

    return dict(by_symbol), dict(by_sector)


def _merge_share_class(symbol: str) -> str:
    """GOOGL 与 GOOG 是同一家公司的经济权益，必须合并统计。"""
    return "GOOG(A+C)" if symbol in ("GOOG", "GOOGL") else symbol


# ── Markdown 渲染 ───────────────────────────────────────────────────────

def render(accounts: dict, weights: dict) -> str:
    today = date.today().isoformat()
    all_pos = [p for a in accounts.values() for p in a.positions]
    stocks = sorted((p for p in all_pos if p.sec_type == "STK"),
                    key=lambda p: -p.market_value)
    options = sorted((p for p in all_pos if p.sec_type == "OPT"),
                     key=lambda p: (p.expiry, p.symbol))

    total_nlv = sum(a.net_liquidation for a in accounts.values())
    total_cash = sum(a.total_cash for a in accounts.values())
    total_stock = sum(p.market_value for p in stocks)
    total_opt = sum(p.market_value for p in options)
    total_notional = sum(p.notional for p in options)
    pct = lambda x: (x / total_nlv * 100) if total_nlv else 0.0

    L = []
    add = L.append

    add(f"# 持仓快照 · {today}\n")
    add(f"> 由 `tools/generate_snapshot.py` 于 {datetime.now():%Y-%m-%d %H:%M} 自动生成。")
    add("> 数据部分已算好，**标注「待填」的地方必须手工补充**——尤其是投资逻辑，那部分不能自动化。\n")

    # 1. 基本信息
    add("## 1. 基本信息\n")
    add("| 项目 | 数值 |")
    add("|------|------|")
    add(f"| 数据截止日期 | {today} |")
    add("| 上次复盘日期 | 待填 |")
    add("| 本次复盘类型 | 待填 |")
    add("| 美元兑人民币汇率 | 待填 |")
    add(f"| 合并总资产（USD） | {total_nlv:,.0f} |")
    add("| 合并总资产（CNY 折算） | 待填 |")
    add("| 本期组合收益率 | 待填 |")
    add("| 同期标普500 收益率 | 待填 |")
    add("| 同期纳指100 收益率 | 待填 |\n")

    # 2. 多账户
    add("## 2. 多账户合并汇总\n")
    add("| 账户 | 净值(USD) | 股票市值 | 期权市值 | 现金 | 占合并净值 |")
    add("|------|-----------|----------|----------|------|------------|")
    for a in accounts.values():
        s = sum(p.market_value for p in a.positions if p.sec_type == "STK")
        o = sum(p.market_value for p in a.positions if p.sec_type == "OPT")
        add(f"| {a.account_id} | {a.net_liquidation:,.0f} | {s:,.0f} | {o:,.0f} | "
            f"{a.total_cash:,.0f} | {pct(a.net_liquidation):.1f}% |")
    add(f"| **合并** | **{total_nlv:,.0f}** | {total_stock:,.0f} | {total_opt:,.0f} | "
        f"{total_cash:,.0f} | 100% |\n")
    add("- 账户间资金是否可快速调拨（T+? 天）：待填")
    add("- 若某账户被追缴保证金，可从其他账户调入的金额上限：待填\n")

    # 3. 股票
    add("## 3. 股票持仓\n")
    add("| 账户 | 代码 | 股数 | 平均成本 | 现价 | 市值(USD) | 占合并净值 | 浮动盈亏% | 我的一句话投资逻辑 |")
    add("|------|------|------|----------|------|-----------|------------|-----------|--------------------|")
    for p in stocks:
        add(f"| {p.account} | {p.symbol} | {p.quantity:g} | {p.avg_cost:.2f} | {p.price:.2f} | "
            f"{p.market_value:,.0f} | {pct(p.market_value):.2f}% | {p.unrealized_pct:+.1f}% | **待你手写** |")
    add(f"| | **合计** | | | | **{total_stock:,.0f}** | **{pct(total_stock):.2f}%** | | |\n")
    add("> 「我的一句话投资逻辑」必须自己写。详细版本写在 `../标的档案/<代码>.md`。\n")

    # 4. 穿透
    by_symbol, by_sector = compute_lookthrough(all_pos, weights)
    add("## 4. ETF 穿透暴露\n")
    add(f"> 权重表更新于 {weights.get('_updated', '未知')}，见 `tools/etf_weights.json`。"
        " 指数权重逐日变动，建议每季度更新一次。\n")
    add("**穿透后的单一标的暴露（占比 ≥ 1%）**\n")
    add("| 标的 | 穿透后合计(USD) | 占合并净值 | 是否超过 20% 上限 |")
    add("|------|-----------------|------------|-------------------|")
    for sym, val in sorted(by_symbol.items(), key=lambda kv: -kv[1]):
        if pct(val) < 1.0:
            continue
        flag = "✗ 超限" if pct(val) > 20 else "✓"
        add(f"| {sym} | {val:,.0f} | {pct(val):.2f}% | {flag} |")
    add("")
    add("**穿透后的行业暴露**\n")
    add("| 行业或主题 | 合计(USD) | 占合并净值 |")
    add("|------------|-----------|------------|")
    for sector, val in sorted(by_sector.items(), key=lambda kv: -kv[1]):
        add(f"| {sector} | {val:,.0f} | {pct(val):.2f}% |")
    add(f"| 现金与短债 | {total_cash:,.0f} | {pct(total_cash):.2f}% |\n")

    # 5. 期权
    add("## 5. 期权头寸与名义敞口\n")
    if not options:
        add("无未平仓期权头寸。\n")
    else:
        add("| 账户 | 标的 | 意图 | 权利 | 行权价 | 到期日 | DTE | 张数 | 开仓权利金 | 现价 | 浮动盈亏% | 名义金额 |")
        add("|------|------|------|------|--------|--------|-----|------|------------|------|-----------|----------|")
        for p in options:
            add(f"| {p.account} | {p.symbol} | **待填** | {p.right} | {p.strike:g} | "
                f"{p.expiry_display} | {p.dte} | {p.quantity:g} | {p.avg_cost:.2f} | "
                f"{p.price:.2f} | {p.unrealized_pct:+.1f}% | "
                f"{p.notional:,.0f} |")
        add("")
        add("> 「意图」列必须手填：**接货型**（真心愿意在盈亏平衡价长期持有）或 **收租型**（不打算接货）。")
        add("> 这两者风险性质相反，规则卡对它们设的是完全不同的额度。\n")

        premium = sum(abs(p.cost_basis) for p in options if p.quantity < 0)
        close_cost = sum(abs(p.market_value) for p in options if p.quantity < 0)
        coverage = (total_cash / total_notional * 100) if total_notional else 0.0
        add("**名义敞口汇总**\n")
        add("| 项目 | 金额(USD) | 占合并净值 |")
        add("|------|-----------|------------|")
        add(f"| Put 名义总额 | {total_notional:,.0f} | {pct(total_notional):.1f}% |")
        add(f"| 可用现金 | {total_cash:,.0f} | {pct(total_cash):.2f}% |")
        add(f"| **现金覆盖率** | **{coverage:.2f}%** | — |")
        add(f"| 累计已收权利金 | {premium:,.0f} | — |")
        add(f"| 当前全部平仓成本 | {close_cost:,.0f} | — |")
        add(f"| 期权净浮动盈亏 | {premium - close_cost:+,.0f} | — |\n")
        if coverage < 100 and total_notional > 0:
            add(f"> ⚠️ 现金覆盖率 {coverage:.2f}%，低于 100%。"
                "**这意味着这些 Put 不是现金担保的，而是保证金担保的。**"
                "两者名字相似但风险性质相反，见 `投资规则卡.md` 第 3.1 节。\n")

        add("**到期日集中度**\n")
        by_exp: dict = defaultdict(float)
        for p in options:
            by_exp[p.expiry_display] += p.notional
        add("| 到期日 | 名义金额 | 占合并净值 |")
        add("|--------|----------|------------|")
        for exp, val in sorted(by_exp.items()):
            mark = " ⚠️" if pct(val) > 10 else ""
            add(f"| {exp} | {val:,.0f} | {pct(val):.1f}%{mark} |")
        add("")
        add("**追高检查**（52 周高点需手工填入，脚本无法可靠获取；同时持有正股的标的已自动填现价）\n")
        add("| 标的 | 行权价 | 现价 | 52周高点 | 距现价 | 距52周高点 | 判定 |")
        add("|------|--------|------|----------|--------|------------|------|")
        spot = {p.symbol: p.price for p in stocks if p.price > 0}
        for p in options:
            if p.notional <= 0:
                continue
            u = spot.get(p.symbol)
            if u:
                gap = (p.strike - u) / u * 100
                add(f"| {p.symbol} | {p.strike:g} | {u:.2f} | 待填 | {gap:+.1f}% | 待算 | 待判定 |")
            else:
                add(f"| {p.symbol} | {p.strike:g} | 待填 | 待填 | 待算 | 待算 | 待判定 |")
        add("")
        add("> 规则卡第 3.3 节：行权价须同时 ≤ 52周高点×0.85、≤ 现价×0.85（指数 ETF 为 ×0.90），"
            "且盈亏平衡点 ≤ 标的档案中写下的合理买入区间上限。任一关不过即为变相追高。\n")

    # 6-10 手填部分
    add("## 6. 现金与弹药\n")
    add("| 项目 | 金额(USD) | 占合并净值 |")
    add("|------|-----------|------------|")
    add(f"| 可自由动用现金 | {total_cash:,.0f} | {pct(total_cash):.2f}% |")
    add("| 短债/货币基金 | 待填 | |")
    for a in accounts.values():
        add(f"| {a.account_id} 维持保证金要求 | {a.maint_margin:,.0f} | {pct(a.maint_margin):.1f}% |")
        add(f"| {a.account_id} 剩余流动性 | {a.excess_liquidity:,.0f} | {pct(a.excess_liquidity):.1f}% |")
    add(f"| 若所有 Put 被行权后的剩余现金 | {total_cash - total_notional:,.0f} | "
        f"{pct(total_cash - total_notional):.1f}% |\n")

    add("## 7. 本期已执行操作\n")
    add("| 日期 | 操作 | 标的 | 价格 | 金额 | 当时的理由 | 现在回看是否正确 |")
    add("|------|------|------|------|------|------------|------------------|")
    add("| | | | | | | |\n")

    add("## 8. 规则卡合规自检\n")
    add("> 逐条抄录 `../投资规则卡.md` 的阈值，填当前值，超限即红牌。上面第 4、5 节已经算好了大部分数字。\n")
    add("| 规则 | 阈值 | 当前值 | 状态 |")
    add("|------|------|--------|------|")
    add("| | | | |\n")

    add("## 9. 待兑现的等待条件\n")
    add("> 从 `../决策日志.md` 抄录进行中的条目，逐条更新状态。\n")
    add("| 标的 | 等待条件 | 目标价位 | 现价 | 状态 |")
    add("|------|----------|----------|------|------|")
    add("| | | | | |\n")

    add("## 10. 其他情况说明\n")
    add("- 未来 3 年内的大额确定性支出：待填")
    add("- 本期心态记录（FOMO、恐慌、想抄底、不愿认亏的拖延）：待填")
    add("- 本期是否有操作偏离 playbook 或规则卡，原因：待填\n")
    add("> ⚠️ 本文件仅为个人投资记录，不构成投资建议。")

    return "\n".join(L) + "\n"


async def main() -> int:
    ap = argparse.ArgumentParser(description="从 IB 生成持仓快照 Markdown")
    ap.add_argument("--host", default=os.getenv("IB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("IB_PORT", "4001")))
    ap.add_argument("--client-id", type=int, default=int(os.getenv("IB_CLIENT_ID", "20")))
    ap.add_argument("--account", action="append", default=None,
                    help="只拉指定账户，可重复。不指定则拉取全部账户（合并口径推荐）")
    ap.add_argument("--stdout", action="store_true", help="打印到终端而非写文件")
    args = ap.parse_args()

    accounts_env = os.getenv("IB_ACCOUNTS", "")
    wanted = args.account or ([a.strip() for a in accounts_env.split(",") if a.strip()] or None)

    weights = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))

    async with Puller(args.host, args.port, args.client_id, wanted or []) as puller:
        accounts = await puller.fetch_accounts()
        positions = await puller.fetch_positions()
        await puller.fill_prices(positions)
        for p in positions:
            accounts.setdefault(p.account, Account(account_id=p.account)).positions.append(p)

    missing = [f"{p.symbol} {p.strike:g}{p.right}".strip() for p in positions if p.price <= 0]
    if missing:
        logger.warning("以下 %d 个头寸没取到价格，需手工补：%s", len(missing), ", ".join(missing))

    markdown = render(accounts, weights)

    if args.stdout:
        print(markdown)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_DIR / f"持仓快照-{date.today().isoformat()}.md"
        if out.exists():
            logger.error("%s 已存在，不覆盖。删除或改名后重试。", out.name)
            return 1
        out.write_text(markdown, encoding="utf-8")
        logger.info("已生成 %s", out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
