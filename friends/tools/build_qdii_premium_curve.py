#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5 只场内纳指100 QDII 近三年逐交易日溢价曲线：算数据 + 生成自包含 HTML。

口径（与 backtest_qdii_true_premium.py 一致）
------------------------------------------
公开口径 naive = 不复权收盘价 / 当日披露单位净值 − 1
    这是各家 App、行情软件显示的那个数，但它混入了「隔夜标的涨跌」噪音：
    美股夜里大涨 → 场内价先反应、披露净值还是旧的 → 显示成假溢价。

真实口径 true  = 不复权收盘价 / NAV_est − 1
    NAV_est(D) = 单位净值(D) × 基准RMB(cur) / 基准RMB(ref)
      cur = D 之前最后一个美股交易日（A股收盘时已知的最新信息）
      ref = 披露净值实际参考的那场美股收盘，用「净值日收益 vs 基准RMB日收益」
            在 A0/A1/A2 三种对齐下的相关性择优判定，不靠假设
    基准 = QQQ 美元收盘 × USDCNY

数据来自 fetch_qdii_quant_data.py 落盘的 CSV，本脚本不联网：
    backtest_data/raw_price/{code}.csv  不复权收盘（溢价分子）
    backtest_data/nav/{code}.csv        单位净值（溢价分母）
    backtest_data/nav_acc/{code}.csv    累计净值（判定净值参考时点，避开分红/折算干扰）
    backtest_data/QQQ.csv  backtest_data/USDCNY.csv

输出：
    friends/qdii-premium-curve.json   数据与统计
    friends/qdii-premium-curve.html   自包含页面（数据内联，可直接双击/转发）

用法：
    python3 friends/tools/build_qdii_premium_curve.py
    python3 friends/tools/build_qdii_premium_curve.py --years 3

仅供研究，非投资建议。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
DATA_DIR = TOOLS_DIR / "backtest_data"
OUT_DIR = TOOLS_DIR.parent
WATCHLIST = TOOLS_DIR / "qdii_watchlist.json"

# 展示顺序 = 用户给定顺序；颜色沿用 matplotlib tab10，与项目其他图一致
FUNDS: list[dict[str, str]] = [
    {"code": "513870", "manager": "富国", "color": "#1f77b4"},
    {"code": "159696", "manager": "易方达", "color": "#d62728"},
    {"code": "513390", "manager": "博时", "color": "#2ca02c"},
    {"code": "159660", "manager": "汇添富", "color": "#ff7f0e"},
    {"code": "159501", "manager": "嘉实", "color": "#9467bd"},
]

BUY_TH = 2.0      # 溢价 <2% 可投
CAUTION_TH = 5.0  # 2%~5% 谨慎，>5% 不投
CANDS = ["A0", "A1", "A2"]


# ---------------------------------------------------------------- 读数据

def read_series(path: Path, col: str) -> dict[str, float]:
    if not path.exists():
        raise SystemExit(f"缺少数据文件：{path}\n先跑 fetch_qdii_quant_data.py")
    out: dict[str, float] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                v = float(row[col])
            except (TypeError, ValueError):
                continue
            if v > 0:
                out[row["date"]] = v
    return out


def load_watchlist() -> dict[str, dict[str, Any]]:
    cfg = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    return {str(it["code"]): it for it in cfg["items"]}


# ------------------------------------------------- 基准（人民币口径）

class BenchRMB:
    """QQQ 美元收盘 × USDCNY = 人民币口径基准，并提供美股交易日的前后查找。"""

    def __init__(self, bench: dict[str, float], fx: dict[str, float]) -> None:
        self.us_dates = sorted(bench)
        self.fx_dates = sorted(fx)
        self.fx = fx
        self._rmb: dict[str, float] = {}
        for d in self.us_dates:
            r = self._fx_on_or_before(d)
            if r:
                self._rmb[d] = bench[d] * r

    @staticmethod
    def _last_le(arr: list[str], d: str) -> str | None:
        lo, hi, best = 0, len(arr) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if arr[mid] <= d:
                best = arr[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def _fx_on_or_before(self, d: str) -> float | None:
        k = self._last_le(self.fx_dates, d)
        return self.fx.get(k) if k else None

    def rmb(self, us_date: str | None) -> float | None:
        return self._rmb.get(us_date) if us_date else None

    def us_on_or_before(self, d: str) -> str | None:
        return self._last_le(self.us_dates, d)

    def us_before(self, d: str, back: int = 1) -> str | None:
        """d 之前第 back 个美股交易日（back=1 → 收在 d 当天凌晨的那场）。"""
        lo, hi, idx = 0, len(self.us_dates) - 1, -1
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.us_dates[mid] < d:
                idx = mid
                lo = mid + 1
            else:
                hi = mid - 1
        j = idx - (back - 1)
        return self.us_dates[j] if 0 <= j < len(self.us_dates) else None

    def ref_for(self, d: str, cand: str) -> str | None:
        if cand == "A0":
            return self.us_on_or_before(d)
        if cand == "A1":
            return self.us_before(d, 1)
        if cand == "A2":
            return self.us_before(d, 2)
        return None


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def detect_lag(acc: dict[str, float], br: BenchRMB, start: str) -> dict[str, Any]:
    """净值参考的是哪一场美股收盘：让相关性说话，不靠假设。"""
    ds = [d for d in sorted(acc) if d >= start]
    corr: dict[str, float] = {}
    for cand in CANDS:
        xs, ys = [], []
        for i in range(1, len(ds)):
            d0, d1 = ds[i - 1], ds[i]
            n0, n1 = acc[d0], acc[d1]
            r0, r1 = br.ref_for(d0, cand), br.ref_for(d1, cand)
            b0, b1 = br.rmb(r0), br.rmb(r1)
            if not b0 or not b1 or r0 == r1:
                continue
            xs.append(n1 / n0 - 1.0)
            ys.append(b1 / b0 - 1.0)
        corr[cand] = pearson(xs, ys)
    valid = {k: v for k, v in corr.items() if v == v}
    best = max(valid, key=lambda k: valid[k]) if valid else "A1"
    return {"corr": {k: (None if v != v else round(v, 4)) for k, v in corr.items()},
            "best": best}


# ---------------------------------------------------------------- 统计

def quantile(sv: list[float], q: float) -> float:
    """线性插值分位数，sv 需已排序。"""
    if not sv:
        return float("nan")
    if len(sv) == 1:
        return sv[0]
    pos = q * (len(sv) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sv) - 1)
    return sv[lo] + (sv[hi] - sv[lo]) * (pos - lo)


def stats_of(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    sv = sorted(vals)
    n = len(vals)
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    return {
        "n": n,
        "min": round(sv[0], 3),
        "p10": round(quantile(sv, 0.10), 3),
        "median": round(quantile(sv, 0.50), 3),
        "mean": round(mean, 3),
        "p90": round(quantile(sv, 0.90), 3),
        "max": round(sv[-1], 3),
        "sd": round(sd, 3),
        "share_neg": round(sum(1 for v in vals if v < 0) / n * 100, 1),
        "share_lt2": round(sum(1 for v in vals if v < BUY_TH) / n * 100, 1),
        "share_2_5": round(sum(1 for v in vals if BUY_TH <= v < CAUTION_TH) / n * 100, 1),
        "share_gt5": round(sum(1 for v in vals if v >= CAUTION_TH) / n * 100, 1),
    }


def hist_of(vals: list[float], edges: list[float]) -> list[int]:
    """落入 (-inf,e0], (e0,e1], ... , (elast,+inf) 各桶的天数。"""
    out = [0] * (len(edges) + 1)
    for v in vals:
        idx = len(edges)
        for i, e in enumerate(edges):
            if v <= e:
                idx = i
                break
        out[idx] += 1
    return out


def neg_episodes(rows: list[tuple[str, float]]) -> list[dict[str, Any]]:
    """连续折价段：起止日、交易日数、自然日跨度、段内最低溢价。"""
    eps: list[dict[str, Any]] = []
    cur: list[tuple[str, float]] = []
    for d, v in rows:
        if v < 0:
            cur.append((d, v))
        elif cur:
            eps.append(_close_ep(cur))
            cur = []
    if cur:
        eps.append(_close_ep(cur))
    return eps


def _close_ep(seg: list[tuple[str, float]]) -> dict[str, Any]:
    d0, d1 = seg[0][0], seg[-1][0]
    span = (datetime.strptime(d1, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days + 1
    return {
        "start": d0, "end": d1,
        "trading_days": len(seg),
        "calendar_days": span,
        "min": round(min(v for _, v in seg), 3),
    }


# ---------------------------------------------------------------- 主流程

def build(years: float) -> dict[str, Any]:
    wl = load_watchlist()
    bench = read_series(DATA_DIR / "QQQ.csv", "close")
    fx = read_series(DATA_DIR / "USDCNY.csv", "close")
    br = BenchRMB(bench, fx)

    raw: dict[str, dict[str, float]] = {}
    nav: dict[str, dict[str, float]] = {}
    acc: dict[str, dict[str, float]] = {}
    for f in FUNDS:
        c = f["code"]
        raw[c] = read_series(DATA_DIR / "raw_price" / f"{c}.csv", "close")
        nav[c] = read_series(DATA_DIR / "nav" / f"{c}.csv", "nav")
        acc[c] = read_series(DATA_DIR / "nav_acc" / f"{c}.csv", "acc")

    # 区间：截止日取「各基金价格与净值都有数」的最新一天里最早的那个，保证 5 条线同步收尾
    end = min(max(d for d in raw[f["code"]] if d in nav[f["code"]]) for f in FUNDS)
    end_d = datetime.strptime(end, "%Y-%m-%d").date()
    start_d = end_d - timedelta(days=round(365.25 * years))
    start = start_d.isoformat()

    lags = {f["code"]: detect_lag(acc[f["code"]], br, start) for f in FUNDS}

    # 逐基金逐日溢价（各自全部可得历史，图表用）
    series: dict[str, dict[str, dict[str, float]]] = {}
    for f in FUNDS:
        c = f["code"]
        cand = lags[c]["best"]
        per_day: dict[str, dict[str, float]] = {}
        for d in sorted(nav[c]):
            if d < start or d > end or d not in raw[c]:
                continue
            price, unit = raw[c][d], nav[c][d]
            rec = {"naive": (price / unit - 1.0) * 100.0}
            b_cur = br.rmb(br.us_before(d, 1))
            b_ref = br.rmb(br.ref_for(d, cand))
            if b_cur and b_ref:
                rec["true"] = (price / (unit * b_cur / b_ref) - 1.0) * 100.0
                rec["adj"] = (b_cur / b_ref - 1.0) * 100.0
            per_day[d] = rec
        series[c] = per_day

    dates = sorted({d for c in series for d in series[c]})

    # 513870 上市最晚，跨基金的次数/天数若各用自己的起点就不可比，
    # 故所有横向统计都统一在「5 只都有数据」的区间上做，曲线仍展示各自全历史。
    common_start = max(min(series[f["code"]]) for f in FUNDS)

    hist_edges = [0.0, 1.0, 2.0, 5.0]
    hist_labels = ["折价 <0%", "0~1%", "1~2%", "2~5%", ">5%"]

    funds_out: list[dict[str, Any]] = []
    for f in FUNDS:
        c = f["code"]
        per_day = {d: v for d, v in series[c].items() if d >= common_start}
        ds = sorted(per_day)
        naive_rows = [(d, per_day[d]["naive"]) for d in ds]
        true_rows = [(d, per_day[d]["true"]) for d in ds if "true" in per_day[d]]
        naive_vals = [v for _, v in naive_rows]
        true_vals = [v for _, v in true_rows]

        # 信号翻转：两个口径给出不同的「能不能买」结论
        both = [(per_day[d]["naive"], per_day[d]["true"]) for d in ds if "true" in per_day[d]]
        flip = sum(1 for a, b in both if (a < BUY_TH) != (b < BUY_TH))
        false_green = sum(1 for a, b in both if a < BUY_TH <= b)

        eps_naive = neg_episodes(naive_rows)
        eps_true = neg_episodes(true_rows)
        latest = ds[-1] if ds else None

        funds_out.append({
            "code": c,
            "name": wl[c]["name"],
            "manager": f["manager"],
            "color": f["color"],
            "fee_total_pct": round(wl[c]["fee_mgmt_pct"] + wl[c]["fee_custody_pct"], 2),
            "first_day": min(series[c]) if series[c] else None,
            "start": ds[0] if ds else None,
            "end": latest,
            "latest_naive": round(per_day[latest]["naive"], 3) if latest else None,
            "latest_true": (round(per_day[latest]["true"], 3)
                            if latest and "true" in per_day[latest] else None),
            "nav_ref": lags[c]["best"],
            "nav_ref_corr": lags[c]["corr"],
            "stats_naive": stats_of(naive_vals),
            "stats_true": stats_of(true_vals),
            "hist_naive": hist_of(naive_vals, hist_edges),
            "hist_true": hist_of(true_vals, hist_edges),
            "flip_days": flip,
            "flip_share": round(flip / len(both) * 100, 1) if both else None,
            "false_green_days": false_green,
            "neg_naive": {
                "episodes": len(eps_naive),
                "days": sum(e["trading_days"] for e in eps_naive),
                "longest": sorted(eps_naive, key=lambda e: (-e["calendar_days"],
                                                            -e["trading_days"]))[:3],
            },
            "neg_true": {
                "episodes": len(eps_true),
                "days": sum(e["trading_days"] for e in eps_true),
                "longest": sorted(eps_true, key=lambda e: (-e["calendar_days"],
                                                           -e["trading_days"]))[:3],
            },
            "curve_naive": [(round(series[c][d]["naive"], 3) if d in series[c] else None)
                            for d in dates],
            "curve_true": [(round(series[c][d]["true"], 3)
                            if d in series[c] and "true" in series[c][d] else None)
                           for d in dates],
        })

    # 同一天 5 只之间的溢价价差：换一只基金能省多少
    spread: list[dict[str, Any]] = []
    for kind in ("naive", "true"):
        vals: list[float] = []
        cheapest: dict[str, int] = {f["code"]: 0 for f in FUNDS}
        n_days = 0
        for d in dates:
            row = [(f["code"], series[f["code"]][d][kind])
                   for f in FUNDS
                   if d in series[f["code"]] and kind in series[f["code"]][d]]
            if len(row) < len(FUNDS):
                continue
            n_days += 1
            vals.append(max(v for _, v in row) - min(v for _, v in row))
            cheapest[min(row, key=lambda t: t[1])[0]] += 1
        sv = sorted(vals)
        spread.append({
            "kind": kind,
            "n_days": n_days,
            "median": round(quantile(sv, 0.5), 3) if sv else None,
            "mean": round(sum(vals) / len(vals), 3) if vals else None,
            "p90": round(quantile(sv, 0.9), 3) if sv else None,
            "max": round(sv[-1], 3) if sv else None,
            "cheapest_share": {k: round(v / n_days * 100, 1) for k, v in cheapest.items()}
            if n_days else {},
        })

    # 溢价最高那天买进去会怎样：溢价靠场内价格下跌回落，净值不背这个锅
    payback: list[dict[str, Any]] = []
    for f in FUNDS:
        c = f["code"]
        ds = [d for d in sorted(series[c]) if d >= common_start]
        peak = max(ds, key=lambda d: series[c][d]["naive"])
        i = ds.index(peak)
        row: dict[str, Any] = {
            "code": c, "name": wl[c]["name"], "date": peak,
            "prem": round(series[c][peak]["naive"], 2),
            "after": {},
        }
        for k in (5, 10, 20):
            j = i + k
            if j >= len(ds):
                continue
            d2 = ds[j]
            row["after"][k] = {
                "date": d2,
                "prem": round(series[c][d2]["naive"], 2),
                "price_ret": round((raw[c][d2] / raw[c][peak] - 1) * 100, 2),
                "nav_ret": round((nav[c][d2] / nav[c][peak] - 1) * 100, 2),
            }
        payback.append(row)

    # 两个口径分歧最大的日子：深折价其实是「净值参考时点错位」造出来的假象
    worst: list[dict[str, Any]] = []
    for f in FUNDS:
        c = f["code"]
        cand = [(d, r["naive"], r["true"], r["adj"])
                for d, r in series[c].items() if "true" in r and d >= common_start]
        for d, nv, tv, adj in sorted(cand, key=lambda t: t[1] - t[2])[:3]:
            worst.append({"code": c, "name": wl[c]["name"], "date": d,
                          "naive": round(nv, 2), "true": round(tv, 2),
                          "adj": round(adj, 2), "gap": round(nv - tv, 2)})
    worst.sort(key=lambda r: r["gap"])

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": "5 只场内纳指100 QDII · 近三年逐日溢价曲线",
        "start": start, "end": end, "years": years,
        "common_start": common_start,
        "false_discount": worst[:6],
        "peak_payback": payback,
        "n_dates": len(dates),
        "dates": dates,
        "hist_labels": hist_labels,
        "buy_th": BUY_TH, "caution_th": CAUTION_TH,
        "method": {
            "naive": "不复权收盘价 / 当日披露单位净值 − 1（各家 App 显示的口径）",
            "true": "把净值折算到「A股收盘时已知的最新美股收盘」同一时点后再算溢价",
            "bench": "QQQ 美元收盘 × USDCNY（ECB 口径）",
            "nav_ref_cand": {
                "A0": "净值(D) 参考「美股交易日 == D」那一场（D 当晚，收在 D+1 凌晨）",
                "A1": "净值(D) 参考「D 之前最后一个美股交易日」（收在 D 当天凌晨）",
                "A2": "再往前一个美股交易日",
            },
        },
        "funds": funds_out,
        "spread": spread,
    }


# ---------------------------------------------------------------- HTML

def fmt(v: Any, digits: int = 2, suffix: str = "%") -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}{suffix}"


def signal_of(v: float | None) -> tuple[str, str]:
    if v is None:
        return "—", "gray"
    if v < 0:
        return "折价·罕见机会", "green"
    if v < BUY_TH:
        return "可投", "green"
    if v < CAUTION_TH:
        return "谨慎", "warn"
    return "不投", "red"


def render_html(d: dict[str, Any]) -> str:
    funds = d["funds"]
    # 直接调用时 after 的键是 int，经 JSON 回读后是 str，统一成 int
    for r in d["peak_payback"]:
        r["after"] = {int(k): v for k, v in r["after"].items()}
    payload = json.dumps({
        "dates": d["dates"],
        "buy_th": d["buy_th"],
        "caution_th": d["caution_th"],
        "funds": [{"code": f["code"], "name": f["name"], "color": f["color"],
                   "naive": f["curve_naive"], "true": f["curve_true"]} for f in funds],
    }, ensure_ascii=False, separators=(",", ":"))

    # 概览卡片
    cards = []
    for f in funds:
        label, tone = signal_of(f["latest_naive"])
        cards.append(
            f'<div class="card"><div class="k">{f["code"]} {f["name"]}</div>'
            f'<div class="v" style="color:{f["color"]}">{fmt(f["latest_naive"])}'
            f'<small>最新 · {d["end"]}</small></div>'
            f'<div class="kv"><span>三年中位</span><b>{fmt(f["stats_naive"]["median"])}</b></div>'
            f'<div class="kv"><span>区间</span><b>{fmt(f["stats_naive"]["min"])} ~ '
            f'{fmt(f["stats_naive"]["max"])}</b></div>'
            f'<div class="kv"><span>折价天数占比</span><b>{fmt(f["stats_naive"]["share_neg"], 1)}</b></div>'
            f'<div class="pill {tone}">{label}</div></div>'
        )

    # 分位数表
    def stat_rows(key: str) -> str:
        out = []
        for f in funds:
            s = f[key]
            out.append(
                f'<tr><td>{f["code"]}</td><td>{f["name"]}</td>'
                f'<td class="num">{s["n"]}</td>'
                f'<td class="num neg">{fmt(s["min"])}</td>'
                f'<td class="num">{fmt(s["p10"])}</td>'
                f'<td class="num"><b>{fmt(s["median"])}</b></td>'
                f'<td class="num">{fmt(s["mean"])}</td>'
                f'<td class="num">{fmt(s["p90"])}</td>'
                f'<td class="num">{fmt(s["max"])}</td>'
                f'<td class="num">{fmt(s["sd"])}</td></tr>'
            )
        return "".join(out)

    # 分布表
    def dist_rows(key: str) -> str:
        out = []
        for f in funds:
            h = f[key]
            n = sum(h)
            cells = "".join(
                f'<td class="num">{v} 天<small>{v / n * 100:.0f}%</small></td>' for v in h
            )
            out.append(f'<tr><td>{f["code"]}</td><td>{f["name"]}</td>{cells}</tr>')
        return "".join(out)

    # 折价段表
    def neg_rows(key: str, stat_key: str) -> str:
        out = []
        for f in funds:
            g = f[key]
            longest = g["longest"][0] if g["longest"] else None
            top = "；".join(
                f'{e["start"]}~{e["end"]}（{e["calendar_days"]}自然日/{e["trading_days"]}交易日，最低 {e["min"]:.2f}%）'
                for e in g["longest"][:2]
            ) or "—"
            out.append(
                f'<tr><td>{f["code"]}</td><td>{f["name"]}</td>'
                f'<td class="num">{g["episodes"]} 段</td>'
                f'<td class="num">{g["days"]} 天<small>占 {fmt(f[stat_key]["share_neg"], 1)}</small></td>'
                f'<td class="num">{longest["calendar_days"] if longest else "—"} 自然日'
                f'<small>{longest["trading_days"] if longest else "—"} 交易日</small></td>'
                f'<td style="white-space:normal;min-width:280px">{top}</td></tr>'
            )
        return "".join(out)

    def pb_row(r: dict[str, Any]) -> str:
        aft = r["after"]
        path = " → ".join([f'{r["prem"]:.2f}%']
                          + [f'{aft[k]["prem"]:.2f}%' for k in (5, 10, 20) if k in aft])
        a = aft.get(20)
        if not a:
            return ""
        gap = a["price_ret"] - a["nav_ret"]
        return (f'<tr><td>{r["code"]}</td><td>{r["name"]}</td><td>{r["date"]}</td>'
                f'<td class="num"><b>{r["prem"]:.2f}%</b></td>'
                f'<td class="num" style="white-space:normal">{path}</td>'
                f'<td class="num">{a["price_ret"]:+.2f}%</td>'
                f'<td class="num">{a["nav_ret"]:+.2f}%</td>'
                f'<td class="num neg"><b>{gap:+.2f}%</b></td></tr>')

    pb_rows = "".join(pb_row(r) for r in d["peak_payback"])

    fd_rows = "".join(
        f'<tr><td>{r["date"]}</td><td>{r["code"]}</td><td>{r["name"]}</td>'
        f'<td class="num neg">{r["naive"]:+.2f}%</td>'
        f'<td class="num">{r["true"]:+.2f}%</td>'
        f'<td class="num">{r["adj"]:+.2f}%</td>'
        f'<td class="num">{r["gap"]:.2f} 个点</td></tr>'
        for r in d["false_discount"]
    )

    # 口径差异表
    flip_rows = "".join(
        f'<tr><td>{f["code"]}</td><td>{f["name"]}</td>'
        f'<td class="num">{fmt(f["stats_naive"]["median"])}</td>'
        f'<td class="num">{fmt(f["stats_true"]["median"])}</td>'
        f'<td class="num">{fmt(f["stats_naive"]["share_neg"], 1)}</td>'
        f'<td class="num">{fmt(f["stats_true"]["share_neg"], 1)}</td>'
        f'<td class="num">{f["flip_days"]} 天<small>{fmt(f["flip_share"], 1)}</small></td>'
        f'<td class="num">{f["false_green_days"]} 天</td>'
        f'<td class="num">{f["nav_ref"]}</td></tr>'
        for f in funds
    )

    sp = {s["kind"]: s for s in d["spread"]}
    spread_rows = "".join(
        f'<tr><td>{"公开口径" if s["kind"] == "naive" else "真实口径"}</td>'
        f'<td class="num">{s["n_days"]}</td>'
        f'<td class="num"><b>{fmt(s["median"])}</b></td>'
        f'<td class="num">{fmt(s["mean"])}</td>'
        f'<td class="num">{fmt(s["p90"])}</td>'
        f'<td class="num">{fmt(s["max"])}</td></tr>'
        for s in d["spread"]
    )
    cheap_rows = "".join(
        f'<tr><td>{f["code"]}</td><td>{f["name"]}</td>'
        f'<td class="num">{fmt(sp["naive"]["cheapest_share"].get(f["code"]), 1)}</td>'
        f'<td class="num">{fmt(sp["true"]["cheapest_share"].get(f["code"]), 1)}</td>'
        f'<td class="num">{fmt(f["fee_total_pct"], 2)}</td></tr>'
        for f in funds
    )

    legend = "".join(
        f'<button class="lg on" data-code="{f["code"]}">'
        f'<i style="background:{f["color"]}"></i>{f["code"]} {f["name"]}</button>'
        for f in funds
    )
    minis = "".join(
        f'<div class="mini"><div class="mini-h">'
        f'<span style="color:{f["color"]}">{f["code"]} {f["name"]}</span>'
        f'<em>三年中位 {fmt(f["stats_naive"]["median"])} · 折价天数占 '
        f'{fmt(f["stats_naive"]["share_neg"], 1)} · 最高 {fmt(f["stats_naive"]["max"])}</em>'
        f'</div><canvas data-mini="{f["code"]}" height="120"></canvas></div>'
        for f in funds
    )

    # 结论文字里的几个数
    med_lo = min(funds, key=lambda f: f["stats_naive"]["median"])
    med_hi = max(funds, key=lambda f: f["stats_naive"]["median"])
    max_f = max(funds, key=lambda f: f["stats_naive"]["max"])
    min_f = min(funds, key=lambda f: f["stats_naive"]["min"])

    now_lo = min(funds, key=lambda f: f["latest_naive"])
    now_hi = max(funds, key=lambda f: f["latest_naive"])
    # 当前溢价在各自三年分布里的位置：比历史上多少比例的日子更贵
    now_pctl = []
    for f in funds:
        vals = [v for v in f["curve_naive"] if v is not None]
        pct = sum(1 for v in vals if v <= f["latest_naive"]) / len(vals) * 100
        now_pctl.append((f, pct))
    pct_lo = min(p for _, p in now_pctl)
    def gap20(r: dict[str, Any]) -> float:
        a = r["after"][20]
        return a["price_ret"] - a["nav_ret"]

    pb_worst = min(d["peak_payback"], key=gap20)
    pb_gaps = [gap20(r) for r in d["peak_payback"]]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{d["title"]}</title>
<style>
  :root {{ --bg:#f7f8fa; --card:#fff; --ink:#1f2329; --muted:#6b7280; --line:#e6e8eb;
           --accent:#1f77b4; --green:#057a55; --warn:#c27803; --red:#c81e1e; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",Roboto,sans-serif;
          background:var(--bg); color:var(--ink); line-height:1.6; }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:28px 20px 60px; }}
  header h1 {{ font-size:22px; margin:0 0 6px; }}
  header .meta {{ color:var(--muted); font-size:13px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(186px,1fr)); gap:12px; margin:22px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
  .card .k {{ color:var(--muted); font-size:12px; }}
  .card .v {{ font-size:22px; font-weight:700; margin:4px 0 8px; font-variant-numeric:tabular-nums; }}
  .card .v small {{ display:block; font-size:11px; color:var(--muted); font-weight:400; }}
  .card .kv {{ display:flex; justify-content:space-between; font-size:12px; color:var(--muted); }}
  .card .kv b {{ color:var(--ink); font-variant-numeric:tabular-nums; }}
  .pill {{ display:inline-block; margin-top:9px; font-size:11px; font-weight:700; padding:2px 9px; border-radius:99px; }}
  .pill.green {{ background:#def7ec; color:var(--green); }}
  .pill.warn {{ background:#fdf6b2; color:var(--warn); }}
  .pill.red {{ background:#fde8e8; color:var(--red); }}
  .pill.gray {{ background:#f3f4f6; color:var(--muted); }}
  .block {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px; margin:18px 0; }}
  .block h2 {{ margin:0 0 4px; font-size:17px; }}
  .block .hint {{ color:var(--muted); font-size:12.5px; margin:0 0 14px; }}
  .toolbar {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }}
  .seg {{ display:inline-flex; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
  .seg button {{ border:0; background:#fff; color:var(--muted); font-size:12.5px; padding:6px 12px; cursor:pointer; }}
  .seg button.on {{ background:var(--accent); color:#fff; font-weight:600; }}
  .lg {{ display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); background:#fff;
         border-radius:99px; font-size:12px; padding:4px 11px; cursor:pointer; color:var(--muted); }}
  .lg i {{ width:9px; height:9px; border-radius:50%; opacity:.28; }}
  .lg.on {{ color:var(--ink); border-color:#cfd4da; font-weight:600; }}
  .lg.on i {{ opacity:1; }}
  .chart-box {{ position:relative; }}
  canvas {{ width:100%; display:block; }}
  #tip {{ position:absolute; pointer-events:none; opacity:0; transition:opacity .1s; background:rgba(255,255,255,.97);
          border:1px solid var(--line); border-radius:8px; box-shadow:0 6px 18px rgba(0,0,0,.10);
          font-size:12px; padding:8px 10px; min-width:150px; z-index:5; }}
  #tip .d {{ color:var(--muted); margin-bottom:4px; }}
  #tip .r {{ display:flex; justify-content:space-between; gap:14px; font-variant-numeric:tabular-nums; }}
  #tip .r i {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; }}
  .minis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
  .mini {{ border:1px solid var(--line); border-radius:10px; padding:10px 12px 4px; }}
  .mini-h {{ font-size:12.5px; font-weight:700; line-height:1.4; }}
  .mini-h em {{ display:block; font-style:normal; font-weight:400; font-size:11px; color:var(--muted); }}
  .tbl {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th,td {{ padding:9px 12px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
  th {{ color:var(--muted); font-weight:600; background:#fafbfc; }}
  th.num {{ text-align:right; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.num small {{ display:block; font-size:11px; color:var(--muted); }}
  td.neg {{ color:var(--green); }}
  .sum {{ background:#fafbfc; border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:18px 0; font-size:13.5px; }}
  .sum.alert {{ background:#fef7f7; border-color:#f3c6c6; border-left:4px solid var(--red); }}
  .disc {{ font-size:12.5px; color:var(--muted); margin-top:18px; }}
  @media (max-width:640px) {{ th,td {{ padding:8px 9px; }} .wrap {{ padding:20px 12px 40px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{d["title"]}</h1>
    <div class="meta">曲线区间 {d["start"]} ~ {d["end"]}（{d["n_dates"]} 个交易日，各只按自身上市日起） ·
      横向统计统一取 5 只都有数据的 {d["common_start"]} 起 · 溢价 = 场内收盘价 / 单位净值 − 1 ·
      生成于 {d["generated_at"][:16].replace("T", " ")}</div>
  </header>

  <div class="cards">{"".join(cards)}</div>

  <div class="sum alert">
    <b>先看当下（{d["end"]}）：5 只全部落在「不投」区间。</b>
    最低的 {now_lo["name"]} {fmt(now_lo["latest_naive"])}，最高的 {now_hi["name"]}
    {fmt(now_hi["latest_naive"])}，没有一只低于 5%。放回各自近三年的分布里，
    这个价位<b>比历史上至少 {pct_lo:.0f}% 的交易日都贵</b>。
    而历史上溢价冲到这个量级之后，消化方式都是<b>场内价格补跌，不是净值上涨来追平</b>——
    下面「溢价最高那天买进去」一节的 5 个真实样本，20 个交易日内价格跑输净值
    {abs(max(pb_gaps)):.1f}%~{abs(min(pb_gaps)):.1f}%（最惨的是 {pb_worst["name"]}）。
    此时若要加仓纳指，场外申购按净值成交、不含溢价，代价明显更低；
    但场外有额度限购与确认速度的差别，需要一并权衡。
  </div>

  <div class="sum">
    <b>怎么读这张图：</b>横轴是交易日，纵轴是溢价率。<b>0 轴以下（绿色区域）是折价</b>，
    这时买场内比买净值便宜；<b>2% 以上（黄区）要谨慎，5% 以上（红区）基本不该买</b>——
    溢价是买入当天就付出的沉没成本，它会在溢价回落时原路还回去。
    三年下来 5 只的溢价中位数从 <b>{fmt(med_lo["stats_naive"]["median"])}（{med_lo["name"]}）</b>
    到 <b>{fmt(med_hi["stats_naive"]["median"])}（{med_hi["name"]}）</b>不等，
    极端值最高见过 <b>{fmt(max_f["stats_naive"]["max"])}（{max_f["name"]}）</b>、
    最低见过 <b>{fmt(min_f["stats_naive"]["min"])}（{min_f["name"]}）</b>。
    <b>同一天 5 只之间的溢价差中位数 {fmt(sp["naive"]["median"])}、极端能到 {fmt(sp["naive"]["max"])}</b>，
    也就是说「买哪一只」这个选择本身，在很多天里就值零点几个点。
  </div>

  <section class="block">
    <h2>近三年逐日溢价曲线</h2>
    <p class="hint">点图例可只看其中几只；鼠标／手指在图上移动看当日数值。
      513870 富国 {[f for f in funds if f["code"] == "513870"][0]["first_day"]} 才上市，起点晚于其余四只。</p>
    <div class="toolbar">
      <div class="seg" id="kind">
        <button class="on" data-kind="naive">公开口径（App 显示）</button>
        <button data-kind="true">真实口径（剔隔夜噪音）</button>
      </div>
      <div class="seg" id="rng">
        <button data-m="0" class="on">近 3 年</button>
        <button data-m="12">近 1 年</button>
        <button data-m="6">近 6 月</button>
        <button data-m="3">近 3 月</button>
      </div>
    </div>
    <div class="toolbar" id="legend">{legend}</div>
    <div class="chart-box">
      <canvas id="main" height="420"></canvas>
      <div id="tip"></div>
    </div>
  </section>

  <section class="block">
    <h2>5 只分开看</h2>
    <p class="hint">同一纵轴范围，便于横比；绿色为折价区间。口径随上方切换。</p>
    <div class="minis">{minis}</div>
  </section>

  <section class="block">
    <h2>溢价分位数统计（公开口径 · {d["common_start"]} 起）</h2>
    <p class="hint">中位数比均值更能代表「常态溢价」——溢价分布右偏，几天极端行情会把均值拉高。
      P10 / P90 是十分位：P10 以下算「便宜的一成日子」，P90 以上算「最贵的一成日子」。</p>
    <div class="tbl"><table>
      <thead><tr><th>代码</th><th>简称</th><th>交易日</th><th>最低</th><th>P10</th>
        <th>中位数</th><th>均值</th><th>P90</th><th>最高</th><th>标准差</th></tr></thead>
      <tbody>{stat_rows("stats_naive")}</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>溢价区间分布：能买的日子有多少</h2>
    <p class="hint">按 &lt;0% / 0~1% / 1~2% / 2~5% / &gt;5% 分档统计天数与占比（公开口径）。前三档合计即「溢价 &lt; 2% 可投」的日子。</p>
    <div class="tbl"><table>
      <thead><tr><th>代码</th><th>简称</th>{"".join(f"<th>{l}</th>" for l in d["hist_labels"])}</tr></thead>
      <tbody>{dist_rows("hist_naive")}</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>折价（负溢价）出现得有多频繁、持续多久</h2>
    <p class="hint">连续折价段 = 溢价率连续为负的一串交易日；自然日跨度含首尾两天。
      折价段大多是 1~2 天的短暂窗口，最长的几段几乎都出现在 A 股长假前后
      （休市期间美股照常交易，节后开盘需要重新定价）。
      但要留意：<b>长假造成的「折价」多半属于下一节说的那种假折价</b>，未必是真便宜。</p>
    <div class="tbl"><table>
      <thead><tr><th>代码</th><th>简称</th><th>折价段数</th><th>折价交易日</th><th>最长一段</th><th>最长的两段明细</th></tr></thead>
      <tbody>{neg_rows("neg_naive", "stats_naive")}</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>在溢价最高那天买进去，后面发生了什么</h2>
    <p class="hint">每只取它三年里溢价最高的那个交易日，看之后 20 个交易日（约一个月）的结果。
      「价格」是场内成交价的涨跌，也就是账户里的钱；「净值」是基金实际赚到的钱。
      两者之差就是<b>溢价回落吃掉的部分</b>。5 只无一例外：<b>净值该涨的照样涨，
      溢价却靠场内价格补跌来消化</b>——这笔差额由高溢价买入的人独自承担，与基金的业绩好坏无关。</p>
    <div class="tbl"><table>
      <thead><tr><th>代码</th><th>简称</th><th>溢价最高日</th><th>当日溢价</th>
        <th>溢价回落路径（当日→+5→+10→+20）</th><th>20 日价格</th><th>20 日净值</th>
        <th>价格跑输净值</th></tr></thead>
      <tbody>{pb_rows}</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>最深的那几次「折价」其实是假的</h2>
    <p class="hint">下面是两个口径分歧最大的几天。共同点是<b>隔夜标的大涨大跌</b>（末列前一栏）：
      披露净值已经反映了当晚美股那一场，而 A 股收盘时根本还看不到它，于是账面上凭空出现深折价。
      2025-04-09 是最典型的一次——关税暂缓消息让纳指单日暴涨，净值随之跳升，
      场内价格却还停在前一晚暴跌的位置，五只同时显示 8~9% 的「折价」，而按同一时点算其实都是正溢价。
      <b>这种折价是看得见吃不到的：第二天场内价格补涨，折价就消失了。</b></p>
    <div class="tbl"><table>
      <thead><tr><th>日期</th><th>代码</th><th>简称</th><th>公开口径显示</th>
        <th>真实溢价</th><th>隔夜基准涨跌</th><th>虚高幅度</th></tr></thead>
      <tbody>{fd_rows}</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>两个口径差多少：App 上的溢价会骗人吗</h2>
    <p class="hint">披露净值参考的美股收盘时点不一定等于 A 股收盘时已知的最新一场。把这个错位修掉之后，
      「溢价 &lt; 2% 能不能买」的结论会在一部分交易日发生翻转；其中<b>假绿灯</b>（App 显示 &lt;2% 但真实 ≥2%）最危险。
      末列是数据判定出的净值参考时点：{"；".join(f"{k} = {v}" for k, v in d["method"]["nav_ref_cand"].items())}。</p>
    <div class="tbl"><table>
      <thead><tr><th>代码</th><th>简称</th><th>中位·公开</th><th>中位·真实</th>
        <th>折价占比·公开</th><th>折价占比·真实</th><th>信号翻转</th><th>其中假绿灯</th><th>净值参考</th></tr></thead>
      <tbody>{flip_rows}</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>同一天买哪只：5 只之间的溢价价差</h2>
    <p class="hint">价差 = 当日 5 只里最高溢价 − 最低溢价。这就是「随手买」与「挑最便宜的买」之间的差距；
      但挑最便宜也要看流动性与费率，长期持有时每年的合计费率同样是真金白银。</p>
    <div class="tbl"><table>
      <thead><tr><th>口径</th><th>可比交易日</th><th>价差中位</th><th>均值</th><th>P90</th><th>最大</th></tr></thead>
      <tbody>{spread_rows}</tbody>
    </table></div>
    <div class="tbl" style="margin-top:14px"><table>
      <thead><tr><th>代码</th><th>简称</th><th>当日最便宜的天数占比·公开</th><th>·真实</th><th>合计费率(年)</th></tr></thead>
      <tbody>{cheap_rows}</tbody>
    </table></div>
    <p class="hint" style="margin:14px 0 0">两列占比完全相同不是笔误：数据判定出 5 只的净值参考时点一致，
      同一天的折算因子就一样，等于给 5 个净值乘同一个数，谁最便宜的排序因此不变。
      结论很实用——<b>「该买哪一只」用 App 上的溢价直接比就行；只有「现在到底能不能买」这个绝对判断，
      才需要修掉隔夜噪音。</b></p>
  </section>

  <div class="disc">
    数据来源：场内不复权收盘价与净值取自东方财富，基准 QQQ 与 USDCNY 用于把净值折算到统一时点。
    公开口径 = {d["method"]["naive"]}；真实口径 = {d["method"]["true"]}。
    净值披露有 T+1 滞后，最新一两个交易日的溢价可能随净值补录而微调。<br>
    免责声明：以上为基于历史数据的统计描述，仅供参考，<b>不构成投资建议</b>。市场有风险，投资需谨慎。
    历史溢价水平与折价窗口不代表未来表现；QDII 另有外汇额度、限购、汇率等风险。
    任何投资决策应结合个人风险承受能力与投资目标独立判断，必要时咨询持牌专业机构。
  </div>
</div>

<script>
const DATA = {payload};
const dates = DATA.dates, funds = DATA.funds;
let kind = 'naive', months = 0;
const on = new Set(funds.map(f => f.code));

const dpr = () => Math.max(1, window.devicePixelRatio || 1);

function sliceIdx(){{
  if(!months) return 0;
  const end = new Date(dates[dates.length-1]);
  const cut = new Date(end.getFullYear(), end.getMonth()-months, end.getDate())
    .toISOString().slice(0,10);
  const i = dates.findIndex(d => d >= cut);
  return i < 0 ? 0 : i;
}}

function yRange(from, codes){{
  let lo = 0, hi = 0;
  for(const f of funds){{
    if(!codes.has(f.code)) continue;
    for(let i = from; i < dates.length; i++){{
      const v = f[kind][i];
      if(v === null) continue;
      if(v < lo) lo = v;
      if(v > hi) hi = v;
    }}
  }}
  const pad = Math.max(0.4, (hi - lo) * 0.08);
  return [lo - pad, hi + pad];
}}

function niceTicks(lo, hi, target){{
  const raw = (hi - lo) / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m*mag).find(s => s >= raw) || 10*mag;
  const out = [];
  for(let v = Math.ceil(lo/step)*step; v <= hi; v += step) out.push(v);
  return out;
}}

function setup(cv, h){{
  const w = cv.clientWidth, r = dpr();
  cv.width = w*r; cv.height = h*r;
  const g = cv.getContext('2d');
  g.setTransform(r,0,0,r,0,0);
  g.clearRect(0,0,w,h);
  return [g, w, h];
}}

function bands(g, x0, x1, Y, lo, hi){{
  // 折价（<0）绿、2%~5% 黄、>5% 红：颜色即结论，不用回头看说明
  const seg = [[lo, Math.min(0, hi), 'rgba(5,122,85,.075)'],
               [Math.max(DATA.buy_th, lo), Math.min(DATA.caution_th, hi), 'rgba(194,120,3,.075)'],
               [Math.max(DATA.caution_th, lo), hi, 'rgba(200,30,30,.075)']];
  for(const [a,b,c] of seg){{
    if(b <= a) continue;
    g.fillStyle = c;
    g.fillRect(x0, Y(b), x1-x0, Y(a)-Y(b));
  }}
}}

function drawMain(){{
  const cv = document.getElementById('main');
  const [g, w, h] = setup(cv, 420);
  const L = 46, R = 12, T = 12, B = 26;
  const from = sliceIdx(), n = dates.length - from;
  const [lo, hi] = yRange(from, on);
  const X = i => L + (w-L-R) * (n === 1 ? 0.5 : i/(n-1));
  const Y = v => T + (h-T-B) * (1 - (v-lo)/(hi-lo));

  bands(g, L, w-R, Y, lo, hi);

  g.strokeStyle = '#eef0f2'; g.fillStyle = '#9ca3af';
  g.font = '11px -apple-system,sans-serif'; g.textAlign = 'right';
  for(const t of niceTicks(lo, hi, 7)){{
    const y = Y(t);
    g.beginPath(); g.moveTo(L, y); g.lineTo(w-R, y); g.stroke();
    g.fillText(t.toFixed(Math.abs(t) < 1 && t !== 0 ? 1 : 0) + '%', L-7, y+3.5);
  }}
  g.strokeStyle = '#9ca3af'; g.lineWidth = 1;
  g.beginPath(); g.moveTo(L, Y(0)); g.lineTo(w-R, Y(0)); g.stroke();

  // x 轴：按月/季/年自适应挑刻度，避免文字重叠
  g.textAlign = 'center'; g.fillStyle = '#9ca3af';
  const stepM = n > 500 ? 6 : n > 250 ? 3 : n > 80 ? 1 : 1;
  let lastKey = '';
  for(let i = 0; i < n; i++){{
    const d = dates[from+i], m = +d.slice(5,7);
    const key = d.slice(0,7);
    if(key === lastKey || (m-1) % stepM !== 0) continue;
    lastKey = key;
    g.strokeStyle = '#f3f4f6';
    g.beginPath(); g.moveTo(X(i), T); g.lineTo(X(i), h-B); g.stroke();
    g.fillText(n > 250 ? d.slice(0,7) : d.slice(5,7)+'月', X(i), h-9);
  }}

  g.lineWidth = 1.5; g.lineJoin = 'round';
  for(const f of funds){{
    if(!on.has(f.code)) continue;
    g.strokeStyle = f.color;
    g.beginPath();
    let pen = false;
    for(let i = 0; i < n; i++){{
      const v = f[kind][from+i];
      if(v === null){{ pen = false; continue; }}
      if(pen) g.lineTo(X(i), Y(v)); else {{ g.moveTo(X(i), Y(v)); pen = true; }}
    }}
    g.stroke();
  }}
  return {{L, R, T, B, w, h, from, n, lo, hi, X, Y}};
}}

function drawMini(cv, code){{
  const f = funds.find(x => x.code === code);
  const [g, w, h] = setup(cv, 120);
  const L = 34, R = 8, T = 8, B = 16;
  const from = sliceIdx(), n = dates.length - from;
  const [lo, hi] = yRange(from, new Set(funds.map(x => x.code)));
  const X = i => L + (w-L-R) * (n === 1 ? 0.5 : i/(n-1));
  const Y = v => T + (h-T-B) * (1 - (v-lo)/(hi-lo));

  bands(g, L, w-R, Y, lo, hi);
  g.strokeStyle = '#9ca3af'; g.lineWidth = 1;
  g.beginPath(); g.moveTo(L, Y(0)); g.lineTo(w-R, Y(0)); g.stroke();
  g.fillStyle = '#9ca3af'; g.font = '10px -apple-system,sans-serif'; g.textAlign = 'right';
  for(const t of [hi, 0, lo]) g.fillText(t.toFixed(0)+'%', L-5, Y(t)+3);

  g.strokeStyle = f.color; g.lineWidth = 1.2; g.beginPath();
  let pen = false;
  for(let i = 0; i < n; i++){{
    const v = f[kind][from+i];
    if(v === null){{ pen = false; continue; }}
    if(pen) g.lineTo(X(i), Y(v)); else {{ g.moveTo(X(i), Y(v)); pen = true; }}
  }}
  g.stroke();
}}

let geom = null;
function renderAll(){{
  geom = drawMain();
  document.querySelectorAll('canvas[data-mini]').forEach(cv => drawMini(cv, cv.dataset.mini));
}}

const tip = document.getElementById('tip');
const box = document.querySelector('.chart-box');

function hover(ev){{
  if(!geom) return;
  const r = box.getBoundingClientRect();
  const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
  const {{L, R, w, from, n}} = geom;
  if(px < L-6 || px > w-R+6){{ tip.style.opacity = 0; return; }}
  const i = Math.max(0, Math.min(n-1, Math.round((px-L)/(w-L-R)*(n-1))));
  const rows = funds.filter(f => on.has(f.code) && f[kind][from+i] !== null)
    .map(f => [f, f[kind][from+i]]).sort((a,b) => a[1]-b[1]);
  if(!rows.length){{ tip.style.opacity = 0; return; }}

  renderAll();
  const g = document.getElementById('main').getContext('2d');
  g.strokeStyle = '#c9ced4'; g.lineWidth = 1; g.setLineDash([3,3]);
  g.beginPath(); g.moveTo(geom.X(i), geom.T); g.lineTo(geom.X(i), geom.h-geom.B); g.stroke();
  g.setLineDash([]);
  for(const [f, v] of rows){{
    g.fillStyle = f.color;
    g.beginPath(); g.arc(geom.X(i), geom.Y(v), 3, 0, 7); g.fill();
  }}

  tip.innerHTML = '<div class="d">' + dates[from+i] + ' · ' +
    (kind === 'naive' ? '公开口径' : '真实口径') + '</div>' +
    rows.map(([f, v]) => '<div class="r"><span><i style="background:' + f.color +
      '"></i>' + f.code + ' ' + f.name + '</span><b style="color:' +
      (v < 0 ? '#057a55' : v >= DATA.caution_th ? '#c81e1e' : 'inherit') + '">' +
      v.toFixed(2) + '%</b></div>').join('');
  tip.style.opacity = 1;
  const tw = tip.offsetWidth;
  tip.style.left = Math.min(Math.max(6, geom.X(i)+14), w-tw-6) + 'px';
  tip.style.top = Math.max(6, geom.T+6) + 'px';
}}

box.addEventListener('mousemove', hover);
box.addEventListener('touchmove', e => {{ hover(e); e.preventDefault(); }}, {{passive:false}});
box.addEventListener('mouseleave', () => {{ tip.style.opacity = 0; renderAll(); }});

document.getElementById('legend').addEventListener('click', e => {{
  const b = e.target.closest('.lg'); if(!b) return;
  const c = b.dataset.code;
  if(on.has(c) && on.size > 1){{ on.delete(c); b.classList.remove('on'); }}
  else {{ on.add(c); b.classList.add('on'); }}
  renderAll();
}});
document.getElementById('kind').addEventListener('click', e => {{
  const b = e.target.closest('button'); if(!b) return;
  kind = b.dataset.kind;
  [...b.parentNode.children].forEach(x => x.classList.toggle('on', x === b));
  renderAll();
}});
document.getElementById('rng').addEventListener('click', e => {{
  const b = e.target.closest('button'); if(!b) return;
  months = +b.dataset.m;
  [...b.parentNode.children].forEach(x => x.classList.toggle('on', x === b));
  renderAll();
}});
window.addEventListener('resize', renderAll);
renderAll();

// 表头跟随首行单元格的对齐方式，数字列右对齐后才和数值排成一条线
document.querySelectorAll('table').forEach(t => {{
  const first = t.tBodies[0] && t.tBodies[0].rows[0];
  if(!first || !t.tHead) return;
  [...t.tHead.rows[0].cells].forEach((th, i) => {{
    const td = first.cells[i];
    if(td && td.classList.contains('num')) th.classList.add('num');
  }});
}});
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=3.0, help="回看年数")
    args = ap.parse_args()

    d = build(args.years)

    json_path = OUT_DIR / "qdii-premium-curve.json"
    json_path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    html_path = OUT_DIR / "qdii-premium-curve.html"
    html_path.write_text(render_html(d), encoding="utf-8")

    print(f"区间 {d['start']} ~ {d['end']}  {d['n_dates']} 个交易日")
    for f in d["funds"]:
        s, t = f["stats_naive"], f["stats_true"]
        print(f"  {f['code']} {f['name']:<12s} n={s['n']:<4d} "
              f"中位 {s['median']:>6.2f}% (真实 {t['median']:>6.2f}%) "
              f"区间 {s['min']:>6.2f}%~{s['max']:>5.2f}% "
              f"折价 {s['share_neg']:>4.1f}% 天  <2% {s['share_lt2']:>4.1f}% 天  "
              f"翻转 {f['flip_days']}天 净值参考={f['nav_ref']}")
    sp = {x["kind"]: x for x in d["spread"]}
    print(f"  同日 5 只价差：中位 {sp['naive']['median']:.2f}% / P90 "
          f"{sp['naive']['p90']:.2f}% / 最大 {sp['naive']['max']:.2f}%")
    print(f"\n{json_path.relative_to(OUT_DIR.parent)}"
          f"\n{html_path.relative_to(OUT_DIR.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
