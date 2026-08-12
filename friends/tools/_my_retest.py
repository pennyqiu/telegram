#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
我的独立复测：不重复文章脚本，从三个新角度切入
  ① Bootstrap 置信区间：溢价桶效应量到底显不显著（文章只给了点估计）
  ② Regime 分割：把 2020-2026 按年切段，看规律在不同时期是否稳定
  ③ 溢价 ↔ 汇率联动：高溢价是不是也隐含着贬值预期？
  ④ 结构性机会的年化定价：给每条策略一个可比较的期望值

数据来源：本地缓存的 A 股场内价格 + 单位净值（腾讯/东财），
Frankfurter USDCNY 日频。全部本地可复现。
"""
from __future__ import annotations

import json
import math
import random
import statistics
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / ".bt_cache" / "retest"
OUT = ROOT / "tools" / "_my_retest_out.json"
CST = timezone(timedelta(hours=8))
random.seed(20260812)


def get(url, tries=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.3 * (i + 1))
    raise RuntimeError(last)


def load_price(code):
    return json.loads((CACHE / f"cn_{code}.json").read_text(encoding="utf-8"))


def load_nav(code):
    return json.loads((CACHE / f"nav_{code}.json").read_text(encoding="utf-8"))


def fetch_fx():
    """Frankfurter USDCNY 分年拉取，缓存拼接。"""
    p = CACHE / "fx_usdcny.json"
    if p.exists() and time.time() - p.stat().st_mtime < 6 * 3600:
        return json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for yr in range(2018, 2027):
        try:
            url = f"https://api.frankfurter.app/{yr}-01-01..{yr}-12-31?from=USD&to=CNY"
            d = json.loads(get(url))
            for k, v in d.get("rates", {}).items():
                out[k] = v["CNY"]
            time.sleep(0.4)
        except Exception as e:  # noqa: BLE001
            print("fx err", yr, e)
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def build_series(code):
    """返回 [(date, price, nav, premium)]"""
    px = load_price(code)
    nav = load_nav(code)
    days = sorted(set(px) & set(nav))
    rows = []
    for d in days:
        if nav[d] <= 0:
            continue
        pr = px[d] / nav[d] - 1
        if abs(pr) > 0.35:
            continue
        rows.append((d, px[d], nav[d], pr))
    return rows


def bootstrap_ci(vals, stat_fn, n=2000, alpha=0.05):
    if len(vals) < 30:
        return None
    m = len(vals)
    est = stat_fn(vals)
    boots = []
    for _ in range(n):
        s = [vals[random.randrange(m)] for _ in range(m)]
        boots.append(stat_fn(s))
    boots.sort()
    lo = boots[int(alpha / 2 * n)]
    hi = boots[int((1 - alpha / 2) * n) - 1]
    return est, lo, hi


def bucket_fwd(series, horizon=60):
    """按当日溢价分桶，看 horizon 后的 (市价收益 - 净值收益)。"""
    buckets = defaultdict(list)
    n = len(series)
    for i in range(n - horizon):
        pr = series[i][3]
        p0, n0 = series[i][1], series[i][2]
        p1, n1 = series[i + horizon][1], series[i + horizon][2]
        excess = (p1 / p0 - 1) - (n1 / n0 - 1)
        if pr < 0:
            key = "折价 <0%"
        elif pr < 0.01:
            key = "0~1%"
        elif pr < 0.02:
            key = "1~2%"
        elif pr < 0.05:
            key = "2~5%"
        else:
            key = ">5%"
        buckets[key].append(excess)
    return buckets


def regime_split(series, horizon=60):
    """把每一天打上 regime 标签（年份），返回每 regime 每桶的均值。"""
    by_year = defaultdict(list)
    n = len(series)
    for i in range(n - horizon):
        d, p0, n0, pr = series[i]
        _, p1, n1, _ = series[i + horizon]
        excess = (p1 / p0 - 1) - (n1 / n0 - 1)
        yr = int(d[:4])
        if pr < 0.02:
            g = "lt2"
        elif pr < 0.05:
            g = "2-5"
        else:
            g = "gt5"
        by_year[(yr, g)].append(excess)
    return by_year


def fx_link(series, fx):
    """溢价 vs 未来 20 日汇率贬值：如果高溢价 = 隐含贬值预期，二者应正相关。"""
    fx_days = sorted(fx)
    fx_arr = [(d, fx[d]) for d in fx_days]
    fx_map = {d: v for d, v in fx_arr}

    def fx_ret(d0, d1):
        try:
            v0 = fx_map[d0]
        except KeyError:
            v0 = None
            for dd in fx_days:
                if dd <= d0:
                    v0 = fx_map[dd]
                else:
                    break
        v1 = None
        for dd in fx_days:
            if dd <= d1:
                v1 = fx_map[dd]
            else:
                break
        if v0 is None or v1 is None:
            return None
        return v1 / v0 - 1

    pairs = []
    for i in range(len(series) - 20):
        d0, _, _, pr = series[i]
        d1 = series[i + 20][0]
        fxr = fx_ret(d0, d1)
        if fxr is not None:
            pairs.append((pr, fxr))
    if len(pairs) < 100:
        return None
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    corr = None if den == 0 else num / den
    # 按溢价档分组看汇率变化
    grp = defaultdict(list)
    for pr, fxr in pairs:
        if pr < 0.02:
            g = "lt2"
        elif pr < 0.05:
            g = "2-5"
        else:
            g = "gt5"
        grp[g].append(fxr)
    return {
        "corr_prem_vs_fx20d": None if corr is None else round(corr, 4),
        "n": len(pairs),
        "by_bucket": {k: {"n": len(v),
                          "mean_pp": round(statistics.mean(v) * 100, 3),
                          "median_pp": round(statistics.median(v) * 100, 3)}
                      for k, v in grp.items()},
    }


def wait_ev(cur_premium, half_life_days, decay_per_day=None):
    """在当前溢价 p0，等 T 日后期望溢价 = p0 * phi^T。
    半生期 h => phi = 0.5^(1/h)。给一张等待成本表：
      T=0/1/5/10/15/20 日的期望剩余溢价、以及期望节省 = p0 - E[p]
    """
    phi = 0.5 ** (1 / half_life_days) if half_life_days else 0
    rows = []
    for T in [0, 1, 5, 10, 15, 20]:
        E = cur_premium * (phi ** T)
        rows.append({"wait_days": T, "expected_prem_pct": round(E * 100, 3),
                     "expected_saving_pp": round((cur_premium - E) * 100, 3)})
    return rows


def analyze_code(code, name, fx):
    series = build_series(code)
    if len(series) < 300:
        return {"code": code, "error": "short"}

    buckets = bucket_fwd(series, 60)
    bucket_stats = {}
    for k, vals in buckets.items():
        ci = bootstrap_ci(vals, statistics.mean)
        if not ci:
            continue
        est, lo, hi = ci
        bucket_stats[k] = {
            "n": len(vals),
            "mean_pct": round(est * 100, 3),
            "ci95_pct": [round(lo * 100, 3), round(hi * 100, 3)],
            "significant_neg": hi < 0,
            "significant_pos": lo > 0,
            "win_pct": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        }

    reg = regime_split(series, 60)
    by_year = defaultdict(dict)
    for (yr, g), vals in reg.items():
        if len(vals) < 20:
            continue
        by_year[yr][g] = {"n": len(vals), "mean_pct": round(statistics.mean(vals) * 100, 3)}

    fx_result = fx_link(series, fx)

    # AR(1) 半生期（再算一次自证）
    xs = [series[i][3] for i in range(len(series) - 1)]
    ys = [series[i + 1][3] for i in range(len(series) - 1)]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    varx = sum((x - mx) ** 2 for x in xs)
    phi = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs))) / varx if varx else 0
    half = math.log(0.5) / math.log(abs(phi)) if 0 < abs(phi) < 1 else None

    return {
        "code": code, "name": name,
        "n_days": len(series),
        "start": series[0][0], "end": series[-1][0],
        "prem_median_pct": round(statistics.median(x[3] for x in series) * 100, 3),
        "prem_p90_pct": round(sorted(x[3] for x in series)[int(0.9 * len(series))] * 100, 3),
        "share_gt5_pct": round(sum(1 for x in series if x[3] >= 0.05) / len(series) * 100, 1),
        "share_lt2_pct": round(sum(1 for x in series if x[3] < 0.02) / len(series) * 100, 1),
        "ar1_phi": round(phi, 4),
        "half_life_days": None if half is None else round(half, 2),
        "buckets_with_ci": bucket_stats,
        "by_year": {int(k): v for k, v in by_year.items()},
        "fx_link": fx_result,
    }


def structural_pricing(results):
    """给每个结构性机会打个数字标签。"""
    # 当前场内实际溢价（来自 qdii-premium.json）
    prem_now = json.loads((ROOT / "qdii-premium.json").read_text(encoding="utf-8"))
    items = prem_now.get("items", [])
    ndx_min = min(it["premium_pct"] / 100 for it in items if it["group"] == "纳指100")
    spx_min = min(it["premium_pct"] / 100 for it in items if it["group"] == "标普500")

    half_ndx = results["513100"]["half_life_days"]
    half_spx = results["513500"]["half_life_days"]

    s1_ndx = wait_ev(ndx_min, half_ndx)
    s1_spx = wait_ev(spx_min, half_spx)

    # S6 渠道切换的年化: 假设每年场内定投平均溢价 x%, 场外 QQQ 溢价 0
    # 从文章 T0 平均买入溢价 1.35%（长期）；当下若维持红线，年化机会成本 = 若被迫买入的溢价 * 12次/年 / 12月摊薄
    # 更实操：如果高溢价持续 M 个月，那期间被迫买入的钱损失 = 溢价 - 半生期后期望剩余
    # 给一个具体量：当下 9.24% 溢价的 QDII vs QQQ 零溢价，20 日预期溢价压缩 ~2.2pp
    # → 若通过美股账户买 QQQ，一年内可能节省 ~ 5% * 一年内高溢价月份占比

    return {
        "current_premium": {"ndx_min": ndx_min, "spx_min": spx_min},
        "wait_expected_saving_ndx": s1_ndx,
        "wait_expected_saving_spx": s1_spx,
        "s6_channel_cost_pp_year": {
            "assumption": "假设一年有 3 个月场内溢价 >5%，平均 8%，若被迫定投则每月 8% 亏损、20 日后回落 2.2pp",
            "cost_estimate_pp": round(3 / 12 * (0.08 - 0.022) * 100, 2),
            "note": "换到美股账户可完全避免这部分税，加汇率成本 <0.3%",
        },
    }


def main():
    fx = fetch_fx()
    print(f"FX 载入 {len(fx)} 日")
    codes = [("513100", "国泰纳指"), ("513500", "博时标普"),
             ("159941", "广发纳指"), ("513650", "南方标普")]
    out = {"generated_at": datetime.now(CST).isoformat(timespec="seconds"),
           "method": "本地缓存的 A 股场内价 ÷ 单位净值(朴素溢价) + Frankfurter USDCNY",
           "funds": {}}
    for code, name in codes:
        print("== analyze", code, name)
        try:
            out["funds"][code] = analyze_code(code, name, fx)
        except Exception as e:  # noqa: BLE001
            out["funds"][code] = {"error": str(e)}
            print(" err", e)

    out["pricing"] = structural_pricing(out["funds"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)

    # 摘要打印
    print("\n=== 摘要 ===")
    for c, v in out["funds"].items():
        if "error" in v:
            continue
        print(f"\n{c} {v['name']}  样本 {v['start']}~{v['end']} n={v['n_days']}")
        print(f"  溢价中位 {v['prem_median_pct']}% / P90 {v['prem_p90_pct']}% / >5%占比 {v['share_gt5_pct']}%")
        print(f"  AR1 φ={v['ar1_phi']}  半生期 {v['half_life_days']} 日")
        print("  60日超额（bootstrap 95%CI）:")
        for k in ["折价 <0%", "0~1%", "1~2%", "2~5%", ">5%"]:
            b = v["buckets_with_ci"].get(k)
            if not b:
                continue
            sig = "***" if b["significant_neg"] else ("+++" if b["significant_pos"] else "")
            print(f"    {k:>8}  mean={b['mean_pct']:+6.2f}%  CI=[{b['ci95_pct'][0]:+.2f}, {b['ci95_pct'][1]:+.2f}]  n={b['n']:>4}  win={b['win_pct']:>4.1f}%  {sig}")
        fxr = v.get("fx_link")
        if fxr:
            print(f"  溢价↔20日USDCNY变化 corr={fxr['corr_prem_vs_fx20d']}")
            for g in ["lt2", "2-5", "gt5"]:
                b = fxr["by_bucket"].get(g, {})
                print(f"    {g:>5}: 未来20日汇率变化 mean={b.get('mean_pp')}pp n={b.get('n')}")

    print("\n=== 当下等待价值 ===")
    p = out["pricing"]
    print(f"纳指 QDII 当前最低溢价 {p['current_premium']['ndx_min']*100:.2f}%")
    for r in p["wait_expected_saving_ndx"]:
        print(f"  等 {r['wait_days']:>2}日: 期望溢价 {r['expected_prem_pct']:>5.2f}%  节省 {r['expected_saving_pp']:>5.2f}pp")


if __name__ == "__main__":
    main()
