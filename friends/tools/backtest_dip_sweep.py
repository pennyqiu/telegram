#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回撤阶梯策略的参数曲面扫描（配合 backtest_dip_rolling.py）。

为什么要扫曲面
--------------
单一参数组合跑出来"策略有效"几乎没有信息量——参数是可以挑的。
判断逻辑是否稳健，要看**收益曲面平不平滑**：
  平滑  → 逻辑本身在起作用，参数只是微调
  尖峰  → 结论是拟合出来的运气，换个参数就没了

本脚本从一个基线出发，每次只动一个因子（one-factor-at-a-time），
看"阶梯 vs 全额立投"的超额收益怎么变。比全网格更容易读出因果。

扫描的因子
----------
  A 现金收益率   ：干粮空等的机会成本（旧脚本按 0% 算，会高估阶梯）
  B 每月新钱     ：新钱越多，期初干粮的择时越不重要
  C 持有年数     ：5/10/15 年
  D 时间再装填   ：0(关闭)/6/12/24 个月 —— 长期水下能否继续买
  E ATH 播种     ：开/关 —— 量化旧脚本"把首日当新高"的偏差有多大
  F 标的         ：SPY / .IXIC（波动更大，阶梯理论上更有利）
  G 阶梯深度     ：阈值整体 ×0.5 / ×1 / ×1.5 / ×2

用法
----
  python backtest_dip_sweep.py
  python backtest_dip_sweep.py --report sweep.txt

仅供研究，非投资建议。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import backtest_dip_rolling as R

TOOLS_DIR = Path(__file__).resolve().parent
LADDER_FILE = TOOLS_DIR / "us_dip_watchlist.json"

BASE = {
    "symbol": "SPY", "initial": 100.0, "monthly": 1.0, "cash_yield": 2.0,
    "expense": 0.09, "rearm_months": 12, "window_years": 10.0,
    "ath_mode": "pit", "ladder_scale": 1.0,
}


def run_cfg(cfg: dict, cache: dict) -> dict:
    """跑一个配置，返回四个策略的滚动回测汇总。"""
    key = json.dumps(cfg, sort_keys=True)
    if key in cache:
        return cache[key]

    sym = cfg["symbol"]
    series = R.fetch_daily(sym)
    group = R.GROUP_OF.get(sym, "标普500")
    ladder_raw = json.loads(LADDER_FILE.read_text(encoding="utf-8"))["groups"][group]["ladder"]
    ladder = [{"drop": t["drop"] * cfg["ladder_scale"], "buy": t["buy"]} for t in ladder_raw]
    div_y = R.DIV_YIELD.get(sym, 1.5)

    sim = R.Sim(series, initial=cfg["initial"], monthly=cfg["monthly"], div_yield_pct=div_y,
                cash_yield_pct=cfg["cash_yield"], expense_pct=cfg["expense"])
    seed = R.SEED_ATH.get(sym)
    sim.seed_ath = float(seed["ath"]) if seed else 0.0
    sim.seed_ath_date = str(seed["date"]) if sim.seed_ath else ""
    sim.ath_mode = cfg["ath_mode"]

    strategies = {
        "S1": R.strat_lump,
        "S2": R.make_strat_spread(12),
        "S3": R.make_strat_ladder(ladder, rearm_months=cfg["rearm_months"], dca_monthly=False),
        "S4": R.make_strat_ladder(ladder, rearm_months=cfg["rearm_months"], dca_monthly=True),
    }

    win = int(cfg["window_years"] * 252)
    starts, seen = [], set()
    for i, (d, _) in enumerate(series):
        if i + win >= len(series):
            break
        if d[:7] not in seen:
            seen.add(d[:7])
            starts.append(i)
    if not starts:
        return {"n": 0}

    res = {k: [sim.run(st, i0, i0 + win) for i0 in starts] for k, st in strategies.items()}
    base = res["S1"]
    same = sum(1 for a, b in zip(res["S4"], base) if abs(a["final"] - b["final"]) < 1e-9)
    out = {"n": len(starts), "span": f"{series[starts[0]][0]}~{series[starts[-1]][0]}",
           "s4_same_as_s1_pct": same / len(starts) * 100}
    for k in strategies:
        mm = sorted(r["money_multiple"] for r in res[k])
        rel = [(r["final"] / b["final"] - 1) * 100 for r, b in zip(res[k], base)]
        cost = sorted((b["avg_cost"] / r["avg_cost"] - 1) * 100 for r, b in zip(res[k], base)
                      if r["avg_cost"] and r["avg_cost"] == r["avg_cost"])
        srel = sorted(rel)
        out[k] = {
            "mm_med": R.pct_of(mm, 50), "mm_p10": R.pct_of(mm, 10), "mm_min": mm[0],
            "rel_med": R.pct_of(srel, 50), "rel_mean": sum(rel) / len(rel),
            "rel_worst": srel[0],
            "win_pct": sum(1 for x in rel if x > 0) / len(rel) * 100,
            "cost_vs_s1_med": R.pct_of(cost, 50),
            "cash_end": sum(r["cash_pct_end"] for r in res[k]) / len(res[k]),
        }
    cache[key] = out
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="回撤阶梯参数曲面扫描")
    ap.add_argument("--report", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    say = R.Tee(Path(args.report) if args.report else None)
    cache: dict = {}
    collected: dict = {}

    sweeps = [
        ("A 现金年化收益%", "cash_yield", [0.0, 2.0, 4.0]),
        ("B 每月新钱(期初=100)", "monthly", [0.0, 0.5, 1.0, 2.0]),
        ("C 持有年数", "window_years", [5.0, 10.0, 15.0]),
        ("D 时间再装填(月)", "rearm_months", [0, 6, 12, 24]),
        ("E ATH口径", "ath_mode", ["pit", "window"]),
        ("F 标的", "symbol", ["SPY", ".IXIC"]),
        ("G 阶梯阈值倍数", "ladder_scale", [0.5, 1.0, 1.5, 2.0]),
    ]

    b = BASE
    say("=" * 108)
    say("基线配置：" + " · ".join(f"{k}={v}" for k, v in b.items()))
    say("说明：rel_med = 相对 S1「全额立投」的终值超额中位数%；win% = 跑赢 S1 的起点占比")
    say("      cost = 加权买入成本相对 S1 的优势%（正数才是真的买得更便宜）")
    say("=" * 108)

    for title, field, values in sweeps:
        say(f"\n【{title}】")
        say(f"{'取值':<14}{'起点数':>7}{'S1中位':>9}"
            f"{'S3 rel%':>9}{'S3 win%':>9}{'S3 cost%':>10}"
            f"{'S4 rel%':>9}{'S4 win%':>9}{'S4 cost%':>10}"
            f"{'S3期末现金%':>12}{'S4=S1占比%':>12}")
        rows = []
        for v in values:
            cfg = dict(b)
            cfg[field] = v
            r = run_cfg(cfg, cache)
            if not r.get("n"):
                say(f"{str(v):<14}  样本不足")
                continue
            say(f"{str(v):<14}{r['n']:>7}{r['S1']['mm_med']:>9.3f}"
                f"{r['S3']['rel_med']:>9.2f}{r['S3']['win_pct']:>9.1f}{r['S3']['cost_vs_s1_med']:>10.2f}"
                f"{r['S4']['rel_med']:>9.2f}{r['S4']['win_pct']:>9.1f}{r['S4']['cost_vs_s1_med']:>10.2f}"
                f"{r['S3']['cash_end']:>12.1f}{r['s4_same_as_s1_pct']:>12.1f}")
            rows.append({"value": v, **{k: r[k] for k in ("S1", "S2", "S3", "S4")},
                         "n": r["n"], "span": r["span"]})
        collected[title] = rows

    say("\n" + "=" * 108)
    say("怎么读这张表：")
    say("  · 如果 S3/S4 的 rel% 在所有因子下都是负的且变化平缓 → 结论稳健：阶梯确实赢不了立投")
    say("  · 如果只在某个窄参数区间为正 → 那是拟合，不是逻辑")
    say("  · cost% 为负说明「等回撤再买」的实际成交价反而比立刻买更贵（上涨市里等待有代价）")

    if args.json:
        Path(args.json).write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
        say(f"\nJSON → {args.json}")
    if args.report:
        say(f"报告 → {args.report}")
    say.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
