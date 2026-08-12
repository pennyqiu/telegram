#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场内纳指/标普 QDII 的量化策略回测（择时层 + 选券层 + 溢价证据）。

回答三个问题：
  ① 什么时候买：溢价过滤、回撤阶梯、趋势过滤、动量轮动、价值平均、溢价止盈
     ——十条规则在 513100（2013 起）/ 513500（2013 起）上跑同一套资金约束
  ② 买哪一只：16 只同指数 QDII 里按费率 / 溢价 / 综合分选，看终值差多少
  ③ 溢价到底值多少钱：按买入日溢价分组，看未来 20/60/120 日「市价收益 − 净值收益」
     ——这是溢价择时有没有用的直接证据，不是靠讲道理

资金约束（所有策略共用，否则没法公平比）：
  - 每月首个交易日固定入账 MONTHLY 元进现金池
  - 池里的钱按货基年化计息，策略决定何时投出多少
  - 终值 = 持仓市值 + 现金池；IRR 用「每月入账」当现金流，闲置现金的机会成本自动计入
  - 买卖计单边成本 TRADE_COST

口径：
  - 持仓市值走后复权成交价（分红再投），溢价波动、汇率、跟踪误差、费率全在里面
  - 溢价 =（不复权收盘价 − 单位净值）/ 单位净值，与 fetch_qdii_premium.py 一致
  - 决策只用 ≤ 当日的数据；净值披露滞后 1 日左右，故当日读到的是最近一个已披露溢价

数据：friends/tools/fetch_qdii_quant_data.py 抓取的 CSV

用法：
  python3 friends/tools/qdii_quant.py
  python3 friends/tools/qdii_quant.py --json friends/qdii-quant.json

仅供研究，非投资建议。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
DATA_DIR = TOOLS_DIR / "backtest_data"
RAW_DIR = DATA_DIR / "raw_price"
NAV_DIR = DATA_DIR / "nav"
ACC_DIR = DATA_DIR / "nav_acc"
WATCHLIST = TOOLS_DIR / "qdii_watchlist.json"

MONTHLY = 10_000.0          # 每月入账
CASH_RATE = 0.015           # 现金池年化（货基）
TRADE_COST = 0.0003         # 单边交易成本
PREM_WINDOW = 250           # 溢价分位的回看窗口（交易日）
PREM_MAX_ABS = 0.30         # 超过此绝对值视为份额折算错位，剔除
NAV_STALE_MAX = 7           # 溢价滞后超过这么多天就当作读不到
PREM_LAG = 1                # 决策只用上一交易日及更早的溢价，杜绝前视

DIVIDEND = "510880"         # 溢价过高时的境内替代去处
BENCH_USD = {"纳指100": "QQQ", "标普500": "SPY"}


# ============================================================================
# 数据层
# ============================================================================
def load_csv(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["date"]
            val = next(v for k, v in row.items() if k != "date")
            try:
                out[key] = float(val)
            except (TypeError, ValueError):
                continue
    return out


class Market:
    """所有序列 + 派生信号。所有取值函数都只回看，不会碰到未来数据。"""

    def __init__(self, codes: list[str], extra: list[str]) -> None:
        self.adj: dict[str, dict[str, float]] = {}
        self.raw: dict[str, dict[str, float]] = {}
        self.nav: dict[str, dict[str, float]] = {}
        self.acc: dict[str, dict[str, float]] = {}
        for c in codes + extra:
            self.adj[c] = load_csv(DATA_DIR / f"{c}.csv")
            self.raw[c] = load_csv(RAW_DIR / f"{c}.csv")
            self.nav[c] = load_csv(NAV_DIR / f"{c}.csv")
            self.acc[c] = load_csv(ACC_DIR / f"{c}.csv")
        self.fx = load_csv(DATA_DIR / "USDCNY.csv")
        for b in ("QQQ", "SPY"):
            self.adj[b] = load_csv(DATA_DIR / f"{b}.csv")

        # 溢价序列 + 有序日期，供分位数与滞后查找
        self.prem: dict[str, dict[str, float]] = {}
        self.prem_days: dict[str, list[str]] = {}
        for c in codes:
            s = {
                d: self.raw[c][d] / self.nav[c][d] - 1
                for d in sorted(set(self.raw[c]) & set(self.nav[c]))
                if self.nav[c][d] > 0
                and abs(self.raw[c][d] / self.nav[c][d] - 1) < PREM_MAX_ABS
            }
            self.prem[c] = s
            self.prem_days[c] = sorted(s)

        self.adj_days = {c: sorted(s) for c, s in self.adj.items()}
        self._ma_cache: dict[tuple[str, int], dict[str, float]] = {}
        self._prem_idx = {
            c: {d: i for i, d in enumerate(days)} for c, days in self.prem_days.items()
        }

    # ---- 价格 ----
    def price(self, code: str, d: str) -> float | None:
        return self.adj.get(code, {}).get(d)

    def last_price(self, code: str, d: str) -> float | None:
        """最近一个 ≤ d 的后复权价（美股/汇率与 A 股休市日不同，需要对齐）"""
        s = self.adj.get(code) or {}
        if d in s:
            return s[d]
        days = self.adj_days.get(code) or []
        i = _bisect_right(days, d)
        return s[days[i - 1]] if i else None

    # ---- 溢价 ----
    def premium(self, code: str, d: str, lag: int = PREM_LAG) -> float | None:
        """决策时读得到的溢价。

        T 日净值要到 T+1 才公布，所以默认滞后一个交易日。实盘里券商的 IOPV
        是实时的，用滞后值等于低估了信号质量，结论偏保守。
        """
        days = self.prem_days.get(code) or []
        i = _bisect_right(days, d) - lag
        if i <= 0:
            return None
        last = days[i - 1]
        if (_to_date(d) - _to_date(last)).days > NAV_STALE_MAX:
            return None
        return self.prem[code][last]

    def prem_rank(self, code: str, d: str) -> float | None:
        """当前溢价在过去窗口中的百分位（0~1，越高越贵）"""
        p = self.premium(code, d)
        if p is None:
            return None
        days = self.prem_days.get(code) or []
        i = max(0, _bisect_right(days, d) - PREM_LAG)
        window = [self.prem[code][x] for x in days[max(0, i - PREM_WINDOW): i]]
        if len(window) < 60:
            return None
        return sum(1 for v in window if v <= p) / len(window)

    # ---- 趋势 / 回撤 / 动量 ----
    def ma(self, code: str, d: str, n: int) -> float | None:
        cache = self._ma_cache.setdefault((code, n), {})
        if d in cache:
            return cache[d]
        days = self.adj_days.get(code) or []
        i = _bisect_right(days, d)
        if i < n:
            return None
        vals = [self.adj[code][x] for x in days[i - n: i]]
        cache[d] = sum(vals) / n
        return cache[d]

    def drawdown(self, code: str, d: str, window: int = 250) -> float | None:
        """相对过去 window 日最高收盘的回撤（负数）"""
        days = self.adj_days.get(code) or []
        i = _bisect_right(days, d)
        if i < 30:
            return None
        vals = [self.adj[code][x] for x in days[max(0, i - window): i]]
        peak = max(vals)
        return vals[-1] / peak - 1 if peak > 0 else None

    def momentum(self, code: str, d: str, months: int) -> float | None:
        """过去 months 个月的涨幅（后复权口径）"""
        p_now = self.last_price(code, d)
        past = _shift_months(d, -months)
        p_old = self.last_price(code, past)
        if p_now is None or p_old is None or p_old <= 0:
            return None
        return p_now / p_old - 1


def _bisect_right(days: list[str], d: str) -> int:
    lo, hi = 0, len(days)
    while lo < hi:
        mid = (lo + hi) // 2
        if days[mid] <= d:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _to_date(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _shift_months(d: str, delta: int) -> str:
    y, m, day = int(d[:4]), int(d[5:7]), d[8:10]
    total = (y * 12 + m - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}-{day}"


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


# ============================================================================
# 回测引擎
# ============================================================================
class Portfolio:
    def __init__(self, mkt: Market) -> None:
        self.mkt = mkt
        self.cash = 0.0
        self.units: dict[str, float] = {}
        self.prem_paid = 0.0      # 累计支付的溢价（买入金额 × 当日溢价）
        self.cost_paid = 0.0
        self.n_buys = 0
        self.n_sells = 0
        self.bought: dict[str, float] = {}   # 各标的累计买入金额

    def holdings_value(self, d: str) -> float:
        return sum(
            u * (self.mkt.last_price(c, d) or 0.0) for c, u in self.units.items()
        )

    def total(self, d: str) -> float:
        return self.cash + self.holdings_value(d)

    def buy(self, code: str, amount: float, d: str) -> None:
        amount = min(amount, self.cash)
        px = self.mkt.last_price(code, d)
        if amount <= 0 or not px:
            return
        cost = amount * TRADE_COST
        net = amount - cost
        self.units[code] = self.units.get(code, 0.0) + net / px
        self.cash -= amount
        self.cost_paid += cost
        self.bought[code] = self.bought.get(code, 0.0) + amount
        self.n_buys += 1
        p = self.mkt.premium(code, d)
        if p is not None:
            self.prem_paid += amount * p

    def sell(self, code: str, fraction: float, d: str) -> None:
        u = self.units.get(code, 0.0)
        px = self.mkt.last_price(code, d)
        if u <= 0 or not px or fraction <= 0:
            return
        sold = u * min(1.0, fraction)
        gross = sold * px
        cost = gross * TRADE_COST
        self.units[code] = u - sold
        self.cash += gross - cost
        self.cost_paid += cost
        self.n_sells += 1


class Context:
    """策略每日拿到的东西"""

    def __init__(self, mkt: Market, port: Portfolio, primary: str, group: str,
                 monthly: float) -> None:
        self.mkt = mkt
        self.port = port
        self.primary = primary
        self.group = group
        self.monthly = monthly
        self.d = ""
        self.is_contrib_day = False
        self.month_idx = 0
        self.state: dict = {}


Rule = Callable[[Context], None]


def irr_monthly(flows: list[float]) -> float:
    def npv(r: float) -> float:
        return sum(f / (1 + r) ** i for i, f in enumerate(flows))

    lo, hi = -0.95, 2.0
    if npv(lo) * npv(hi) > 0:
        return float("nan")
    for _ in range(300):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    r = (lo + hi) / 2
    return (1 + r) ** 12 - 1


def run_strategy(
    mkt: Market,
    rule: Rule,
    days: list[str],
    primary: str,
    group: str,
    monthly: float = MONTHLY,
    keep_curve: bool = True,
) -> dict:
    port = Portfolio(mkt)
    ctx = Context(mkt, port, primary, group, monthly)
    daily_cash_factor = (1 + CASH_RATE) ** (1 / 252) - 1

    flows: list[float] = []
    nav, nav_peak, nav_max_dd = 1.0, 1.0, 0.0
    equity_peak, acct_max_dd = 0.0, 0.0
    idle_ratio: list[float] = []
    curve: list[tuple[str, float]] = []
    month_seen: set[str] = set()
    contributed = 0.0
    prev_total: float | None = None

    for d in days:
        port.cash *= 1 + daily_cash_factor

        # 交易前的总值：只有价格变动与利息，是当日的时间加权收益
        cur = port.total(d)
        if prev_total and prev_total > 0:
            nav *= cur / prev_total
            nav_peak = max(nav_peak, nav)
            nav_max_dd = min(nav_max_dd, nav / nav_peak - 1)

        ctx.d = d
        ctx.is_contrib_day = d[:7] not in month_seen
        if ctx.is_contrib_day:
            month_seen.add(d[:7])
            port.cash += monthly
            contributed += monthly
            flows.append(-monthly)
            ctx.month_idx = len(month_seen)

        rule(ctx)

        after = port.total(d)
        prev_total = after
        equity_peak = max(equity_peak, after)
        if equity_peak > 0:
            acct_max_dd = min(acct_max_dd, after / equity_peak - 1)
        if after > 0:
            idle_ratio.append(port.cash / after)
        if keep_curve:
            curve.append((d, after))

    final = port.total(days[-1])
    flows[-1] += final
    years = (_to_date(days[-1]) - _to_date(days[0])).days / 365.25

    return {
        "final": final,
        "contributed": contributed,
        "multiple": final / contributed if contributed else float("nan"),
        "irr": irr_monthly(flows),
        "nav_max_dd": nav_max_dd,
        "acct_max_dd": acct_max_dd,
        "idle_mean": statistics.fmean(idle_ratio) if idle_ratio else 0.0,
        "prem_paid": port.prem_paid,
        # 分母用累计买入额而非累计入账：会清仓重建的策略买入额远大于入账额
        "prem_paid_pct": port.prem_paid / sum(port.bought.values())
        if port.bought else 0.0,
        "turnover": sum(port.bought.values()) / contributed if contributed else 0.0,
        "cost_paid": port.cost_paid,
        "n_buys": port.n_buys,
        "n_sells": port.n_sells,
        "end_cash": port.cash,
        "years": years,
        "start": days[0],
        "end": days[-1],
        "bought": port.bought,
        "curve": curve,
    }


def month_start_indices(days: list[str]) -> list[int]:
    seen: set[str] = set()
    out = []
    for i, d in enumerate(days):
        if d[:7] not in seen:
            seen.add(d[:7])
            out.append(i)
    return out


def rolling_analysis(
    mkt: Market,
    specs: list[dict],
    days: list[str],
    primary: str,
    group: str,
    monthly: float,
    span_months: int = 36,
    base_id: str = "T0",
) -> dict:
    """在所有可能的起点上重跑一遍，看结论是不是只在某一段行情里成立"""
    starts = month_start_indices(days)
    n_win = len(starts) - span_months
    if n_win < 12:
        return {}
    per_window: list[dict[str, float]] = []
    for k in range(n_win):
        seg = days[starts[k]: starts[k + span_months]]
        row = {
            s["id"]: run_strategy(
                mkt, s["rule"], seg, primary, group, monthly, keep_curve=False
            )["irr"]
            for s in specs
        }
        per_window.append(row)

    stats = {}
    for s in specs:
        sid = s["id"]
        vals = [w[sid] for w in per_window if not math.isnan(w[sid])]
        gaps = [
            w[sid] - w[base_id] for w in per_window
            if not (math.isnan(w[sid]) or math.isnan(w[base_id]))
        ]
        if not vals:
            continue
        stats[sid] = {
            "name": s["name"],
            "n": len(vals),
            "min": min(vals),
            "p25": _pct(vals, 0.25),
            "median": statistics.median(vals),
            "p75": _pct(vals, 0.75),
            "max": max(vals),
            "mean_gap": statistics.fmean(gaps) if gaps else float("nan"),
            "beat_base": sum(1 for g in gaps if g > 0) / len(gaps) if gaps else float("nan"),
        }
    return {
        "span_months": span_months,
        "n_windows": n_win,
        "first_start": days[starts[0]],
        "last_start": days[starts[n_win - 1]],
        "base": base_id,
        "stats": stats,
    }


# ============================================================================
# 择时策略：什么时候买
# ============================================================================
def make_timing_rules(primary: str, alt: str) -> list[dict]:
    """每条规则都在「每月入账、现金池计息」的同一约束下运行"""

    def dca(ctx: Context) -> None:
        if ctx.is_contrib_day:
            ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)

    def prem_fixed(threshold: float) -> Rule:
        """溢价低于阈值就把池子全投出去；否则一分不投，攒着等"""
        def rule(ctx: Context) -> None:
            p = ctx.mkt.premium(ctx.primary, ctx.d)
            if p is None:
                if ctx.is_contrib_day:
                    ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
                return
            if p < threshold:
                ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
        return rule

    def prem_rank_rule(max_rank: float) -> Rule:
        """溢价处于自身历史低分位时才买，比固定阈值更能适应溢价整体上移"""
        def rule(ctx: Context) -> None:
            r = ctx.mkt.prem_rank(ctx.primary, ctx.d)
            if r is None:
                if ctx.is_contrib_day:
                    ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
                return
            if r <= max_rank:
                ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
        return rule

    def prem_divert(threshold: float) -> Rule:
        """溢价高时不等待，本月这笔钱改买境内红利，钱始终在市场里"""
        def rule(ctx: Context) -> None:
            if not ctx.is_contrib_day:
                return
            p = ctx.mkt.premium(ctx.primary, ctx.d)
            target = ctx.primary if p is None or p < threshold else alt
            ctx.port.buy(target, ctx.port.cash, ctx.d)
        return rule

    def dip_ladder(ctx: Context) -> None:
        """平时只投 70%，攒下的弹药等回撤 15% / 25% 时分两次打出去"""
        st = ctx.state
        if ctx.is_contrib_day:
            ctx.port.buy(ctx.primary, min(ctx.monthly * 0.70, ctx.port.cash), ctx.d)
        dd = ctx.mkt.drawdown(ctx.primary, ctx.d, 250)
        if dd is None:
            return
        if dd > -0.10:                      # 回到高点附近，重新装弹
            st["fired"] = set()
        fired = st.setdefault("fired", set())
        if dd <= -0.25 and 25 not in fired:
            fired.update({15, 25})
            ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
        elif dd <= -0.15 and 15 not in fired:
            fired.add(15)
            ctx.port.buy(ctx.primary, ctx.port.cash * 0.5, ctx.d)

    def ma_filter(ctx: Context) -> None:
        """站上 200 日线才买，跌破只停买不卖"""
        px = ctx.mkt.last_price(ctx.primary, ctx.d)
        ma = ctx.mkt.ma(ctx.primary, ctx.d, 200)
        if ma is None:
            if ctx.is_contrib_day:
                ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
            return
        if px and px > ma:
            ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)

    def ma_trade(ctx: Context) -> None:
        """完整趋势择时：上穿 200 日线满仓，下穿清仓"""
        px = ctx.mkt.last_price(ctx.primary, ctx.d)
        ma = ctx.mkt.ma(ctx.primary, ctx.d, 200)
        if ma is None or not px:
            if ctx.is_contrib_day:
                ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
            return
        if px > ma:
            ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
        elif ctx.port.units.get(ctx.primary, 0.0) > 0:
            ctx.port.sell(ctx.primary, 1.0, ctx.d)

    def momentum_new_money(ctx: Context) -> None:
        """新钱买过去 6 个月最强的那个，存量不动"""
        if not ctx.is_contrib_day:
            return
        cands = [primary, alt] + (["513500"] if primary != "513500" else ["513100"])
        scored = [
            (c, ctx.mkt.momentum(c, ctx.d, 6))
            for c in cands
            if ctx.mkt.momentum(c, ctx.d, 6) is not None
        ]
        target = max(scored, key=lambda kv: kv[1])[0] if scored else ctx.primary
        ctx.port.buy(target, ctx.port.cash, ctx.d)

    def momentum_full(ctx: Context) -> None:
        """整仓轮动到过去 6 个月最强的那个"""
        if not ctx.is_contrib_day:
            return
        cands = [primary, alt] + (["513500"] if primary != "513500" else ["513100"])
        scored = [
            (c, ctx.mkt.momentum(c, ctx.d, 6))
            for c in cands
            if ctx.mkt.momentum(c, ctx.d, 6) is not None
        ]
        target = max(scored, key=lambda kv: kv[1])[0] if scored else ctx.primary
        for c in list(ctx.port.units):
            if c != target and ctx.port.units[c] > 0:
                ctx.port.sell(c, 1.0, ctx.d)
        ctx.port.buy(target, ctx.port.cash, ctx.d)

    def value_averaging(ctx: Context) -> None:
        """目标市值按 8%/年 的斜坡走，落后就多买、超前就停买（钱留池）"""
        if not ctx.is_contrib_day:
            return
        n = ctx.month_idx
        target = ctx.monthly * sum(1.08 ** ((n - k) / 12) for k in range(1, n + 1))
        have = ctx.port.holdings_value(ctx.d)
        gap = target - have
        if gap > 0:
            ctx.port.buy(ctx.primary, min(gap, ctx.port.cash), ctx.d)

    def prem_take_profit(ctx: Context) -> None:
        """定投照做；溢价冲到历史 95 分位卖 15% 份额，回落到 40 分位以下买回

        卖出的钱要与每月定投的钱分开，否则下个定投日就原价买回去了，止盈等于没做。
        """
        st = ctx.state
        if ctx.is_contrib_day:
            ctx.port.buy(ctx.primary, min(ctx.monthly, ctx.port.cash), ctx.d)
        r = ctx.mkt.prem_rank(ctx.primary, ctx.d)
        if r is None:
            return
        if r >= 0.95 and not st.get("trimmed"):
            ctx.port.sell(ctx.primary, 0.15, ctx.d)
            st["trimmed"] = True
        elif r <= 0.40 and st.get("trimmed"):
            ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
            st["trimmed"] = False

    def prem_chase(ctx: Context) -> None:
        """反面对照：只在溢价冲进历史前 30% 时买，量化「追高」的代价

        攒到 6 个月还没等到贵的就投出去，避免钱无限堆在池里失去可比性。
        """
        r = ctx.mkt.prem_rank(ctx.primary, ctx.d)
        st = ctx.state
        if r is not None and r >= 0.70:
            ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
            st["wait"] = 0
        elif ctx.is_contrib_day:
            st["wait"] = st.get("wait", 0) + 1
            if st["wait"] >= 6:
                ctx.port.buy(ctx.primary, ctx.port.cash, ctx.d)
                st["wait"] = 0

    return [
        {"id": "T0", "name": "每月无脑定投", "note": "基准：入账当日全额买入", "rule": dca},
        {"id": "T1", "name": "溢价<2%才买", "note": "否则钱留现金池，等溢价回落再一次投出",
         "rule": prem_fixed(0.02)},
        {"id": "T2", "name": "溢价<1%才买", "note": "更严格的阈值，等更久", "rule": prem_fixed(0.01)},
        {"id": "T3", "name": "溢价在历史后30%才买", "note": "动态分位，能适应溢价整体上移",
         "rule": prem_rank_rule(0.30)},
        {"id": "T4", "name": "溢价≥2%改买红利", "note": "不等待，钱换到境内红利 510880",
         "rule": prem_divert(0.02)},
        {"id": "T5", "name": "回撤阶梯（70%+弹药）", "note": "平时投七成，回撤15%/25%时打出弹药",
         "rule": dip_ladder},
        {"id": "T6", "name": "200日线上方才买", "note": "跌破只停买不卖，钱留池", "rule": ma_filter},
        {"id": "T7", "name": "200日线择时（会清仓）", "note": "下穿清仓、上穿满仓，看择时代价",
         "rule": ma_trade},
        {"id": "T8", "name": "6月动量·新钱轮动", "note": "新钱买最强的，存量不动",
         "rule": momentum_new_money},
        {"id": "T9", "name": "6月动量·整仓轮动", "note": "整仓换到最强的那个",
         "rule": momentum_full},
        {"id": "TA", "name": "价值平均法", "note": "目标市值按8%/年斜坡，落后多买超前停买",
         "rule": value_averaging},
        {"id": "TB", "name": "定投+溢价止盈", "note": "溢价95分位卖15%，回40分位买回",
         "rule": prem_take_profit},
        {"id": "TZ", "name": "反面对照·专挑贵的买", "note": "只在溢价前30%时买（等满6个月强制投）",
         "rule": prem_chase},
    ]


# ============================================================================
# 选券策略：买哪一只
# ============================================================================
def make_picking_rules(codes: list[str], fees: dict[str, float]) -> list[dict]:
    cheapest = min(codes, key=lambda c: fees.get(c, 9.9))
    biggest = codes[0]  # watchlist 内按规模/上市顺序，首只为老牌大规模
    min_fee = min(fees.get(c, 9.9) for c in codes)
    cheap_tier = [c for c in codes if fees.get(c, 9.9) <= min_fee + 1e-9]

    def fixed(code: str) -> Rule:
        def rule(ctx: Context) -> None:
            if ctx.is_contrib_day:
                ctx.port.buy(code, ctx.port.cash, ctx.d)
        return rule

    def lowest_premium(ctx: Context) -> None:
        if not ctx.is_contrib_day:
            return
        scored = [
            (c, ctx.mkt.premium(c, ctx.d)) for c in codes
            if ctx.mkt.premium(c, ctx.d) is not None
            and ctx.mkt.last_price(c, ctx.d)
        ]
        target = min(scored, key=lambda kv: kv[1])[0] if scored else biggest
        ctx.port.buy(target, ctx.port.cash, ctx.d)

    def score_prem_fee(ctx: Context) -> None:
        """溢价是一次性成本、费率是每年成本：把费率折成 3 年持有期的等价溢价再比"""
        if not ctx.is_contrib_day:
            return
        scored = []
        for c in codes:
            p = ctx.mkt.premium(c, ctx.d)
            if p is None or not ctx.mkt.last_price(c, ctx.d):
                continue
            scored.append((c, p + fees.get(c, 1.0) / 100 * 3))
        target = min(scored, key=lambda kv: kv[1])[0] if scored else biggest
        ctx.port.buy(target, ctx.port.cash, ctx.d)

    def best_tracker(ctx: Context) -> None:
        """买过去一年净值涨得最多的那只：同指数下净值差异只能来自跟踪质量与费率"""
        if not ctx.is_contrib_day:
            return
        scored = []
        for c in codes:
            acc = ctx.mkt.acc.get(c) or {}
            now = _last_val(acc, ctx.d)
            past = _last_val(acc, _shift_months(ctx.d, -12))
            if now and past and past > 0 and ctx.mkt.last_price(c, ctx.d):
                scored.append((c, now / past))
        target = max(scored, key=lambda kv: kv[1])[0] if scored else biggest
        ctx.port.buy(target, ctx.port.cash, ctx.d)

    def cheap_tier_lowest_premium(ctx: Context) -> None:
        """先用费率把池子缩到最低那一档，再在档内挑溢价最低的

        费率是事前就写在合同里的，跟踪质量要事后才知道，所以这条规则完全可执行。
        """
        if not ctx.is_contrib_day:
            return
        scored = [
            (c, ctx.mkt.premium(c, ctx.d)) for c in cheap_tier
            if ctx.mkt.premium(c, ctx.d) is not None and ctx.mkt.last_price(c, ctx.d)
        ]
        target = min(scored, key=lambda kv: kv[1])[0] if scored else cheapest
        ctx.port.buy(target, ctx.port.cash, ctx.d)

    def equal_weight(ctx: Context) -> None:
        if not ctx.is_contrib_day:
            return
        avail = [c for c in codes if ctx.mkt.last_price(c, ctx.d)]
        if not avail:
            return
        each = ctx.port.cash / len(avail)
        for c in avail:
            ctx.port.buy(c, each, ctx.d)

    return [
        {"id": "C0", "name": f"始终买老牌大规模（{biggest}）", "rule": fixed(biggest)},
        {"id": "C1", "name": f"始终买费率最低（{cheapest}）", "rule": fixed(cheapest)},
        {"id": "C2", "name": "每月买当月溢价最低", "rule": lowest_premium},
        {"id": "C3", "name": "溢价+费率综合分最低", "rule": score_prem_fee},
        {"id": "C4", "name": "等权买全部（分散溢价）", "rule": equal_weight},
        {"id": "C5", "name": "买过去1年净值最强（跟踪质量）", "rule": best_tracker},
        {"id": "C6", "name": f"最低费率档内比溢价（{len(cheap_tier)}只）",
         "rule": cheap_tier_lowest_premium},
    ]


# ============================================================================
# 溢价证据：买在高溢价日，未来到底亏多少
# ============================================================================
def premium_evidence(mkt: Market, codes: list[str], horizons=(20, 60, 120)) -> dict:
    """按买入日溢价分档，统计未来 N 日「市价收益 − 净值收益」

    市价收益用后复权价、净值收益用累计净值，两者之差就是溢价变化带来的损益。
    净值收益本身与买点无关，所以这个差额是溢价择时的干净证据。
    """
    buckets = [
        ("折价 <0%", -9.9, 0.0),
        ("0~1%", 0.0, 0.01),
        ("1~2%", 0.01, 0.02),
        ("2~5%", 0.02, 0.05),
        (">5%", 0.05, 9.9),
    ]
    out: dict[str, dict] = {}
    for h in horizons:
        rows = {label: [] for label, _, _ in buckets}
        for c in codes:
            days = mkt.prem_days.get(c) or []
            adj, acc = mkt.adj.get(c) or {}, mkt.acc.get(c) or {}
            common = sorted(set(adj) & set(acc))
            idx = {d: i for i, d in enumerate(common)}
            for d in days:
                if d not in idx:
                    continue
                i = idx[d]
                if i + h >= len(common):
                    continue
                d2 = common[i + h]
                if adj[d] <= 0 or acc[d] <= 0:
                    continue
                excess = (adj[d2] / adj[d]) / (acc[d2] / acc[d]) - 1
                p = mkt.prem[c][d]
                for label, lo, hi in buckets:
                    if lo <= p < hi:
                        rows[label].append(excess)
                        break
        out[str(h)] = {
            label: {
                "n": len(v),
                "mean": statistics.fmean(v) if v else float("nan"),
                "median": statistics.median(v) if v else float("nan"),
                "win": sum(1 for x in v if x > 0) / len(v) if v else float("nan"),
            }
            for label, v in rows.items()
        }
    return out


def premium_stats(mkt: Market, codes: list[str], names: dict[str, str]) -> list[dict]:
    out = []
    for c in codes:
        s = mkt.prem.get(c) or {}
        if not s:
            continue
        vals = list(s.values())
        days = sorted(s)
        out.append({
            "code": c,
            "name": names.get(c, c),
            "start": days[0],
            "end": days[-1],
            "n": len(vals),
            "median": statistics.median(vals),
            "mean": statistics.fmean(vals),
            "p10": _pct(vals, 0.10),
            "p90": _pct(vals, 0.90),
            "max": max(vals),
            "share_lt2": sum(1 for v in vals if v < 0.02) / len(vals),
            "share_gt5": sum(1 for v in vals if v > 0.05) / len(vals),
            "vol": statistics.stdev(vals) if len(vals) > 2 else float("nan"),
        })
    return out


def _track_row(mkt: Market, code: str, name: str, group: str, fee: float,
               d0: str, d1: str) -> dict | None:
    acc = mkt.acc.get(code) or {}
    a0, a1 = _last_val(acc, d0), _last_val(acc, d1)
    bench = BENCH_USD.get(group, "QQQ")
    b0, b1 = mkt.last_price(bench, d0), mkt.last_price(bench, d1)
    f0, f1 = _last_val(mkt.fx, d0), _last_val(mkt.fx, d1)
    yrs = (_to_date(d1) - _to_date(d0)).days / 365.25
    if not (a0 and a1 and b0 and b1 and f0 and f1) or yrs < 0.9:
        return None
    fund = (a1 / a0) ** (1 / yrs) - 1
    idx = ((b1 * f1) / (b0 * f0)) ** (1 / yrs) - 1
    return {
        "code": code, "name": name, "group": group, "bench": bench,
        "start": d0, "end": d1, "years": yrs,
        "fund_cagr": fund, "bench_cagr": idx, "gap": fund - idx, "fee": fee,
    }


def premium_spread(mkt: Market, codes: list[str], groups: dict[str, str],
                   min_members: int = 4) -> dict:
    """同组同一天「最贵那只 − 最便宜那只」的溢价差：比价最多能省多少钱"""
    out: dict[str, dict] = {}
    for g in ("纳指100", "标普500"):
        members = [c for c in codes if groups.get(c) == g]
        by_date: dict[str, list[tuple[str, float]]] = {}
        for c in members:
            for d, v in (mkt.prem.get(c) or {}).items():
                by_date.setdefault(d, []).append((c, v))
        rows = [
            (d, max(v for _, v in lst) - min(v for _, v in lst),
             min(lst, key=lambda kv: kv[1])[0])
            for d, lst in sorted(by_date.items()) if len(lst) >= min_members
        ]
        if not rows:
            continue
        spreads = [s for _, s, _ in rows]
        cheapest_count: dict[str, int] = {}
        for _, _, c in rows:
            cheapest_count[c] = cheapest_count.get(c, 0) + 1
        out[g] = {
            "start": rows[0][0],
            "end": rows[-1][0],
            "n_days": len(rows),
            "median": statistics.median(spreads),
            "p90": _pct(spreads, 0.90),
            "max": max(spreads),
            "cheapest_share": sorted(
                ({"code": c, "days": n, "share": n / len(rows)}
                 for c, n in cheapest_count.items()),
                key=lambda x: -x["days"],
            ),
        }
    return out


def tracking_quality(mkt: Market, codes: list[str], names: dict[str, str],
                     groups: dict[str, str], fees: dict[str, float]) -> dict:
    """净值口径年化 vs 美元基准×汇率年化：差额里有费率、股息税、现金拖累与跟踪误差

    分两种口径。各自全历史只能看"这只基金历史上做得怎么样"；要横向排名必须用
    同一段区间，否则 2013 年上市的和 2023 年上市的在比不同的市场。
    """
    full = []
    for c in codes:
        acc = mkt.acc.get(c) or {}
        if len(acc) < 250:
            continue
        days = sorted(acc)
        row = _track_row(mkt, c, names.get(c, c), groups.get(c, ""),
                         fees.get(c, float("nan")), days[0], days[-1])
        if row:
            full.append(row)

    common: dict[str, dict] = {}
    for g in ("纳指100", "标普500"):
        members = [c for c in codes if groups.get(c) == g and mkt.acc.get(c)]
        if len(members) < 2:
            continue
        d0 = max(sorted(mkt.acc[c])[0] for c in members)
        d1 = min(sorted(mkt.acc[c])[-1] for c in members)
        rows = [
            r for c in members
            if (r := _track_row(mkt, c, names.get(c, c), g,
                                fees.get(c, float("nan")), d0, d1))
        ]
        if rows:
            common[g] = {
                "start": d0, "end": d1,
                "years": rows[0]["years"],
                "rows": sorted(rows, key=lambda r: -r["gap"]),
            }
    return {"full": sorted(full, key=lambda r: -r["gap"]), "common": common}


_SORTED_KEYS: dict[int, tuple[dict, list[str]]] = {}


def _last_val(series: dict[str, float], d: str) -> float | None:
    """最近一个 ≤ d 的值。序列建好后不再变动，故缓存排好序的键。"""
    if not series:
        return None
    if d in series:
        return series[d]
    entry = _SORTED_KEYS.get(id(series))
    if entry is None or entry[0] is not series:
        entry = (series, sorted(series))
        _SORTED_KEYS[id(series)] = entry
    days = entry[1]
    i = _bisect_right(days, d)
    return series[days[i - 1]] if i else None


# ============================================================================
# 报告
# ============================================================================
def print_timing(title: str, rows: list[dict]) -> None:
    base = next((r for r in rows if r["id"] == "T0"), rows[0])
    print("=" * 118)
    print(title)
    print("=" * 118)
    print(f"  {'':3s} {'策略':22s} {'终值':>9s} {'倍数':>6s} {'IRR':>8s} "
          f"{'vs定投':>8s} {'策略回撤':>8s} {'闲置现金':>8s} {'买入溢价':>8s} "
          f"{'换手':>6s} {'买/卖':>8s}")
    print("  " + "-" * 114)
    for r in rows:
        rel = r["final"] / base["final"] - 1
        print(f"  {r['id']:3s} {r['name']:22s} {r['final']/1e4:8.1f}万 "
              f"{r['multiple']:6.3f} {r['irr']:8.2%} {rel:+8.2%} "
              f"{r['nav_max_dd']:8.1%} {r['idle_mean']:8.1%} "
              f"{r['prem_paid_pct']:8.2%} {r['turnover']:6.2f} "
              f"{r['n_buys']:4d}/{r['n_sells']:<3d}")
    print("  「买入溢价」= 每 100 元买入里为溢价多付的钱；「换手」= 累计买入额 ÷ 累计入账额")
    print()
    for r in rows:
        print(f"      {r['id']} {r['name']}：{r['note']}")
    print()


def print_rolling(title: str, roll: dict) -> None:
    if not roll:
        return
    print("=" * 118)
    print(title)
    print(f"  {roll['n_windows']} 个滚动 {roll['span_months'] // 12} 年窗口，"
          f"起点 {roll['first_start']} → {roll['last_start']}")
    print("=" * 118)
    print(f"  {'':3s} {'策略':22s} {'IRR最差':>9s} {'P25':>9s} {'中位':>9s} "
          f"{'P75':>9s} {'最好':>9s} {'平均超额':>9s} {'跑赢定投':>9s}")
    print("  " + "-" * 114)
    for sid, s in roll["stats"].items():
        print(f"  {sid:3s} {s['name']:22s} {s['min']:9.2%} {s['p25']:9.2%} "
              f"{s['median']:9.2%} {s['p75']:9.2%} {s['max']:9.2%} "
              f"{s['mean_gap']:+9.2%} {s['beat_base']:9.1%}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="QDII 量化策略回测")
    ap.add_argument("--json", default="", help="结果写出到 JSON")
    ap.add_argument("--monthly", type=float, default=MONTHLY)
    args = ap.parse_args()

    cfg = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    items = cfg["items"]
    codes = [str(it["code"]) for it in items]
    names = {str(it["code"]): it["name"] for it in items}
    groups = {str(it["code"]): it["group"] for it in items}
    fees = {
        str(it["code"]): float(it.get("fee_mgmt_pct") or 0)
        + float(it.get("fee_custody_pct") or 0)
        for it in items
    }

    mkt = Market(codes, [DIVIDEND])

    # ---- 数据总览 ----
    print("=" * 112)
    print("① 数据总览（后复权成交价 / 单位净值 / 累计净值）")
    print("=" * 112)
    ready: list[str] = []
    for c in codes:
        adj, prem, acc = mkt.adj[c], mkt.prem[c], mkt.acc[c]
        if not adj or not prem:
            print(f"  {c} {names[c]:20s} 数据缺失（价格 {len(adj)} / 溢价 {len(prem)}）")
            continue
        ready.append(c)
        d = sorted(adj)
        print(f"  {c} {names[c]:20s} {groups[c]:7s} 价格 {len(adj):5d}天 {d[0]}→{d[-1]}"
              f"  溢价 {len(prem):5d}天  累计净值 {len(acc):5d}天  合计费率 {fees[c]:.2f}%")

    # ---- ② 溢价分布 ----
    pstats = premium_stats(mkt, ready, names)
    print()
    print("=" * 112)
    print("② 历史溢价分布（日频，=不复权收盘/单位净值−1，剔除份额折算错位）")
    print("=" * 112)
    print(f"  {'代码':7s} {'名称':20s} {'天数':>5s} {'中位':>7s} {'均值':>7s} "
          f"{'P10':>7s} {'P90':>7s} {'最大':>7s} {'<2%占比':>8s} {'>5%占比':>8s} {'波动':>7s}")
    for r in sorted(pstats, key=lambda x: x["median"]):
        print(f"  {r['code']:7s} {r['name']:20s} {r['n']:5d} {r['median']:7.2%} "
              f"{r['mean']:7.2%} {r['p10']:7.2%} {r['p90']:7.2%} {r['max']:7.2%} "
              f"{r['share_lt2']:8.1%} {r['share_gt5']:8.1%} {r['vol']:7.2%}")

    spread = premium_spread(mkt, ready, groups)
    if spread:
        print()
        print("  同一天同组「最贵 − 最便宜」的溢价差（比价最多能省多少）")
        for g, s in spread.items():
            top = "、".join(
                f"{x['code']} {x['share']:.0%}" for x in s["cheapest_share"][:3]
            )
            print(f"    {g}：{s['start']}→{s['end']} 共 {s['n_days']} 天，"
                  f"中位 {s['median']:.2%}、P90 {s['p90']:.2%}、最大 {s['max']:.2%}"
                  f"；最常最便宜：{top}")

    # ---- ③ 溢价证据 ----
    ev = premium_evidence(mkt, ready)
    print()
    print("=" * 112)
    print("③ 溢价到底值多少钱：按买入日溢价分档，未来 N 日「市价收益 − 净值收益」")
    print("   （净值收益与买点无关，所以这个差额就是溢价回归带来的损益）")
    print("=" * 112)
    print(f"  {'溢价档':12s}" + "".join(f"{'N='+h:>26s}" for h in ev))
    print(f"  {'':12s}" + "".join(f"{'均值':>9s}{'中位':>9s}{'胜率':>8s}" for _ in ev))
    for label in ("折价 <0%", "0~1%", "1~2%", "2~5%", ">5%"):
        line = f"  {label:12s}"
        for h in ev:
            b = ev[h][label]
            line += f"{b['mean']:9.2%}{b['median']:9.2%}{b['win']:8.1%}" \
                if b["n"] else f"{'—':>9s}{'—':>9s}{'—':>8s}"
        print(line)
    print("  样本量：" + "  ".join(
        f"N={h}: " + "/".join(str(ev[h][l]["n"]) for l in ("折价 <0%", "0~1%", "1~2%", "2~5%", ">5%"))
        for h in ev
    ))

    # ---- ④ 跟踪质量 ----
    trk = tracking_quality(mkt, ready, names, groups, fees)
    print()
    print("=" * 118)
    print("④ 跟踪质量：基金净值年化 vs 美元基准×汇率年化（差额含费率、股息税、现金拖累）")
    print("=" * 118)
    for g, blk in trk["common"].items():
        print(f"  【{g}】同一区间横向可比：{blk['start']}→{blk['end']}（{blk['years']:.1f} 年）")
        print(f"    {'代码':7s} {'名称':20s} {'净值年化':>9s} {'基准年化':>9s} "
              f"{'差额':>8s} {'费率':>6s} {'费率解释了多少':>14s}")
        for r in blk["rows"]:
            expl = -r["fee"] / 100 / r["gap"] if r["gap"] < 0 else float("nan")
            expl_s = f"{expl:13.0%}" if not math.isnan(expl) else f"{'—':>13s}"
            print(f"    {r['code']:7s} {r['name']:20s} {r['fund_cagr']:9.2%} "
                  f"{r['bench_cagr']:9.2%} {r['gap']:+8.2%} {r['fee']:5.2f}% {expl_s}")
        print()
    print("  各自全历史（区间不同，只能纵向看，不能横向排名）")
    print(f"    {'代码':7s} {'名称':20s} {'区间':>23s} {'年':>5s} {'净值年化':>9s} "
          f"{'基准年化':>9s} {'差额':>8s} {'费率':>6s}")
    for r in trk["full"]:
        print(f"    {r['code']:7s} {r['name']:20s} {r['start']}→{r['end']} {r['years']:5.1f} "
              f"{r['fund_cagr']:9.2%} {r['bench_cagr']:9.2%} {r['gap']:+8.2%} {r['fee']:5.2f}%")

    # ---- ⑤ 择时层 ----
    timing_out: dict[str, dict] = {}
    for group, primary in (("纳指100", "513100"), ("标普500", "513500")):
        if primary not in ready:
            continue
        days = [d for d in mkt.adj_days[primary]]
        # 起点：主标的与替代标的都有价格，且从首个完整月开始
        d0 = max(days[0], sorted(mkt.adj[DIVIDEND])[0])
        days = [d for d in days if d >= d0][1:]
        if len(days) < 500:
            continue
        rules = make_timing_rules(primary, DIVIDEND)
        rows = []
        for spec in rules:
            res = run_strategy(mkt, spec["rule"], days, primary, group, args.monthly)
            rows.append({**{k: v for k, v in spec.items() if k != "rule"}, **res})
        print()
        print_timing(
            f"⑤ 择时层 · {group}（主标的 {primary} {names[primary]}，"
            f"{days[0]}→{days[-1]}，每月入账 {args.monthly:,.0f} 元，闲置现金按 {CASH_RATE:.1%} 计息）",
            rows,
        )
        roll = rolling_analysis(mkt, rules, days, primary, group, args.monthly, 36)
        print_rolling(f"   稳健性检验 · {group}：换个起点结论还成立吗", roll)

        timing_out[group] = {
            "primary": primary,
            "primary_name": names[primary],
            "alt": DIVIDEND,
            "start": days[0],
            "end": days[-1],
            "rows": [{k: v for k, v in r.items() if k != "curve"} for r in rows],
            "curves": {
                r["id"]: [[d, round(v)] for d, v in r["curve"][::10]] for r in rows
            },
            "rolling": roll,
        }

    # ---- ⑥ 选券层 ----
    picking_out: dict[str, dict] = {}
    for group in ("纳指100", "标普500"):
        members = [c for c in ready if groups[c] == group]
        if len(members) < 2:
            continue
        # 全员齐备之后才公平：起点取最晚上市那只的首日
        starts = [sorted(mkt.adj[c])[0] for c in members]
        d0 = max(starts)
        base_days = sorted(mkt.adj[members[0]])
        days = [d for d in base_days if d >= d0]
        if len(days) < 250:
            continue
        rules = make_picking_rules(members, fees)
        rows = []
        for spec in rules:
            res = run_strategy(mkt, spec["rule"], days, members[0], group, args.monthly)
            rows.append({**{k: v for k, v in spec.items() if k != "rule"}, **res})
        base = rows[0]
        years = (_to_date(days[-1]) - _to_date(days[0])).days / 365.25
        print()
        print("=" * 118)
        print(f"⑥ 选券层 · {group}（{len(members)} 只全员齐备后：{days[0]}→{days[-1]}，"
              f"仅 {years:.1f} 年，每月 {args.monthly:,.0f} 元）")
        print("=" * 118)
        print(f"  {'':3s} {'规则':32s} {'终值':>9s} {'IRR':>8s} {'vs老牌':>8s} "
              f"{'买入溢价':>8s} {'成本':>7s}  {'钱主要去了哪':<28s}")
        for r in rows:
            rel = r["final"] / base["final"] - 1
            top = sorted(r["bought"].items(), key=lambda kv: -kv[1])[:3]
            flow = " ".join(
                f"{c}{v / sum(r['bought'].values()):.0%}" for c, v in top
            )
            print(f"  {r['id']:3s} {r['name']:32s} {r['final']/1e4:8.2f}万 {r['irr']:8.2%} "
                  f"{rel:+8.2%} {r['prem_paid_pct']:8.2%} {r['cost_paid']:7.0f}  {flow:<28s}")

        roll_pick = rolling_analysis(
            mkt, rules, days, members[0], group, args.monthly, 12, base_id="C0"
        )
        print_rolling(f"   稳健性检验 · {group} 选券（窗口短、样本弱，仅供参考）", roll_pick)

        picking_out[group] = {
            "members": members,
            "start": days[0],
            "end": days[-1],
            "years": years,
            "rows": [{k: v for k, v in r.items() if k != "curve"} for r in rows],
            "rolling": roll_pick,
        }

    if args.json:
        out = {
            "title": "场内 QDII 量化策略回测",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "params": {
                "monthly": args.monthly,
                "cash_rate": CASH_RATE,
                "trade_cost": TRADE_COST,
                "prem_window": PREM_WINDOW,
                "dividend_alt": DIVIDEND,
            },
            "universe": [
                {"code": c, "name": names[c], "group": groups[c], "fee": fees[c]}
                for c in ready
            ],
            "premium_stats": pstats,
            "premium_spread": spread,
            "premium_evidence": ev,
            "tracking": trk,
            "timing": timing_out,
            "picking": picking_out,
        }
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON → {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
