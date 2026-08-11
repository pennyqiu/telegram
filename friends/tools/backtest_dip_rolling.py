#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回撤阶梯 vs 定投：现金流感知 + 多起点滚动回测。

为什么要重写 backtest_us_dip.py
------------------------------
旧脚本有四个会让结论失真的问题，本脚本逐条修：

1) **ATH 预热偏差**：旧脚本 `ath = prices[0]`，把序列第一天当历史最高。
   SPY 序列从 2001-01 开始，而真实前高在 2000-03（≈152.6），
   即序列开头其实已经 −15%，旧算法却认为在新高 → 早期阶梯全部假触发。
   本脚本用**文档化的样本前 ATH 常数**播种（见 SEED_ATH），或用 --warmup-years 丢弃预热段。

2) **现金零利息**：旧脚本未触发的钱按 0 收益算，低估了"空等"的机会成本。
   本脚本给未投入现金计息（--cash-yield），并做 0%/2%/4% 敏感性。

3) **长期水下 re-arm 失效**：只有创新高才重装阶梯。若遇 2000–2013 这种十几年
   水下，三档打完就再无子弹，而那恰是最该持续买入的时期。
   本脚本增加**时间再装填**：水下满 N 个月自动补一档（--rearm-months）。

4) **单起点回测 = 过拟合温床**：旧脚本从今天往回切 5/10/15/20 年，只有一个起点，
   且必然包含美股大牛市。本脚本跑**所有可能的起始月份**，报告分布
   （中位数 / P10 / 最差）与"跑输基线的概率与幅度"。

另外两条与你目标对齐的改动
--------------------------
- **目标函数不是夏普**：你是股息永续、本金永不卖，所以任何"卖出信号"都不该进策略。
  择时只用于决定新钱何时进、进多少。因此主指标是
  **加权平均成本 vs 同期均价**、**跑输一次性买入的概率与幅度(regret)**、
  最大回撤与最长水下时间，而不是波动率调整后收益。
- **必须有定投对照**：很多策略赢了"空仓"却输给定投。本脚本把定投设为基线，
  策略要打败的是它，不是"不投资"。

四个对照策略
------------
  S1 全额立投   ：期初一次性买入，之后每月新钱立即买入（现金≈0）
  S2 12个月分批 ：期初资金分 12 个月摊平，之后每月新钱立即买入
  S3 纯阶梯     ：期初资金全部作为干粮，按回撤阶梯投放；每月新钱也进干粮池
  S4 定投+阶梯  ：每月新钱立即买入（基线定投），期初资金作为干粮按阶梯加仓

数据源与口径限制（重要，请连同结论一起读）
------------------------------------------
  价格：新浪 US_MinKService 日线，**不复权**。
        股息用参数化年化股息率按季度模拟并再投（--div-yield），
        这样能把"价格回报"和"股息回报"分开归因。
  SPY  ：2001-01 ~ 今，完整（含 2001–02 与 2008 两次大熊）
  .IXIC：2004-01 ~ 今，完整（纳指综指，作为纳指100的代理；相关性极高但非同一指数）
  QQQ  ：**该源缺 2005–2010 整段，不可用于回测**（已在报告中标注）
  ⚠️ 全样本都不含 2000-03~2002-10 的完整互联网泡沫破裂。
     对一个"越跌越买"的策略来说，**样本里缺了纳指历史上最惨的那次下跌**，
     所以最差情形一定比回测显示的更差。

用法
----
  python backtest_dip_rolling.py
  python backtest_dip_rolling.py --symbol SPY --cash-yield 4
  python backtest_dip_rolling.py --symbol .IXIC --report r.txt --json r.json

仅供研究，非投资建议。
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
LADDER_FILE = TOOLS_DIR / "us_dip_watchlist.json"
CACHE_DIR = TOOLS_DIR / ".bt_cache" / "dip_rolling"
CACHE_TTL = 12 * 3600

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://finance.sina.com.cn/"}

# 样本前的真实历史最高收盘，用于播种 ATH，避免"把序列第一天当新高"。
# 数值为该标的在样本开始之前已经创下的最高收盘价（不复权口径，公开可查）。
SEED_ATH: dict[str, dict[str, Any]] = {
    "SPY":   {"ath": 152.65, "date": "2000-03-24", "note": "互联网泡沫顶，SPY 不复权收盘"},
    ".IXIC": {"ath": 5048.62, "date": "2000-03-10", "note": "纳斯达克综指历史顶（2015 年才收复）"},
    ".INX":  {"ath": 1527.46, "date": "2000-03-24", "note": "标普500 指数 2000 年顶"},
}

# 各标的的长期平均年化股息率（价格序列不复权，用它把股息补回来）
DIV_YIELD: dict[str, float] = {"SPY": 1.8, ".INX": 1.8, ".IXIC": 0.9, "QQQ": 0.6}

# 分组映射：决定用哪套阶梯
GROUP_OF: dict[str, str] = {"SPY": "标普500", ".INX": "标普500", ".IXIC": "纳指100", "QQQ": "纳指100"}


# ---------------------------------------------------------------- 工具
def _get(url: str, tries: int = 4, timeout: int = 40) -> str:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"请求失败 {url} ({last})")


def _cache(name: str, producer, ttl: int = CACHE_TTL):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / name
    if p.exists() and time.time() - p.stat().st_mtime < ttl:
        return json.loads(p.read_text(encoding="utf-8"))
    val = producer()
    p.write_text(json.dumps(val, ensure_ascii=False), encoding="utf-8")
    return val


class Tee:
    def __init__(self, path: Path | None):
        self.f = path.open("w", encoding="utf-8") if path else None

    def __call__(self, *parts: Any, **_: Any) -> None:
        line = " ".join(str(p) for p in parts)
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            print(line.encode("ascii", "replace").decode(), flush=True)
        if self.f:
            self.f.write(line + "\n")
            self.f.flush()

    def close(self) -> None:
        if self.f:
            self.f.close()


def irr(flows: list[tuple[float, float]], final: float, years: float) -> float:
    """资金加权年化收益率（IRR）。

    flows = [(t年, 投入额), ...]（正数=投入），final = 期末市值。
    直接用 (终值/总投入)^(1/年) 会低估：后期投入的钱并没有享受完整年限。
    """
    def npv(r: float) -> float:
        v = -final / ((1 + r) ** years)
        for t, amt in flows:
            v += amt / ((1 + r) ** t)
        return v

    lo, hi = -0.95, 2.0
    if npv(lo) * npv(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2 * 100


def pct_of(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def fetch_daily(symbol: str) -> list[tuple[str, float]]:
    """新浪美股/指数日线 → [(date, close)]，按日期升序。"""
    def _fetch():
        url = ("https://stock.finance.sina.com.cn/usstock/api/json_v2.php/"
               "US_MinKService.getDailyK?symbol=" + urllib.parse.quote(symbol))
        text = _get(url)
        i = text.find("[")
        rows = json.loads(text[i:]) if i >= 0 else []
        out = []
        for r in rows:
            d, c = str(r.get("d") or "")[:10], r.get("c")
            if d and c not in (None, ""):
                out.append((d, float(c)))
        out.sort()
        return out

    return [(d, float(c)) for d, c in _cache(f"px_{symbol.replace('.', '_')}.json", _fetch)]


def check_gaps(series: list[tuple[str, float]]) -> list[str]:
    """按年样本数检查缺口，返回缺失或样本明显不足的年份。"""
    cnt: dict[str, int] = {}
    for d, _ in series:
        cnt[d[:4]] = cnt.get(d[:4], 0) + 1
    yrs = sorted(cnt)
    bad = []
    for y in range(int(yrs[0]), int(yrs[-1]) + 1):
        n = cnt.get(str(y), 0)
        if n == 0:
            bad.append(f"{y}(缺失)")
        elif n < 200 and str(y) not in (yrs[0], yrs[-1]):
            bad.append(f"{y}({n}天)")
    return bad


# ---------------------------------------------------------------- 模拟器
class Sim:
    """现金流感知的模拟器。

    每个交易日：
      - 价格变动
      - 到月初：注入新钱（contribution）
      - 到季度：按年化股息率派息并再投（份额增加）
      - 现金按日计息
      - 策略决定今天买多少
    单位统一为"元"，份额为浮点。
    """

    def __init__(self, prices: list[tuple[str, float]], *, initial: float, monthly: float,
                 div_yield_pct: float, cash_yield_pct: float, expense_pct: float):
        self.prices = prices
        self.initial = initial
        self.monthly = monthly
        self.div_d = div_yield_pct / 100.0 / 4.0          # 每季度派息率
        self.cash_d = (1 + cash_yield_pct / 100.0) ** (1 / 252.0) - 1
        self.exp_d = (expense_pct / 100.0) / 252.0        # ETF 费率按日扣
        # 截至第 i 天之前的历史最高收盘（point-in-time，用于正确初始化 ATH）
        self.runmax: list[float] = []
        m = 0.0
        for _, px in prices:
            self.runmax.append(m)
            m = max(m, px)

    def initial_ath(self, i0: int) -> float:
        """窗口开始时应当已知的历史最高价。

        'pit'（默认）= max(样本前ATH, 样本内 i0 之前的最高收盘) —— 正确口径
        'window'     = 窗口首日价格 —— 复现旧脚本的预热偏差
        """
        if self.ath_mode == "window":
            return self.prices[i0][1]
        return max(self.seed_ath, self.runmax[i0])

    def run(self, strategy, i0: int, i1: int) -> dict[str, Any]:
        """strategy(ctx) -> 今日要投入的现金额（元）。区间为 prices[i0:i1]。"""
        cash = self.initial
        shares = 0.0
        invested = 0.0          # 累计买入金额（用于加权平均成本）
        cost_shares = 0.0       # 累计买入份额
        contributed = self.initial
        flows: list[tuple[float, float]] = [(0.0, self.initial)]
        ath = self.initial_ath(i0)
        peak_value = 0.0
        max_dd = 0.0
        longest_uw = 0
        uw_run = 0
        pf_uw_run = 0        # 组合价值低于自身峰值的连续天数
        pf_longest_uw = 0
        px_sum = 0.0
        px_n = 0
        cur_month = self.prices[i0][0][:7]
        cur_q = None
        rearm_count = 0
        tiers_done: set[int] = set()

        for i in range(i0, i1):
            d, px = self.prices[i]
            px_sum += px
            px_n += 1

            # 现金计息
            cash *= (1 + self.cash_d)
            # ETF 费率
            shares *= (1 - self.exp_d)

            # 月初注入新钱
            if d[:7] != cur_month:
                cur_month = d[:7]
                cash += self.monthly
                contributed += self.monthly
                flows.append(((i - i0) / 252.0, self.monthly))

            # 季度派息再投（不复权价格序列，用参数化股息补回）
            q = (d[:4], (int(d[5:7]) - 1) // 3)
            if cur_q is None:
                cur_q = q
            elif q != cur_q:
                cur_q = q
                if shares > 0 and self.div_d > 0:
                    shares += shares * self.div_d      # 股息全额再投

            # ATH 与回撤
            if px > ath:
                ath = px
                if tiers_done:
                    tiers_done = set()
                    rearm_count += 1
                uw_run = 0
            else:
                uw_run += 1
                longest_uw = max(longest_uw, uw_run)
            dd = (px / ath - 1.0) * 100.0 if ath > 0 else 0.0

            # 策略下单
            ctx = {"i": i, "date": d, "px": px, "cash": cash, "dd": dd, "ath": ath,
                   "tiers_done": tiers_done, "underwater_days": uw_run,
                   "i0": i0, "sim": self}
            buy = strategy(ctx)
            buy = max(0.0, min(buy, cash))
            if buy > 0:
                sh = buy / px
                shares += sh
                cost_shares += sh
                invested += buy
                cash -= buy

            # 组合净值与回撤（组合层面，与"价格水下"不同：有新钱流入会更快回到峰值）
            val = shares * px + cash
            if val >= peak_value:
                peak_value = val
                pf_uw_run = 0
            else:
                pf_uw_run += 1
                pf_longest_uw = max(pf_longest_uw, pf_uw_run)
            if peak_value > 0:
                max_dd = min(max_dd, (val / peak_value - 1.0) * 100.0)

        d_end, px_end = self.prices[i1 - 1]
        final = shares * px_end + cash
        years = (i1 - i0) / 252.0
        avg_cost = invested / cost_shares if cost_shares > 0 else float("nan")
        avg_px = px_sum / px_n if px_n else float("nan")
        money_irr = irr(flows, final, years) if years > 0 else float("nan")
        return {
            "start": self.prices[i0][0], "end": d_end, "years": round(years, 2),
            "contributed": contributed, "invested": invested, "final": final,
            "shares": shares, "cash_left": cash,
            "cash_pct_end": cash / final * 100 if final > 0 else 0.0,
            "avg_cost": avg_cost, "avg_px": avg_px,
            "cost_edge_pct": (avg_px / avg_cost - 1) * 100 if avg_cost and avg_cost == avg_cost else float("nan"),
            "money_multiple": final / contributed if contributed else float("nan"),
            "irr_pct": money_irr,
            "max_dd": max_dd, "longest_uw_days": longest_uw,
            "pf_longest_uw_days": pf_longest_uw,
            "rearm_count": rearm_count,
        }

    seed_ath = 0.0
    seed_ath_date = ""
    ath_mode = "pit"


# ---------------------------------------------------------------- 策略
def strat_lump(ctx) -> float:
    """S1 全额立投：手上有钱就买。"""
    return ctx["cash"]


def make_strat_spread(months: int):
    """S2 期初资金分 N 个月摊平；新钱立即买入。
    实现：每月投入「期初资金/N」+ 当月新钱；月内只在首个交易日下单。
    """
    state: dict[str, Any] = {}

    def f(ctx) -> float:
        sim: Sim = ctx["sim"]
        if ctx["i"] == ctx["i0"]:
            state["tranche"] = sim.initial / months
            state["left"] = months
            state["month"] = None
        m = ctx["date"][:7]
        if state.get("month") == m:
            return 0.0
        state["month"] = m
        amt = sim.monthly
        if state["left"] > 0:
            amt += state["tranche"]
            state["left"] -= 1
        return amt

    return f


def make_strat_ladder(ladder: list[dict[str, float]], *, rearm_months: int, dca_monthly: bool):
    """S3/S4 回撤阶梯。

    ladder: [{"drop":8,"buy":30}, ...] buy 为阶梯的相对权重。

    投放基数用「当前干粮余额」而非固定的期初金额：
    第 k 档投放 cash × buy_k / (尚未触发档位的 buy 之和)。
    这样最后一档必然把干粮清空，且持续流入的新钱不会被永久搁死
    （固定基数会导致后来的新钱永远投不出去，那是建模artifact，不是策略）。

    rearm_months: 水下满 N 个月自动补装一档（修长期水下失效）。0 = 关闭。
    dca_monthly: True → 每月新钱立即买入（S4 定投+阶梯）；False → 新钱进干粮池（S3 纯阶梯）。
    """
    state: dict[str, Any] = {}

    def f(ctx) -> float:
        sim: Sim = ctx["sim"]
        if ctx["i"] == ctx["i0"]:
            state["month"] = ctx["date"][:7]
            state["last_rearm_day"] = 0
        buy = 0.0

        # S4：每月新钱立即买入，不参与择时
        if dca_monthly and ctx["date"][:7] != state["month"]:
            state["month"] = ctx["date"][:7]
            buy += min(sim.monthly, ctx["cash"])
        elif not dca_monthly:
            state["month"] = ctx["date"][:7]

        # 时间再装填：水下满 N 个月，清掉一档已用记录，允许再买一次
        if rearm_months > 0 and ctx["tiers_done"]:
            uw = ctx["underwater_days"]
            need = state["last_rearm_day"] + rearm_months * 21
            if uw >= need:
                state["last_rearm_day"] = uw
                ctx["tiers_done"].discard(max(ctx["tiers_done"]))

        # 回撤阶梯：按当前干粮余额归一化投放
        dd = ctx["dd"]
        avail = max(0.0, ctx["cash"] - buy)
        done = ctx["tiers_done"]
        for k, tier in enumerate(ladder):
            if k in done:
                continue
            if dd <= -float(tier["drop"]):
                denom = sum(float(ladder[j]["buy"]) for j in range(len(ladder)) if j not in done)
                amt = avail * float(tier["buy"]) / denom if denom > 0 else avail
                done.add(k)
                buy += amt
                avail -= amt
        return buy

    return f


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="回撤阶梯 vs 定投：现金流感知 + 多起点滚动回测")
    ap.add_argument("--symbol", default="SPY", help="SPY / .IXIC / .INX")
    ap.add_argument("--initial", type=float, default=100.0, help="期初资金（单位任意，默认100）")
    ap.add_argument("--monthly", type=float, default=1.0, help="每月新钱（相对期初的比例感，默认1）")
    ap.add_argument("--cash-yield", type=float, default=2.0, help="未投入现金年化收益%%")
    ap.add_argument("--expense", type=float, default=0.09, help="ETF 年费率%%")
    ap.add_argument("--div-yield", type=float, default=-1.0, help="年化股息率%%，-1=用内置默认")
    ap.add_argument("--rearm-months", type=int, default=12, help="水下满N个月补一档，0=关闭")
    ap.add_argument("--window-years", type=float, default=10.0, help="每次滚动的持有年数")
    ap.add_argument("--warmup-years", type=float, default=0.0, help="丢弃序列开头N年")
    ap.add_argument("--no-seed-ath", action="store_true", help="不用样本前ATH常数")
    ap.add_argument("--ath-mode", choices=["pit", "window"], default="pit",
                    help="pit=point-in-time正确口径；window=复现旧脚本「窗口首日当新高」的偏差")
    ap.add_argument("--report", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    say = Tee(Path(args.report) if args.report else None)
    sym = args.symbol
    div_y = DIV_YIELD.get(sym, 1.5) if args.div_yield < 0 else args.div_yield
    group = GROUP_OF.get(sym, "标普500")
    ladder = json.loads(LADDER_FILE.read_text(encoding="utf-8"))["groups"][group]["ladder"]

    series = fetch_daily(sym)
    if args.warmup_years > 0:
        cut = int(args.warmup_years * 252)
        series = series[cut:]
    gaps = check_gaps(series)

    say("=" * 100)
    say(f"标的 {sym} · 分组 {group} · 阶梯 {[(t['drop'], t['buy']) for t in ladder]}")
    say(f"样本 {series[0][0]} ~ {series[-1][0]}（{len(series)} 个交易日 ≈ {len(series)/252:.1f} 年）")
    say(f"参数：期初 {args.initial} · 每月新钱 {args.monthly} · 现金年化 {args.cash_yield}% · "
        f"股息年化 {div_y}% · ETF费率 {args.expense}% · 时间再装填 {args.rearm_months} 个月")
    say(f"      {args.window_years:g} 年内新钱累计 = 期初的 "
        f"{args.monthly * 12 * args.window_years / args.initial:.2f} 倍"
        f"（新钱越多，期初那笔干粮的择时越不重要）")
    if gaps:
        say(f"⚠️ 数据缺口：{', '.join(gaps)} —— 该标的不适合直接回测")
    seed = SEED_ATH.get(sym)
    say(f"ATH 口径：{args.ath_mode}"
        + ("（每个窗口用「样本前ATH 与 起点之前的最高收盘」的较大值）" if args.ath_mode == "pit"
           else "（窗口首日当作历史新高 —— 旧脚本的偏差，仅用于对比）"))
    if seed and not args.no_seed_ath:
        say(f"样本前 ATH 播种：{seed['ath']}（{seed['date']}，{seed['note']}）"
            f" → 样本首日回撤 {(series[0][1]/seed['ath']-1)*100:+.1f}%")
    else:
        say("样本前 ATH 播种：关闭")
    say("=" * 100)

    sim = Sim(series, initial=args.initial, monthly=args.monthly, div_yield_pct=div_y,
              cash_yield_pct=args.cash_yield, expense_pct=args.expense)
    sim.seed_ath = 0.0 if (args.no_seed_ath or not seed) else float(seed["ath"])
    sim.seed_ath_date = "" if sim.seed_ath == 0 else str(seed["date"])
    sim.ath_mode = args.ath_mode

    strategies = {
        "S1 全额立投": strat_lump,
        "S2 12月摊平": make_strat_spread(12),
        "S3 纯阶梯": make_strat_ladder(ladder, rearm_months=args.rearm_months, dca_monthly=False),
        "S4 定投+阶梯": make_strat_ladder(ladder, rearm_months=args.rearm_months, dca_monthly=True),
    }

    # 多起点滚动：每个月初一个起点
    win = int(args.window_years * 252)
    starts: list[int] = []
    seen: set[str] = set()
    for i, (d, _) in enumerate(series):
        if i + win >= len(series):
            break
        if d[:7] not in seen:
            seen.add(d[:7])
            starts.append(i)
    if not starts:
        say("样本不足，无法做滚动回测")
        say.close()
        return 1

    say(f"\n滚动回测：{len(starts)} 个起点（每月一个）× {args.window_years:g} 年持有期"
        f" · 覆盖起点 {series[starts[0]][0]} ~ {series[starts[-1]][0]}")

    results: dict[str, list[dict[str, Any]]] = {k: [] for k in strategies}
    for i0 in starts:
        for name, st in strategies.items():
            results[name].append(sim.run(st, i0, i0 + win))

    # ------------- 报告：起点状态（解释为什么阶梯常常"没机会择时"）
    say("\n" + "=" * 100)
    say("零、起点时市场已经在水下多深？（决定阶梯有没有择时的机会）")
    say("-" * 100)
    dd0s = [(series[i0][1] / sim.initial_ath(i0) - 1) * 100 for i0 in starts]
    first_drop = float(ladder[0]["drop"])
    last_drop = float(ladder[-1]["drop"])
    n_high = sum(1 for x in dd0s if x > -first_drop)
    n_all = sum(1 for x in dd0s if x <= -last_drop)
    sd0 = sorted(dd0s)
    say(f"  起点回撤分布：中位 {pct_of(sd0,50):.1f}% · P10 {pct_of(sd0,10):.1f}% · 最深 {sd0[0]:.1f}%")
    say(f"  在高点附近（回撤 > -{first_drop:g}%，一档都不触发）：{n_high}/{len(starts)}"
        f" = {n_high/len(starts)*100:.1f}%")
    say(f"  已跌破最深一档（回撤 ≤ -{last_drop:g}%，开局即全投）：{n_all}/{len(starts)}"
        f" = {n_all/len(starts)*100:.1f}%")
    same = sum(1 for a, b in zip(results["S4 定投+阶梯"], results["S1 全额立投"])
               if abs(a["final"] - b["final"]) < 1e-9)
    say(f"  → S4 与 S1 终值完全相同的窗口：{same}/{len(starts)} = {same/len(starts)*100:.1f}%"
        f"（这些窗口里阶梯根本没起作用）")

    # ------------- 报告：分布
    say("\n" + "=" * 100)
    say(f"一、终值分布（每投入 1 元最终变成多少元 · {args.window_years:g} 年持有）")
    say("-" * 100)
    say("  终值倍数 = 期末市值 / 累计投入；IRR = 资金加权年化收益率（已计入新钱进入的时点）")
    say("-" * 100)
    say(f"{'策略':<14}{'中位数':>9}{'P10':>9}{'最差':>9}{'P90':>9}{'最好':>9}"
        f"{'IRR中位%':>10}{'期末现金%':>10}")
    base = results["S1 全额立投"]
    for name in strategies:
        mm = sorted(r["money_multiple"] for r in results[name])
        cg = sorted(r["irr_pct"] for r in results[name] if r["irr_pct"] == r["irr_pct"])
        cashp = sum(r["cash_pct_end"] for r in results[name]) / len(results[name])
        say(f"{name:<14}{pct_of(mm,50):>9.3f}{pct_of(mm,10):>9.3f}{mm[0]:>9.3f}"
            f"{pct_of(mm,90):>9.3f}{mm[-1]:>9.3f}{pct_of(cg,50):>10.2f}{cashp:>10.1f}")

    # ------------- 报告：相对基线
    say("\n" + "=" * 100)
    say("二、相对 S1 全额立投（这才是该打败的对手，不是「不投资」）")
    say("-" * 100)
    say(f"{'策略':<14}{'跑赢概率':>10}{'中位超额%':>11}{'平均超额%':>11}"
        f"{'跑输时中位幅度%':>16}{'最惨跑输%':>11}")
    for name in strategies:
        if name == "S1 全额立投":
            continue
        rel = [(r["final"] / b["final"] - 1) * 100 for r, b in zip(results[name], base)]
        win_p = sum(1 for x in rel if x > 0) / len(rel) * 100
        lose = sorted(x for x in rel if x <= 0)
        srel = sorted(rel)
        say(f"{name:<14}{win_p:>9.1f}%{pct_of(srel,50):>11.2f}{sum(rel)/len(rel):>11.2f}"
            f"{(pct_of(lose,50) if lose else 0):>16.2f}{(lose[0] if lose else 0):>11.2f}")

    # ------------- 报告：买入价优势与风险
    say("\n" + "=" * 100)
    say("三、择时到底有没有买得更便宜？")
    say("-" * 100)
    say("  「vs同期均价」会被趋势污染：上涨市里\"早买\"天然显得便宜，不代表择时能力。")
    say("  真正隔离择时的是「vs S1 成本」——同一笔钱，等回撤买是否比立刻买更便宜。")
    say("-" * 100)
    say(f"{'策略':<14}{'vs同期均价%':>13}{'vs S1成本%':>12}{'vs S1 P10%':>12}"
        f"{'最大回撤中位%':>15}{'组合最长水下(月)':>17}{'再装填':>8}")
    for name in strategies:
        ce = sorted(r["cost_edge_pct"] for r in results[name] if r["cost_edge_pct"] == r["cost_edge_pct"])
        vs1 = sorted((b["avg_cost"] / r["avg_cost"] - 1) * 100
                     for r, b in zip(results[name], base)
                     if r["avg_cost"] and r["avg_cost"] == r["avg_cost"])
        dd = sorted(r["max_dd"] for r in results[name])
        uw = sorted(r["pf_longest_uw_days"] / 21.0 for r in results[name])
        ra = sum(r["rearm_count"] for r in results[name]) / len(results[name])
        say(f"{name:<14}{pct_of(ce,50):>13.2f}{pct_of(vs1,50):>12.2f}{pct_of(vs1,10):>12.2f}"
            f"{pct_of(dd,50):>15.2f}{pct_of(uw,50):>17.1f}{ra:>8.1f}")

    # ------------- 报告：最差起点
    say("\n" + "=" * 100)
    say("四、最差的 5 个起点（S4 定投+阶梯 的终值倍数排序）")
    say("-" * 100)
    say(f"{'起点':<12}{'终点':<12}{'S1':>8}{'S2':>8}{'S3':>8}{'S4':>8}{'S4最大回撤%':>13}")
    order = sorted(range(len(starts)), key=lambda k: results["S4 定投+阶梯"][k]["money_multiple"])
    for k in order[:5]:
        r4 = results["S4 定投+阶梯"][k]
        say(f"{r4['start']:<12}{r4['end']:<12}"
            f"{results['S1 全额立投'][k]['money_multiple']:>8.3f}"
            f"{results['S2 12月摊平'][k]['money_multiple']:>8.3f}"
            f"{results['S3 纯阶梯'][k]['money_multiple']:>8.3f}"
            f"{r4['money_multiple']:>8.3f}{r4['max_dd']:>13.2f}")

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": sym, "group": group, "ladder": ladder,
        "sample": {"start": series[0][0], "end": series[-1][0], "days": len(series), "gaps": gaps},
        "params": vars(args) | {"div_yield_used": div_y,
                                "seed_ath": sim.seed_ath, "seed_ath_date": sim.seed_ath_date},
        "n_starts": len(starts),
        "results": {k: v for k, v in results.items()},
    }
    path = Path(args.json) if args.json else (CACHE_DIR / f"rolling_{sym.replace('.','_')}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"\nJSON → {path}")
    if args.report:
        say(f"报告 → {args.report}")
    say.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
