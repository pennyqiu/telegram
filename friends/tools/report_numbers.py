#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把回测结果整理成写页面要用的数字，避免手抄出错。

依赖 backtest_cn_etf.py（同目录）与 backtest_data/ 缓存。

用法：
  python3 friends/tools/report_numbers.py
  python3 friends/tools/report_numbers.py --json /tmp/report.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from backtest_cn_etf import (
    CONTRIB_MONTHS,
    HOLD_MONTHS,
    MONTHLY_CONTRIB,
    build_glides,
    build_universe,
    cagr,
    month_range,
    pct,
    returns_from_levels,
    rolling,
    simulate,
)

RECOMMENDED = "推荐·激进纳指为核"
NAMES = {"DIV": "红利", "NDX": "纳指100", "SPX": "标普500",
         "CXI": "中概互联", "GEM": "创业板"}


def max_drawdown(levels: dict[str, float]) -> tuple[float, str]:
    peak, dd, at = 0.0, 0.0, ""
    for m in sorted(levels):
        peak = max(peak, levels[m])
        if peak > 0 and levels[m] / peak - 1 < dd:
            dd, at = levels[m] / peak - 1, m
    return dd, at


def stage_returns(
    weights: dict[str, float], rets: dict, months: list[str], years: int = 10
) -> dict:
    """某一组固定权重、每年再平衡的滚动 N 年年化收益分布"""
    assets = list(weights)
    avail = [m for m in months if all(m in rets[a] for a in assets)]
    span = years * 12
    anns, dds = [], []
    for s in range(0, len(avail) - span + 1):
        win = avail[s: s + span]
        holdings = dict(weights)
        peak, dd = 1.0, 0.0
        for m in win:
            for a in assets:
                holdings[a] *= 1 + rets[a][m]
            v = sum(holdings.values())
            peak = max(peak, v)
            dd = min(dd, v / peak - 1)
            if int(m[5:7]) == 1:
                holdings = {a: v * weights[a] for a in assets}
        anns.append(sum(holdings.values()) ** (1 / years) - 1)
        dds.append(dd)
    return {
        "n": len(anns),
        "min": min(anns), "p10": pct(anns, 0.10), "p25": pct(anns, 0.25),
        "median": statistics.median(anns), "p75": pct(anns, 0.75),
        "p90": pct(anns, 0.90), "max": max(anns),
        "dd_median": statistics.median(dds), "dd_worst": min(dds),
    }


def year_table(stage_rates: list[tuple[int, int, float]]) -> list[dict]:
    """逐年测算：40→49 岁每月定额投入，50→60 岁只复利。按月计息。"""
    rate_of = {}
    for lo, hi, r in stage_rates:
        for age in range(lo, hi + 1):
            rate_of[age] = r
    rows = []
    value = 0.0
    invested = 0.0
    for age in range(40, 60):
        r_m = (1 + rate_of[age]) ** (1 / 12) - 1
        contrib = MONTHLY_CONTRIB if age < 40 + CONTRIB_MONTHS // 12 else 0.0
        start = value
        for _ in range(12):
            value = value * (1 + r_m) + contrib
            invested += contrib
        rows.append({
            "age_end": age + 1,
            "annual_rate": rate_of[age],
            "contrib_year": contrib * 12,
            "invested": invested,
            "start": start,
            "end": value,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args()

    rets, levels, all_months, meta = build_universe()
    raw, cal, drag = meta["raw"], meta["cal"], meta["drag"]
    glides = {g.name: g for g in build_glides()}
    rec = glides[RECOMMENDED]

    out: dict = {}

    # ---------- 1. 资产 ----------
    print("=" * 92)
    print("【1】资产历史表现（人民币可投资口径，2007-01 起）")
    print("=" * 92)
    print(f"  {'资产':10s} {'区间':>17s} {'年化':>8s} {'年化波动':>9s} "
          f"{'最差单月':>9s} {'最大回撤':>9s} {'回撤底部':>9s}")
    out["assets"] = {}
    for a, lv in levels.items():
        ms = sorted(lv)
        r = returns_from_levels(lv, all_months)
        dd, at = max_drawdown(lv)
        rec_a = {
            "name": NAMES[a], "first": ms[0], "last": ms[-1],
            "cagr": cagr(lv, month_range(ms[0], ms[-1])),
            "vol": statistics.stdev(r.values()) * 12**0.5,
            "worst_month": min(r.values()), "max_dd": dd, "dd_at": at,
        }
        out["assets"][a] = rec_a
        print(f"  {NAMES[a]:10s} {ms[0]}→{ms[-1]} {rec_a['cagr']:8.2%} "
              f"{rec_a['vol']:9.2%} {rec_a['worst_month']:9.2%} {dd:9.1%} {at:>9s}")

    # ---------- 2. 红利标的选择 ----------
    print()
    print("=" * 92)
    print("【2】红利底仓该选哪只（共同区间对比）")
    print("=" * 92)
    div_codes = {"510880": "华泰柏瑞上证红利", "515080": "招商中证红利", "512890": "华泰柏瑞红利低波"}
    me = {c: {m: v for m, v in raw[c].items()} for c in div_codes}
    common = sorted(set.intersection(*(set(v) for v in me.values())))
    out["div_compare"] = {"window": [common[0], common[-1]], "items": {}}
    for c, nm in div_codes.items():
        sub = {m: me[c][m] for m in common}
        r = returns_from_levels(sub, common)
        dd, _ = max_drawdown(sub)
        item = {
            "name": nm, "cagr": cagr(sub, common),
            "vol": statistics.stdev(r.values()) * 12**0.5, "max_dd": dd,
        }
        out["div_compare"]["items"][c] = item
        print(f"  {c} {nm:14s} {common[0]}→{common[-1]}  年化={item['cagr']:7.2%}  "
              f"波动={item['vol']:6.2%}  最大回撤={dd:6.1%}")

    # ---------- 3. QDII 损耗 ----------
    print()
    print("=" * 92)
    print("【3】QDII 包装损耗校准")
    print("=" * 92)
    out["drag"] = drag
    out["calibration"] = cal
    for tag, a in (("纳指 513100", "NDX"), ("标普 513500", "SPX")):
        c = cal[a]
        print(f"  {tag}: 重叠 {c['start']}→{c['end']}  真实 {c['cagr_real']:.2%} vs "
              f"合成 {c['cagr_syn']:.2%}  → 采用损耗 −{drag[a]:.2%}/年")

    # ---------- 4. 策略对比 ----------
    print()
    print("=" * 92)
    print("【4】阶段一 40→50 岁滚动 10 年定投（每月 8,333 元 / 累计 100 万）")
    print("=" * 92)
    print(f"  {'策略':20s} {'窗口':>4s} {'IRR最差':>8s} {'IRR p10':>8s} {'IRR中位':>8s} "
          f"{'IRR p90':>8s} {'终值中位':>9s} {'终值最差':>9s} {'回撤中位':>8s} {'回撤最深':>8s}")
    out["strategies"] = {}
    for name, g in glides.items():
        runs = rolling(g, rets, all_months, CONTRIB_MONTHS)
        if not runs:
            continue
        irr = [r["irr"] for r in runs]
        fin = [r["final"] for r in runs]
        dd = [r["nav_max_dd"] for r in runs]
        e = {
            "label": g.label, "n": len(runs),
            "first_start": runs[0]["start_month"], "last_start": runs[-1]["start_month"],
            "irr": {"min": min(irr), "p10": pct(irr, .1), "median": statistics.median(irr),
                    "p90": pct(irr, .9), "max": max(irr)},
            "final": {"min": min(fin), "p10": pct(fin, .1),
                      "median": statistics.median(fin), "p90": pct(fin, .9), "max": max(fin)},
            "dd": {"median": statistics.median(dd), "worst": min(dd)},
            "stages": [[lo, hi, w] for lo, hi, w in g.stages],
        }
        out["strategies"][name] = e
        print(f"  {name:20s} {e['n']:4d} {e['irr']['min']:8.2%} {e['irr']['p10']:8.2%} "
              f"{e['irr']['median']:8.2%} {e['irr']['p90']:8.2%} "
              f"{e['final']['median']/1e4:8.0f}万 {e['final']['min']/1e4:8.0f}万 "
              f"{e['dd']['median']:8.1%} {e['dd']['worst']:8.1%}")

    # ---------- 5. 推荐策略各阶段年化 ----------
    print()
    print("=" * 92)
    print(f"【5】{RECOMMENDED} 各阶段配置的滚动 10 年年化分布")
    print("=" * 92)
    out["stages"] = []
    for lo, hi, w in rec.stages:
        st = stage_returns(w, rets, all_months, 10)
        desc = " / ".join(f"{NAMES[a]} {v:.0%}" for a, v in w.items())
        out["stages"].append({
            "age_from": lo, "age_to": hi, "weights": w, "desc": desc, "stats": st,
        })
        print(f"  {lo}-{hi}岁  {desc:34s} n={st['n']:3d}  最差={st['min']:7.2%} "
              f"p10={st['p10']:7.2%} 中位={st['median']:7.2%} p90={st['p90']:7.2%} "
              f"最好={st['max']:7.2%}  回撤中位={st['dd_median']:6.1%}")

    # ---------- 5b. 停投期 11 年 ----------
    print()
    print("=" * 92)
    print(f"【5b】阶段二 50→60 岁：停止投入、按滑翔路径持有 {HOLD_MONTHS//12} 年（滚动窗口）")
    print("=" * 92)
    out["phase2"] = {}
    for name in (RECOMMENDED, "yyang基准", "激进C·全美股无红利"):
        runs = rolling(glides[name], rets, all_months, HOLD_MONTHS, contrib_months=0,
                       monthly_contrib=0.0, start_age=50, initial=1.0)
        ann = [r["growth"] ** (12 / HOLD_MONTHS) - 1 for r in runs]
        dd = [r["nav_max_dd"] for r in runs]
        e = {
            "n": len(runs), "min": min(ann), "p10": pct(ann, .1),
            "median": statistics.median(ann), "p90": pct(ann, .9), "max": max(ann),
            "dd_median": statistics.median(dd), "dd_worst": min(dd),
        }
        out["phase2"][name] = e
        print(f"  {name:20s} n={e['n']:3d}  {HOLD_MONTHS//12}年年化 最差={e['min']:7.2%} "
              f"p10={e['p10']:7.2%} 中位={e['median']:7.2%} p90={e['p90']:7.2%} "
              f"最好={e['max']:7.2%}  回撤中位={e['dd_median']:6.1%}")

    # ---------- 6. 逐年测算表 ----------
    print()
    print("=" * 92)
    print("【6】逐年测算（悲观=各阶段 p10，中性=中位，乐观=p90）")
    print("=" * 92)
    scen_rates = {}
    for tag, key in (("悲观", "p10"), ("中性", "median"), ("乐观", "p90")):
        scen_rates[tag] = [
            (s["age_from"], min(s["age_to"], 60), s["stats"][key]) for s in out["stages"]
        ]
    tables = {t: year_table(r) for t, r in scen_rates.items()}
    out["year_tables"] = tables
    out["scen_rates"] = {
        t: [{"age_from": a, "age_to": b, "rate": r} for a, b, r in rs]
        for t, rs in scen_rates.items()
    }
    print(f"  {'到达年龄':>8s} {'当年投入':>9s} {'累计本金':>9s} "
          f"{'悲观年末':>10s} {'中性年末':>10s} {'乐观年末':>10s}")
    for i in range(len(tables["中性"])):
        r_mid = tables["中性"][i]
        print(f"  {r_mid['age_end']:6d}岁 {r_mid['contrib_year']/1e4:8.0f}万 "
              f"{r_mid['invested']/1e4:8.0f}万 "
              f"{tables['悲观'][i]['end']/1e4:9.0f}万 {r_mid['end']/1e4:9.0f}万 "
              f"{tables['乐观'][i]['end']/1e4:9.0f}万")

    # ---------- 7. 完整真实路径 ----------
    print()
    print("=" * 92)
    print("【7】完整真实路径：2007-02 起投（40岁），投 10 年，持有到 2026-07（59.5岁）")
    print("=" * 92)
    full = [m for m in all_months if m >= "2007-02"]
    out["full_path"] = {}
    for name in (RECOMMENDED, "yyang基准", "激进C·全美股无红利"):
        r = simulate(glides[name], rets, full)
        out["full_path"][name] = {
            "value_at_50": r["value_at_50"], "final": r["final"],
            "contributed": r["contributed"], "irr": r["irr"],
            "nav_max_dd": r["nav_max_dd"], "multiple": r["multiple"],
        }
        if name == RECOMMENDED:
            out["full_path"][name]["equity"] = r["equity"]
            out["full_path"][name]["months"] = full
        print(f"  {name:20s} 50岁={r['value_at_50']/1e4:6.0f}万  "
              f"59.5岁={r['final']/1e4:6.0f}万  IRR={r['irr']:6.2%}  "
              f"策略最大回撤={r['nav_max_dd']:6.1%}")

    # ---------- 8. 敏感性 ----------
    print()
    print("=" * 92)
    print("【8】敏感性：红利 +1.5%/年、美股 −3%/年")
    print("=" * 92)
    out["sensitivity"] = {}
    combos = [("基准", 0.0, 0.0), ("红利+1.5%", 0.015, 0.0),
              ("美股-3%", 0.0, 0.03), ("红利+1.5%·美股-3%", 0.015, 0.03)]
    print(f"  {'情景':20s} {'推荐IRR中位':>11s} {'推荐IRR最差':>11s} "
          f"{'yyang中位':>10s} {'59.5岁终值':>11s}")
    for tag, db, hc in combos:
        r2, _, m2, _ = build_universe(db, hc)
        runs = rolling(rec, r2, m2, CONTRIB_MONTHS)
        irr = [r["irr"] for r in runs]
        y_runs = rolling(glides["yyang基准"], r2, m2, CONTRIB_MONTHS)
        y_irr = [r["irr"] for r in y_runs]
        fp = simulate(rec, r2, [m for m in m2 if m >= "2007-02"])
        e = {
            "irr_median": statistics.median(irr), "irr_min": min(irr),
            "irr_p10": pct(irr, .1),
            "yyang_irr_median": statistics.median(y_irr),
            "full_final": fp["final"], "full_irr": fp["irr"],
        }
        out["sensitivity"][tag] = e
        print(f"  {tag:20s} {e['irr_median']:11.2%} {e['irr_min']:11.2%} "
              f"{e['yyang_irr_median']:10.2%} {e['full_final']/1e4:10.0f}万")

    if args.json:
        Path(args.json).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 {args.json}")


if __name__ == "__main__":
    main()
