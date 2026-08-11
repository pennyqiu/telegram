#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测 A股场内纳指100 / 标普500 QDII ETF 日溢价率（2026 年起）。

方法：
- 收盘价：东财日 K（不复权）
- 单位净值：东财基金历史净值 DWJZ
- 日溢价% = (收盘价 − 单位净值) / 单位净值 × 100
  （按净值披露日对齐；QDII 净值常滞后 1 日，故最新交易日可能尚无溢价）

⚠️ 口径警告：本脚本的溢价是「有偏」的，只适合看趋势，不要用来定阈值或做买点判断。
   实测（backtest_qdii_true_premium.py，16 只标的、2025-01 起 388 个交易日）确认：
   净值(D) 参考的是「美股交易日 == D」那一场，即 D 当晚、收在 D+1 凌晨
   （净值日收益 vs 基准人民币日收益 相关系数 0.987~0.997；错位一天则降到约 0）。
   而 A 股 D 日 15:00 收盘价还不知道当晚涨跌 → 本口径混入了整晚的标的波动：
     美股当晚大涨 → 净值(D) 偏高 → 显示成「假折价」（最危险，会诱你在贵的时候买）
     美股当晚大跌 → 显示成「假高溢价」
   典型案例 513100 / 2025-04-09（纳指当晚 +12%）：本口径 −6.00%「深折价」，
   实际真溢价 +5.44%，方向相反、差 11.4 个百分点。
   偏差在高波动期最大，恰好是你最想加仓的时候。
   → 请改用 backtest_qdii_true_premium.py（把净值折算到 A 股收盘时点的统一口径）。
   注：实时脚本 fetch_qdii_premium.py 用的是东财 IOPV(f441)，本身无此问题。

信号（与 fetch_qdii_premium.py 一致）：
  <2% 可投 · 2–5% 谨慎 · >5% 不投

用法：
  python3 friends/tools/backtest_qdii_premium.py
  python3 friends/tools/backtest_qdii_premium.py --start 20260101 --json /tmp/qdii_prem.json

仅供研究，非投资建议。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
WATCHLIST_FILE = TOOLS_DIR / "qdii_watchlist.json"
CACHE_DIR = TOOLS_DIR / ".bt_cache" / "qdii_premium"

H = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}


def _secid(code: str) -> str:
    return f"1.{code}" if code.startswith(("5", "6")) else f"0.{code}"


def _get(url: str, tries: int = 5) -> str:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"请求失败: {url} ({last})")


def load_watchlist() -> list[dict[str, Any]]:
    cfg = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    items = []
    for it in cfg.get("items") or []:
        code = str(it["code"]).strip()
        items.append({
            "code": code,
            "secid": _secid(code),
            "name": it.get("name") or code,
            "group": it.get("group") or "其他",
            "manager": it.get("manager") or "",
        })
    return items


def _sym_cn(code: str) -> str:
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def fetch_closes(code: str, secid: str, start: str, end: str) -> dict[str, float]:
    """start/end: YYYYMMDD → {YYYY-MM-DD: close}。优先腾讯，东财作备选。"""
    start_d = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    end_d = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    sym = _sym_cn(code)

    # 1) 腾讯 fq kline（稳定）
    try:
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
            f"param={sym},day,{start_d},{end_d},640,"
        )
        d = json.loads(_get(url, tries=3))
        block = (d.get("data") or {}).get(sym) or {}
        rows = block.get("day") or block.get("qfqday") or block.get("hfqday") or []
        out: dict[str, float] = {}
        for row in rows:
            # [date, open, close, high, low, volume]
            dt = row[0][:10]
            if start_d <= dt <= end_d:
                out[dt] = float(row[2])
        if out:
            return out
    except Exception:
        pass

    # 2) 新浪
    try:
        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=300"
        )
        rows = json.loads(_get(url, tries=3))
        out = {}
        for row in rows:
            dt = row["day"][:10]
            if start_d <= dt <= end_d:
                out[dt] = float(row["close"])
        if out:
            return out
    except Exception:
        pass

    # 3) 东财（偶发断连）
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=0&beg={start}&end={end}&lmt=10000"
    )
    d = json.loads(_get(url))
    kl = (d.get("data") or {}).get("klines") or []
    out = {}
    for row in kl:
        p = row.split(",")
        out[p[0]] = float(p[2])
    return out


def fetch_navs(code: str, start: str, end: str) -> dict[str, float]:
    """start/end: YYYYMMDD → {YYYY-MM-DD: nav}

    东财 lsjz 的 startDate/endDate 经常不生效，且 pageSize 固定约 20；
    TotalCount 在响应顶层。按页从新到旧翻，越过 start 即停。
    """
    sdate = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    edate = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    out: dict[str, float] = {}
    page = 1
    page_size = 20
    total = None
    while True:
        url = (
            "https://api.fund.eastmoney.com/f10/lsjz?"
            f"callback=jQuery&fundCode={code}&pageIndex={page}&pageSize={page_size}"
            f"&startDate=&endDate=&_={int(time.time()*1000)}"
        )
        text = _get(url)
        m = re.search(r"jQuery\((.*)\)\s*$", text, re.S)
        payload = json.loads(m.group(1) if m else text)
        data = payload.get("Data") or {}
        rows = data.get("LSJZList") or []
        if not rows:
            break
        if total is None:
            total = int(payload.get("TotalCount") or data.get("TotalCount") or 0)
        oldest_on_page = None
        for r in rows:
            dt = r.get("FSRQ")
            nav = r.get("DWJZ")
            if not dt or nav in (None, ""):
                continue
            oldest_on_page = dt
            if dt < sdate or dt > edate:
                continue
            try:
                out[dt] = float(nav)
            except (TypeError, ValueError):
                continue
        # 本页已全部早于 start，可停
        if oldest_on_page is not None and oldest_on_page < sdate:
            break
        if total and page * page_size >= total:
            break
        # 保险：最多翻 40 页（约 800 日）
        if page >= 40:
            break
        page += 1
        time.sleep(0.12)
    return out


def signal_for(premium: float) -> str:
    if premium < 2:
        return "可投"
    if premium < 5:
        return "谨慎"
    return "不投"


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def analyze_series(prem_by_date: dict[str, float]) -> dict[str, Any]:
    items = sorted(prem_by_date.items())
    vals = [v for _, v in items]
    if not vals:
        return {"n": 0}
    sv = sorted(vals)
    n = len(vals)
    buy_days = [(d, v) for d, v in items if v < 2]
    caution_days = [(d, v) for d, v in items if 2 <= v < 5]
    avoid_days = [(d, v) for d, v in items if v >= 5]
    # 连续可投段
    streaks: list[tuple[str, str, int, float]] = []
    i = 0
    while i < n:
        d, v = items[i]
        if v >= 2:
            i += 1
            continue
        j = i
        while j < n and items[j][1] < 2:
            j += 1
        seg = items[i:j]
        streaks.append((seg[0][0], seg[-1][0], len(seg), min(x[1] for x in seg)))
        i = j
    streaks.sort(key=lambda x: -x[2])
    # 最低溢价日（前 10）
    lowest = sorted(items, key=lambda x: x[1])[:10]
    latest = items[-1]
    return {
        "n": n,
        "start": items[0][0],
        "end": items[-1][0],
        "latest_date": latest[0],
        "latest_prem": round(latest[1], 2),
        "latest_signal": signal_for(latest[1]),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "mean": round(sum(vals) / n, 2),
        "median": round(percentile(sv, 50), 2),
        "p10": round(percentile(sv, 10), 2),
        "p25": round(percentile(sv, 25), 2),
        "p75": round(percentile(sv, 75), 2),
        "p90": round(percentile(sv, 90), 2),
        "buy_n": len(buy_days),
        "buy_pct": round(len(buy_days) / n * 100, 1),
        "caution_n": len(caution_days),
        "caution_pct": round(len(caution_days) / n * 100, 1),
        "avoid_n": len(avoid_days),
        "avoid_pct": round(len(avoid_days) / n * 100, 1),
        "buy_streaks": [
            {"from": a, "to": b, "days": c, "min_prem": round(m, 2)}
            for a, b, c, m in streaks[:8]
        ],
        "lowest": [{"date": d, "prem": round(v, 2)} for d, v in lowest],
        "series": [{"date": d, "prem": round(v, 2)} for d, v in items],
    }


def load_or_fetch(code: str, secid: str, start: str, end: str, refresh: bool) -> dict[str, float]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{code}_{start}_{end}.json"
    if cache.exists() and not refresh and time.time() - cache.stat().st_mtime < 6 * 3600:
        return json.loads(cache.read_text(encoding="utf-8"))

    closes = fetch_closes(code, secid, start, end)
    time.sleep(0.25)
    navs = fetch_navs(code, start, end)
    prem: dict[str, float] = {}
    for d, nav in navs.items():
        if d not in closes or abs(nav) < 1e-9:
            continue
        prem[d] = (closes[d] - nav) / nav * 100.0
    cache.write_text(json.dumps(prem, ensure_ascii=False, indent=2), encoding="utf-8")
    return prem


def group_daily_best(all_series: dict[str, dict[str, Any]], group: str) -> list[dict[str, Any]]:
    """每日同组最低溢价（可买哪只）。"""
    by_date: dict[str, list[tuple[str, str, float]]] = {}
    for code, info in all_series.items():
        if info["group"] != group:
            continue
        for pt in info["stats"]["series"]:
            by_date.setdefault(pt["date"], []).append((code, info["name"], pt["prem"]))
    out = []
    for d in sorted(by_date):
        best = min(by_date[d], key=lambda x: x[2])
        out.append({
            "date": d,
            "code": best[0],
            "name": best[1],
            "prem": best[2],
            "signal": signal_for(best[2]),
            "n_listed": len(by_date[d]),
        })
    return out


def print_report(payload: dict[str, Any]) -> None:
    print(f"区间：{payload['start']} → {payload['end']}（按净值披露日对齐）")
    print(f"规则：溢价<2%可投 · 2–5%谨慎 · >5%不投；长线买入优先等可投/低分位。\n")

    for g in payload["groups_order"]:
        rows = [x for x in payload["items"] if x["group"] == g]
        rows.sort(key=lambda x: (x["stats"].get("median", 99), x["stats"].get("mean", 99)))
        print("=" * 100)
        print(f"【{g}】按中位溢价从低到高")
        print("-" * 100)
        print(
            f"{'代码':<8}{'名称':<18}{'N日':>4}{'最新%':>8}{'信号':>4}"
            f"{'均':>7}{'中位':>7}{'P10':>7}{'P25':>7}{'最小':>7}"
            f"{'可投%':>7}{'谨慎%':>7}{'不投%':>7}"
        )
        for r in rows:
            s = r["stats"]
            if not s.get("n"):
                print(f"{r['code']:<8}{r['name']:<18}  无数据")
                continue
            print(
                f"{r['code']:<8}{r['name']:<18}{s['n']:>4}"
                f"{s['latest_prem']:>8.2f}{s['latest_signal']:>4}"
                f"{s['mean']:>7.2f}{s['median']:>7.2f}{s['p10']:>7.2f}{s['p25']:>7.2f}{s['min']:>7.2f}"
                f"{s['buy_pct']:>6.1f}%{s['caution_pct']:>6.1f}%{s['avoid_pct']:>6.1f}%"
            )

        gb = payload["group_best"].get(g) or []
        if gb:
            buy_n = sum(1 for x in gb if x["prem"] < 2)
            caution_n = sum(1 for x in gb if 2 <= x["prem"] < 5)
            avoid_n = sum(1 for x in gb if x["prem"] >= 5)
            vals = sorted(x["prem"] for x in gb)
            print()
            print(f"  ▸ 同组每日「最低溢价」汇总（选最便宜那只再看信号）")
            print(
                f"    交易日 {len(gb)} · 可投日 {buy_n}({buy_n/len(gb)*100:.1f}%) · "
                f"谨慎日 {caution_n}({caution_n/len(gb)*100:.1f}%) · "
                f"不投日 {avoid_n}({avoid_n/len(gb)*100:.1f}%)"
            )
            print(
                f"    最低溢价分布：min={vals[0]:.2f}%  P10={percentile(vals,10):.2f}%  "
                f"中位={percentile(vals,50):.2f}%  均={sum(vals)/len(vals):.2f}%  "
                f"最新 {gb[-1]['date']} {gb[-1]['code']} {gb[-1]['prem']:.2f}% ({gb[-1]['signal']})"
            )
            # 可投窗口
            windows = []
            i = 0
            while i < len(gb):
                if gb[i]["prem"] >= 2:
                    i += 1
                    continue
                j = i
                while j < len(gb) and gb[j]["prem"] < 2:
                    j += 1
                seg = gb[i:j]
                windows.append(seg)
                i = j
            if windows:
                print("    可投窗口（同组最低溢价<2%）：")
                for seg in sorted(windows, key=lambda s: -len(s))[:6]:
                    mn = min(x["prem"] for x in seg)
                    codes = {}
                    for x in seg:
                        codes[x["code"]] = codes.get(x["code"], 0) + 1
                    top = sorted(codes.items(), key=lambda x: -x[1])[:3]
                    top_s = ", ".join(f"{c}×{n}" for c, n in top)
                    print(
                        f"      {seg[0]['date']} → {seg[-1]['date']}  "
                        f"{len(seg)}日  最低{mn:.2f}%  常胜：{top_s}"
                    )
            else:
                print("    今年以来同组最低溢价也从未跌破 2%（无「可投」日）。")
            # 相对低位：P25 以下的买入提示
            p25 = percentile(vals, 25)
            low_days = [x for x in gb if x["prem"] <= p25]
            print(
                f"    相对低位（≤同组最低溢价P25={p25:.2f}%）共 {len(low_days)} 日；"
                f"长线若不愿等<2%，可把「≤P25」当加仓区。"
            )
        print()

    print("提示：长线一般不卖；买点优先等「可投」，其次同组相对低分位+大市值/高流动性。")


def main() -> int:
    ap = argparse.ArgumentParser(description="QDII 场内溢价历史回测")
    ap.add_argument("--start", default="20260101", help="YYYYMMDD")
    ap.add_argument("--end", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新拉取")
    ap.add_argument("--json", default="", help="写出完整结果 JSON 路径")
    args = ap.parse_args()

    watch = load_watchlist()
    items_out: list[dict[str, Any]] = []
    series_map: dict[str, dict[str, Any]] = {}

    print(f"拉取 {len(watch)} 只 ETF 溢价：{args.start} → {args.end}\n")
    for it in watch:
        code = it["code"]
        print(f"  … {code} {it['name']}", flush=True)
        try:
            prem = load_or_fetch(code, it["secid"], args.start, args.end, args.refresh)
            stats = analyze_series(prem)
        except Exception as e:  # noqa: BLE001
            print(f"    FAIL {e}")
            stats = {"n": 0, "error": str(e), "series": []}
            prem = {}
        row = {**it, "stats": stats}
        items_out.append(row)
        series_map[code] = row
        time.sleep(0.25)

    groups_order = ["纳指100", "标普500"]
    group_best = {g: group_daily_best(series_map, g) for g in groups_order}

    payload = {
        "title": "场内 QDII 溢价历史回测",
        "start": args.start,
        "end": args.end,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "premium=(close-nav)/nav*100；净值披露日对齐",
        "rules": {"buy": "<2%", "caution": "2–5%", "avoid": ">5%"},
        "groups_order": groups_order,
        "items": items_out,
        "group_best": {
            g: [
                {k: x[k] for k in ("date", "code", "name", "prem", "signal")}
                for x in gb
            ]
            for g, gb in group_best.items()
        },
    }

    print()
    print_report(payload)

    out_path = args.json or str(CACHE_DIR / f"summary_{args.start}_{args.end}.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    # 完整 series 较大；summary 里保留 series 供 canvas
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
