#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大陆场内 ETF 定投策略历史回测。

数据：friends/tools/backtest_data/*.csv（由 fetch_backtest_data.py 抓取，前复权=分红再投）

三层口径：
  1) 真实 ETF 回测：直接用 510880 / 513100 / 513500 等场内成交价，
     溢价波动、汇率、跟踪误差、费率全部已包含在价格里。
  2) 长历史合成回测：大陆 QDII 上市前，用 QQQ/SPY(美元前复权) × USDCNY − 包装损耗
     补齐，把回测起点推到 2007 年（含 2008 年崩盘），以获得足够多的滚动 10 年窗口。
  3) 包装损耗（drag）由重叠期真实 QDII 与合成序列的差异校准得出，不靠拍脑袋。

策略机制：
  - 每月月末定额买入；按「补低配」方式分配新增资金
  - 每年 1 月 / 7 月检查，偏离目标 > 5pp 时全额再平衡（含交易成本）
  - 随年龄滑翔调整目标比例

用法：
  python3 friends/tools/backtest_cn_etf.py            # 完整报告
  python3 friends/tools/backtest_cn_etf.py --json out.json
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "backtest_data"

MONTHLY_CONTRIB = 100_000 / 12          # 每年 10 万，按月分摊
CONTRIB_MONTHS = 120                    # 投入期：40 岁起投满 10 年，投完正好 50 岁
HOLD_MONTHS = 120                       # 停投期：50 → 60 岁，再持有 10 年
TARGET_AGE_END = 60                     # 复利终点
START_AGE = 40
REBALANCE_MONTHS = (1, 7)               # 每年 1 月、7 月检查
REBALANCE_THRESHOLD = 0.05              # 偏离 5 个百分点才动
TRADE_COST = 0.0003                     # 再平衡换手成本（佣金+冲击，单边）


# ----------------------------------------------------------------------------
# 数据装载
# ----------------------------------------------------------------------------
def load_series(name: str) -> dict[str, float]:
    """读 CSV → {YYYY-MM-DD: close}"""
    path = DATA_DIR / f"{name}.csv"
    out: dict[str, float] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[row["date"]] = float(row["close"])
    return out


def to_month_end(daily: dict[str, float]) -> dict[str, float]:
    """日线 → 月末值 {YYYY-MM: close}（取该月最后一个交易日）"""
    out: dict[str, float] = {}
    for day in sorted(daily):
        out[day[:7]] = daily[day]
    return out


def month_range(start: str, end: str) -> list[str]:
    """生成 [start..end] 的 YYYY-MM 列表（含端点）"""
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def returns_from_levels(levels: dict[str, float], months: list[str]) -> dict[str, float]:
    """月末净值 → 月度收益率 {YYYY-MM: r}（r 为该月的收益）"""
    out: dict[str, float] = {}
    prev = None
    for mth in months:
        cur = levels.get(mth)
        if cur is not None and prev is not None and prev > 0:
            out[mth] = cur / prev - 1
        if cur is not None:
            prev = cur
    return out


def cagr(levels: dict[str, float], months: list[str]) -> float:
    avail = [m for m in months if m in levels]
    if len(avail) < 2:
        return float("nan")
    a, b = levels[avail[0]], levels[avail[-1]]
    if a <= 0 or b <= 0:
        return float("nan")
    return (b / a) ** (12 / (len(avail) - 1)) - 1


# ----------------------------------------------------------------------------
# 合成人民币序列 + 包装损耗校准
# ----------------------------------------------------------------------------
def synth_rmb(usd: dict[str, float], fx: dict[str, float]) -> dict[str, float]:
    """美元前复权净值 × 汇率 → 人民币计价净值（未扣损耗）"""
    return {m: usd[m] * fx[m] for m in usd if m in fx}


def calibrate_drag(real: dict[str, float], syn: dict[str, float]) -> dict[str, float]:
    """用重叠期校准「大陆 QDII 包装」相对纯指数的年化损耗。

    返回两种口径：
      cagr_gap  : 用首末点年化之差（含期初/期末溢价错位的一次性影响）
      median_gap: 用逐月收益中位数之差年化（对溢价一次性错位更稳健）
    """
    common = sorted(set(real) & set(syn))
    months = month_range(common[0], common[-1])
    r_real = returns_from_levels(real, months)
    r_syn = returns_from_levels(syn, months)
    both = sorted(set(r_real) & set(r_syn))

    c_real = cagr(real, months)
    c_syn = cagr(syn, months)
    cagr_gap = 1 - (1 + c_real) / (1 + c_syn)

    diffs = [r_syn[m] - r_real[m] for m in both]
    median_gap = (1 + statistics.median(diffs)) ** 12 - 1

    return {
        "start": common[0],
        "end": common[-1],
        "months": len(both),
        "cagr_real": c_real,
        "cagr_syn": c_syn,
        "cagr_gap": cagr_gap,
        "median_gap": median_gap,
        "tracking_sd": statistics.stdev(diffs) * (12**0.5),
    }


def levels_from_returns(rets: dict[str, float], months: list[str]) -> dict[str, float]:
    """月度收益率 → 归一化净值。基期为首个有收益月的上一个月，净值 = 1。"""
    idx = next((i for i, m in enumerate(months) if m in rets), None)
    if idx is None:
        return {}
    out: dict[str, float] = {}
    acc = 1.0
    if idx > 0:
        out[months[idx - 1]] = acc
    for mth in months[idx:]:
        if mth not in rets:
            break  # 中间断档就截断，不跨洞拼接
        acc *= 1 + rets[mth]
        out[mth] = acc
    return out


def apply_drag(levels: dict[str, float], annual_drag: float, months: list[str]) -> dict[str, float]:
    """在合成净值上按月扣除年化包装损耗"""
    factor = (1 - annual_drag) ** (1 / 12)
    rets = returns_from_levels(levels, months)
    return levels_from_returns(
        {m: (1 + r) * factor - 1 for m, r in rets.items()}, months
    )


def splice(real: dict[str, float], syn: dict[str, float], months: list[str]) -> dict[str, float]:
    """真实序列优先，其上市前用合成序列的收益率向前接。"""
    r_real = returns_from_levels(real, months)
    r_syn = returns_from_levels(syn, months)
    merged = {
        m: (r_real[m] if m in r_real else r_syn[m])
        for m in months
        if m in r_real or m in r_syn
    }
    return levels_from_returns(merged, months)


# ----------------------------------------------------------------------------
# 组合模拟
# ----------------------------------------------------------------------------
class GlidePath:
    """按年龄段给出目标权重"""

    def __init__(self, name: str, stages: list[tuple[int, int, dict[str, float]]], label: str = ""):
        self.name = name
        self.label = label
        self.stages = stages
        for _, _, w in stages:
            assert abs(sum(w.values()) - 1) < 1e-9, f"{name} 权重不等于 1: {w}"

    def weights(self, age: float) -> dict[str, float]:
        for lo, hi, w in self.stages:
            if lo <= age <= hi:
                return w
        return self.stages[-1][2]

    def assets(self) -> list[str]:
        seen: list[str] = []
        for _, _, w in self.stages:
            for a in w:
                if a not in seen:
                    seen.append(a)
        return seen


def irr_monthly(flows: list[float]) -> float:
    """月度现金流 IRR（年化）。flows[0] 为最早，末项含终值。"""
    def npv(rate: float) -> float:
        return sum(f / (1 + rate) ** i for i, f in enumerate(flows))

    lo, hi = -0.9, 1.0
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


def simulate(
    glide: GlidePath,
    rets: dict[str, dict[str, float]],
    months: list[str],
    contrib_months: int = CONTRIB_MONTHS,
    monthly_contrib: float = MONTHLY_CONTRIB,
    start_age: float = START_AGE,
    initial: float = 0.0,
) -> dict:
    """从 months[0] 起逐月模拟。months 为收益月序列（第 i 个月产生 rets[a][months[i]]）。"""
    assets = glide.assets()
    w0 = glide.weights(start_age)
    holdings = {a: initial * w0.get(a, 0.0) for a in assets}
    flows: list[float] = []
    peak = 0.0
    max_dd = 0.0
    equity: list[float] = []
    contributed = 0.0
    cost_paid = 0.0
    # 策略自身净值（剔除定投带来的规模增长），用于衡量真实波动
    nav = 1.0
    nav_peak = 1.0
    nav_max_dd = 0.0
    nav_series: list[float] = []
    value_at_50 = None
    if initial:
        flows.append(-initial)  # 期初一次性投入，占现金流第 0 期

    for i, mth in enumerate(months):
        age = start_age + i / 12

        # 1) 市场收益
        before = sum(holdings.values())
        for a in assets:
            r = rets[a].get(mth)
            if r is None:
                return {"ok": False, "reason": f"{a} 缺 {mth} 数据"}
            holdings[a] *= 1 + r
        after = sum(holdings.values())
        if before > 0:
            nav *= after / before
            nav_peak = max(nav_peak, nav)
            nav_max_dd = min(nav_max_dd, nav / nav_peak - 1)
        nav_series.append(nav)

        # 2) 月末定额买入（新增资金优先补低配）
        cash = monthly_contrib if i < contrib_months else 0.0
        contributed += cash
        w = glide.weights(age)
        if cash > 0:
            total = sum(holdings.values()) + cash
            need = {a: max(0.0, total * w.get(a, 0.0) - holdings[a]) for a in assets}
            tot_need = sum(need.values())
            if tot_need <= 0:
                for a in assets:
                    holdings[a] += cash * w.get(a, 0.0)
            else:
                for a in assets:
                    holdings[a] += cash * need[a] / tot_need

        # 3) 1 月 / 7 月再平衡（偏离超阈值才动，计交易成本）
        if int(mth[5:7]) in REBALANCE_MONTHS:
            total = sum(holdings.values())
            if total > 0:
                dev = max(abs(holdings[a] / total - w.get(a, 0.0)) for a in assets)
                if dev > REBALANCE_THRESHOLD:
                    turnover = sum(
                        abs(total * w.get(a, 0.0) - holdings[a]) for a in assets
                    ) / 2
                    cost = turnover * TRADE_COST
                    cost_paid += cost
                    total -= cost
                    for a in assets:
                        holdings[a] = total * w.get(a, 0.0)

        value = sum(holdings.values())
        equity.append(value)
        flows.append(-cash)
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1)
        if i + 1 == contrib_months:
            value_at_50 = value

    final = sum(holdings.values())
    flows[-1] += final

    return {
        "ok": True,
        "start_month": months[0],
        "end_month": months[-1],
        "n_months": len(months),
        "contributed": contributed,
        "initial": initial,
        "final": final,
        "value_at_50": value_at_50,
        "growth": final / initial if initial else float("nan"),
        "multiple": final / contributed if contributed else float("nan"),
        "irr": irr_monthly(flows),
        "max_dd": max_dd,
        "nav_max_dd": nav_max_dd,
        "trade_cost": cost_paid,
        "equity": equity,
        "nav": nav_series,
    }


def pct(vals: list[float], q: float) -> float:
    """分位数（线性插值）"""
    if not vals:
        return float("nan")
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def rolling(
    glide: GlidePath,
    rets: dict[str, dict[str, float]],
    months: list[str],
    span: int,
    **kw,
) -> list[dict]:
    """在所有可用起点上跑 span 个月的滚动窗口"""
    assets = glide.assets()
    avail = [m for m in months if all(m in rets[a] for a in assets)]
    out = []
    for s in range(0, len(avail) - span + 1):
        r = simulate(glide, rets, avail[s: s + span], **kw)
        if r["ok"]:
            out.append({k: v for k, v in r.items() if k not in ("equity", "nav")})
    return out


# ----------------------------------------------------------------------------
# 配置候选
# ----------------------------------------------------------------------------
def build_glides() -> list[GlidePath]:
    """候选滑翔路径。资产键：DIV=红利 SPX=标普500 NDX=纳指100 CXI=中概互联 GEM=创业板"""
    return [
        GlidePath(
            "推荐·激进纳指为核",
            [
                (40, 49, {"DIV": 0.20, "SPX": 0.30, "NDX": 0.50}),
                (50, 54, {"DIV": 0.30, "SPX": 0.30, "NDX": 0.40}),
                (55, 59, {"DIV": 0.45, "SPX": 0.25, "NDX": 0.30}),
                (60, 99, {"DIV": 0.55, "SPX": 0.25, "NDX": 0.20}),
            ],
            "投入期不降仓，50 岁后分三段滑翔",
        ),
        GlidePath(
            "yyang基准",
            [
                (0, 46, {"DIV": 0.45, "SPX": 0.30, "NDX": 0.25}),
                (47, 51, {"DIV": 0.50, "SPX": 0.30, "NDX": 0.20}),
                (52, 99, {"DIV": 0.60, "SPX": 0.25, "NDX": 0.15}),
            ],
            "中低风险原方案（对照组）",
        ),
        GlidePath(
            "激进A·纳指为核",
            [
                (0, 44, {"DIV": 0.15, "SPX": 0.30, "NDX": 0.55}),
                (45, 49, {"DIV": 0.25, "SPX": 0.30, "NDX": 0.45}),
                (50, 54, {"DIV": 0.35, "SPX": 0.30, "NDX": 0.35}),
                (55, 99, {"DIV": 0.50, "SPX": 0.25, "NDX": 0.25}),
            ],
            "三资产，纳指顶格",
        ),
        GlidePath(
            "激进B·纳指为核+中概卫星",
            [
                (0, 44, {"DIV": 0.15, "SPX": 0.25, "NDX": 0.50, "CXI": 0.10}),
                (45, 49, {"DIV": 0.25, "SPX": 0.25, "NDX": 0.42, "CXI": 0.08}),
                (50, 54, {"DIV": 0.35, "SPX": 0.28, "NDX": 0.32, "CXI": 0.05}),
                (55, 99, {"DIV": 0.50, "SPX": 0.25, "NDX": 0.25}),
            ],
            "加中概互联做高弹性卫星",
        ),
        GlidePath(
            "激进C·全美股无红利",
            [
                (0, 49, {"SPX": 0.40, "NDX": 0.60}),
                (50, 54, {"DIV": 0.25, "SPX": 0.35, "NDX": 0.40}),
                (55, 99, {"DIV": 0.45, "SPX": 0.30, "NDX": 0.25}),
            ],
            "投入期完全放弃红利底仓",
        ),
        GlidePath(
            "激进D·纳指+创业板",
            [
                (0, 44, {"DIV": 0.15, "SPX": 0.25, "NDX": 0.45, "GEM": 0.15}),
                (45, 49, {"DIV": 0.25, "SPX": 0.25, "NDX": 0.40, "GEM": 0.10}),
                (50, 54, {"DIV": 0.35, "SPX": 0.30, "NDX": 0.35}),
                (55, 99, {"DIV": 0.50, "SPX": 0.25, "NDX": 0.25}),
            ],
            "用创业板替代部分成长敞口",
        ),
        GlidePath(
            "激进E·纳指为核·晚降仓",
            [
                (0, 49, {"DIV": 0.20, "SPX": 0.28, "NDX": 0.52}),
                (50, 55, {"DIV": 0.35, "SPX": 0.30, "NDX": 0.35}),
                (56, 99, {"DIV": 0.55, "SPX": 0.25, "NDX": 0.20}),
            ],
            "整个投入期不降仓，50 岁后才滑翔",
        ),
    ]


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def build_universe(
    div_boost: float = 0.0, us_haircut: float = 0.0
) -> tuple[dict, dict, list[str], dict]:
    """装载数据、校准损耗、拼出各资产人民币月度收益序列。

    div_boost:  给红利资产额外加的年化收益，用于敏感性测试
                （510880 从 2007 年泡沫高点起算偏保守，且中证红利/红利低波
                 这类更高股息的标的没有同样长的历史）
    us_haircut: 给纳指/标普扣减的年化收益，用于回答「美股未来跑不出过去 19 年
                这么好怎么办」——回测窗口全都落在美股大牛市里，必须压力测试
    """
    raw = {
        k: to_month_end(load_series(k))
        for k in (
            "510880", "515080", "512890", "513100", "159941", "513500",
            "513050", "159915", "510300", "QQQ", "SPY", "USDCNY",
        )
    }
    all_months = month_range("2007-01", "2026-07")
    fx = raw["USDCNY"]

    syn_ndx_raw = synth_rmb(raw["QQQ"], fx)
    syn_spx_raw = synth_rmb(raw["SPY"], fx)
    cal = {
        "NDX": calibrate_drag(raw["513100"], syn_ndx_raw),
        "SPX": calibrate_drag(raw["513500"], syn_spx_raw),
    }
    drag = {
        a: round(max(cal[a]["cagr_gap"], cal[a]["median_gap"]), 4) for a in cal
    }

    levels = {
        "DIV": splice(raw["510880"], {}, all_months),
        "NDX": splice(raw["513100"], apply_drag(syn_ndx_raw, drag["NDX"], all_months), all_months),
        "SPX": splice(raw["513500"], apply_drag(syn_spx_raw, drag["SPX"], all_months), all_months),
        "CXI": splice(raw["513050"], {}, all_months),
        "GEM": splice(raw["159915"], {}, all_months),
    }
    rets = {a: returns_from_levels(lv, all_months) for a, lv in levels.items()}
    if div_boost:
        bump = (1 + div_boost) ** (1 / 12)
        rets["DIV"] = {m: (1 + r) * bump - 1 for m, r in rets["DIV"].items()}
    if us_haircut:
        cut = (1 - us_haircut) ** (1 / 12)
        for a in ("NDX", "SPX"):
            rets[a] = {m: (1 + r) * cut - 1 for m, r in rets[a].items()}

    meta = {"raw": raw, "cal": cal, "drag": drag, "levels": levels}
    return rets, levels, all_months, meta


def describe(runs: list[dict], key: str) -> dict:
    vals = [r[key] for r in runs]
    return {
        "n": len(vals),
        "min": min(vals),
        "p10": pct(vals, 0.10),
        "p25": pct(vals, 0.25),
        "median": statistics.median(vals),
        "p75": pct(vals, 0.75),
        "p90": pct(vals, 0.90),
        "max": max(vals),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="把结果写到 JSON 文件")
    ap.add_argument("--div-boost", type=float, default=0.0,
                    help="给红利资产额外加的年化收益（敏感性测试，如 0.015）")
    ap.add_argument("--us-haircut", type=float, default=0.0,
                    help="给纳指/标普扣减的年化收益（压力测试，如 0.03）")
    args = ap.parse_args()

    rets, levels, all_months, meta = build_universe(args.div_boost, args.us_haircut)
    raw, cal, drag = meta["raw"], meta["cal"], meta["drag"]
    glides = build_glides()
    chosen_name = "推荐·激进纳指为核"

    print("=" * 84)
    print("① 原始数据总览（月末后复权 = 分红再投；大陆 ETF 为真实成交价）")
    print("=" * 84)
    for k, s in raw.items():
        ms = sorted(s)
        print(f"  {k:8s} {ms[0]} → {ms[-1]}  月数={len(ms):4d}  "
              f"期间年化={cagr(s, month_range(ms[0], ms[-1])):8.2%}")

    print()
    print("=" * 84)
    print("② QDII「包装损耗」校准：真实场内 ETF  vs  美元ETF×汇率")
    print("=" * 84)
    for tag, a in (("纳指 513100", "NDX"), ("标普 513500", "SPX")):
        c = cal[a]
        print(f"  {tag}  重叠期 {c['start']}→{c['end']}（{c['months']} 个月）")
        print(f"    真实场内年化 {c['cagr_real']:7.2%}   美元×汇率合成年化 {c['cagr_syn']:7.2%}")
        print(f"    首末口径损耗 {c['cagr_gap']:7.2%}   逐月中位口径 {c['median_gap']:7.2%}"
              f"   月度差异年化波动 {c['tracking_sd']:6.2%}")
    print(f"\n  → 合成段采用（取更保守者）：纳指 −{drag['NDX']:.2%}/年，标普 −{drag['SPX']:.2%}/年")

    print()
    print("=" * 84)
    print("③ 拼接后各资产（人民币计价，可投资口径）")
    print("=" * 84)
    names = {"DIV": "红利 510880", "NDX": "纳指100", "SPX": "标普500",
             "CXI": "中概互联 513050", "GEM": "创业板 159915"}
    for a, lv in levels.items():
        ms = sorted(lv)
        r = returns_from_levels(lv, all_months)
        vol = statistics.stdev(r.values()) * (12 ** 0.5)
        print(f"  {names[a]:16s} {ms[0]} → {ms[-1]}  {len(ms):4d}月  "
              f"年化={cagr(lv, month_range(ms[0], ms[-1])):7.2%}  "
              f"年化波动={vol:6.2%}  最差单月={min(r.values()):7.2%}")
    if args.div_boost:
        print(f"  ※ 敏感性测试：红利年化已额外 +{args.div_boost:.2%}")
    if args.us_haircut:
        print(f"  ※ 压力测试：纳指/标普年化已扣减 −{args.us_haircut:.2%}")

    # ---- ④ 阶段一：滚动 10 年定投窗口 ----
    print()
    print("=" * 84)
    print(f"④ 阶段一 40→50 岁：滚动 10 年定投（每月 {MONTHLY_CONTRIB:,.0f} 元，累计投入 100 万）")
    print("=" * 84)
    print(f"  {'策略':24s} {'窗口':>4s} {'起点范围':>17s} {'IRR中位':>8s} {'IRR最差':>8s} "
          f"{'IRR最好':>8s} {'终值中位':>9s} {'终值最差':>9s} {'策略回撤中位':>11s}")
    print("  " + "-" * 106)

    summary: dict[str, dict] = {}
    for g in glides:
        runs = rolling(g, rets, all_months, CONTRIB_MONTHS)
        if not runs:
            n = len([m for m in all_months if all(m in rets[a] for a in g.assets())])
            print(f"  {g.name:24s} 数据不足（仅 {n} 个月，需 {CONTRIB_MONTHS}）")
            summary[g.name] = {"label": g.label, "insufficient": True, "months": n}
            continue
        summary[g.name] = {
            "label": g.label,
            "stages": [[lo, hi, w] for lo, hi, w in g.stages],
            "phase1": {
                "n_windows": len(runs),
                "first_start": runs[0]["start_month"],
                "last_start": runs[-1]["start_month"],
                "irr": describe(runs, "irr"),
                "final": describe(runs, "final"),
                "nav_max_dd": describe(runs, "nav_max_dd"),
                "acct_max_dd": describe(runs, "max_dd"),
            },
        }
        p = summary[g.name]["phase1"]
        print(f"  {g.name:24s} {p['n_windows']:4d} "
              f"{p['first_start']}→{p['last_start']} "
              f"{p['irr']['median']:8.2%} {p['irr']['min']:8.2%} {p['irr']['max']:8.2%} "
              f"{p['final']['median']/1e4:8.0f}万 {p['final']['min']/1e4:8.0f}万 "
              f"{p['nav_max_dd']['median']:11.1%}")

    # ---- ⑤ 同窗口口径（含中概/创业板方案也能比）----
    print()
    print("=" * 84)
    print("⑤ 同一起点区间的公平对比（受中概互联数据长度限制，取 2017-02 起 114 个月）")
    print("=" * 84)
    span_common = 114
    common_months = [m for m in all_months if m >= "2017-02"]
    for g in glides:
        runs = rolling(g, rets, common_months, span_common)
        if not runs:
            print(f"  {g.name:24s} 数据不足")
            continue
        r = runs[0]
        summary.setdefault(g.name, {})["common_window"] = {
            k: v for k, v in r.items()
        }
        print(f"  {g.name:24s} {r['start_month']}→{r['end_month']}  "
              f"投入={r['contributed']/1e4:5.1f}万  终值={r['final']/1e4:6.1f}万  "
              f"IRR={r['irr']:6.2%}  策略最大回撤={r['nav_max_dd']:6.1%}")

    # ---- ⑥ 阶段二：50→60 岁只复利 ----
    print()
    print("=" * 84)
    print("⑥ 阶段二 50→60 岁：停止投入、仅持有 10 年（滚动窗口，期初 1 元）")
    print("=" * 84)
    phase2: dict[str, dict] = {}
    for g in glides:
        runs = rolling(g, rets, all_months, HOLD_MONTHS, contrib_months=0,
                       monthly_contrib=0.0, start_age=50, initial=1.0)
        if not runs:
            print(f"  {g.name:24s} 数据不足")
            continue
        ann = [r["growth"] ** (12 / HOLD_MONTHS) - 1 for r in runs]
        phase2[g.name] = {
            "n_windows": len(runs),
            "hold_years": HOLD_MONTHS // 12,
            "annual": {
                "min": min(ann), "p10": pct(ann, 0.10), "median": statistics.median(ann),
                "p90": pct(ann, 0.90), "max": max(ann),
            },
            "nav_max_dd": describe(runs, "nav_max_dd"),
        }
        summary.setdefault(g.name, {})["phase2"] = phase2[g.name]
        a_ = phase2[g.name]["annual"]
        print(f"  {g.name:24s} {len(runs):3d}窗口  {HOLD_MONTHS//12} 年年化: "
              f"最差={a_['min']:7.2%} p10={a_['p10']:7.2%} 中位={a_['median']:7.2%} "
              f"p90={a_['p90']:7.2%} 最好={a_['max']:7.2%}   "
              f"回撤中位={phase2[g.name]['nav_max_dd']['median']:6.1%}")

    # ---- ⑦ 完整真实路径：2007-02 起 ----
    print()
    print("=" * 84)
    print("⑦ 完整真实路径：2007-02 起投（40 岁，正好赶上 2008 年崩盘前），")
    print("   投 10 年、持有到 2026-07（59.5 岁）")
    print("=" * 84)
    full_months = [m for m in all_months if m >= "2007-02"]
    for g in glides:
        if not all(full_months[0] in rets[a] for a in g.assets()):
            miss = [names[a] for a in g.assets() if full_months[0] not in rets[a]]
            print(f"  {g.name:24s} 跳过（{'、'.join(miss)} 无 2007 年数据）")
            continue
        r = simulate(g, rets, full_months)
        if not r["ok"]:
            print(f"  {g.name:24s} {r['reason']}")
            continue
        summary.setdefault(g.name, {})["full_path"] = {
            k: v for k, v in r.items() if k not in ("equity", "nav")
        }
        if g.name == chosen_name:
            summary[g.name]["full_path_equity"] = r["equity"]
            summary[g.name]["full_path_months"] = full_months
        print(f"  {g.name:24s} 50岁={r['value_at_50']/1e4:6.0f}万  "
              f"59.5岁终值={r['final']/1e4:6.0f}万  本金={r['contributed']/1e4:3.0f}万  "
              f"倍数={r['multiple']:5.2f}x  IRR={r['irr']:6.2%}  "
              f"策略最大回撤={r['nav_max_dd']:6.1%}")

    # ---- ⑧ 60 岁终值情景 ----
    print()
    print("=" * 84)
    print("⑧ 60 岁终值情景（阶段一终值 × 阶段二 11 年复利，同分位配对）")
    print("=" * 84)
    scen: dict[str, dict] = {}
    for g in glides:
        s = summary.get(g.name, {})
        if "phase1" not in s or "phase2" not in s:
            continue
        f1, a2 = s["phase1"]["final"], s["phase2"]["annual"]
        rows = {}
        for tag, fk, ak in (("悲观", "p10", "p10"), ("中性", "median", "median"),
                            ("乐观", "p90", "p90")):
            v50 = f1[fk]
            rows[tag] = {
                "v50": v50,
                "annual": a2[ak],
                "v60": v50 * (1 + a2[ak]) ** (HOLD_MONTHS // 12),
            }
        rows["最差"] = {
            "v50": f1["min"], "annual": a2["min"],
            "v60": f1["min"] * (1 + a2["min"]) ** (HOLD_MONTHS // 12),
        }
        scen[g.name] = rows
        summary[g.name]["scenarios"] = rows
        print(f"  {g.name:24s} "
              + "  ".join(
                  f"{t}: 50岁{rows[t]['v50']/1e4:5.0f}万→60岁{rows[t]['v60']/1e4:6.0f}万"
                  f"({rows[t]['annual']:5.2%})"
                  for t in ("最差", "悲观", "中性", "乐观")
              ))

    if args.json:
        out = {
            "meta": {
                "monthly_contrib": MONTHLY_CONTRIB,
                "annual_contrib": MONTHLY_CONTRIB * 12,
                "contrib_months": CONTRIB_MONTHS,
                "start_age": START_AGE,
                "end_age": TARGET_AGE_END,
                "drag": drag,
                "calibration": cal,
                "div_boost": args.div_boost,
                "us_haircut": args.us_haircut,
                "data_range": [all_months[0], all_months[-1]],
                "rebalance_months": list(REBALANCE_MONTHS),
                "rebalance_threshold": REBALANCE_THRESHOLD,
                "trade_cost": TRADE_COST,
                "chosen": chosen_name,
            },
            "assets": {
                a: {
                    "name": names[a],
                    "first": sorted(lv)[0],
                    "last": sorted(lv)[-1],
                    "cagr": cagr(lv, month_range(sorted(lv)[0], sorted(lv)[-1])),
                    "vol": statistics.stdev(
                        returns_from_levels(lv, all_months).values()
                    ) * (12 ** 0.5),
                    "worst_month": min(returns_from_levels(lv, all_months).values()),
                }
                for a, lv in levels.items()
            },
            "strategies": summary,
        }
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已写出 {args.json}")


if __name__ == "__main__":
    main()

