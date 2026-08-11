#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股场内 QDII（纳指100 / 标普500）长期走势 vs 美股原生 ETF（QQQ / SPY）

回答一个问题：在 A 股买纳指/标普 ETF，长期比直接买 QQQ/SPY 差多少？差在哪？
    QDII 人民币收益 ≈ 美股ETF美元收益 + 汇率变动 − 费率 − 跟踪误差/现金拖累

口径：
  - QDII：东财 pingzhongdata 的 Data_ACWorthTrend（累计净值，已还原份额折算与分红）
          → 净值口径，剔除了场内溢价波动的噪音
  - QQQ / SPY：Yahoo adjclose（含分红再投）
  - 汇率：Yahoo CNY=X（USDCNY 中间价近似），基准×汇率 = 人民币口径的美股收益
  - 场内市价：Yahoo 513100.SS / 159941.SZ 等 adjclose，仅做校验与「溢价侵蚀」参考

输出：friends/qdii-history.json（页面 friends/qdii-vs-us.html 读取）

用法：
  python3 friends/tools/fetch_qdii_history.py
  python3 friends/tools/fetch_qdii_history.py --out friends/qdii-history.json
  python3 friends/tools/fetch_qdii_history.py --sample      # 同时更新 sample 兜底文件

数据量不大但请求较多（每只基金 1 次全历史 + 3 个 Yahoo 序列），建议每周或每日盘后跑一次。
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))
TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
WATCHLIST_FILE = TOOLS_DIR / "qdii_watchlist.json"
FEES_CACHE_FILE = TOOLS_DIR / "qdii_fees_cache.json"

PZ_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
YAHOO_PATH = "/v8/finance/chart/{sym}?range={rng}&interval=1d&includeAdjustedClose=true"
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
CACHE_DIR = TOOLS_DIR / ".hist_cache"
CACHE_TTL_HOURS = 12

BENCH = {"纳指100": "QQQ", "标普500": "SPY"}
FX_SYMBOL = "CNY=X"  # 1 美元 = ? 人民币
WINDOWS = [("1y", 1), ("3y", 3), ("5y", 5), ("10y", 10)]


def _fetch_text(url: str, *, timeout: int = 30, retries: int = 3, backoff: float = 2.0) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
            last = e
            if i < retries - 1:
                time.sleep(backoff * (i + 1))
    raise RuntimeError(f"请求失败：{url} → {last}")


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', key)}.json"


def cache_read(key: str, *, max_age_hours: float = CACHE_TTL_HOURS) -> Any | None:
    """
    磁盘缓存：Yahoo 对高频请求会返回 429，跑失败一次就得等很久。
    命中缓存可让重跑/调试不再打网络；过期后仍保留，作为抓取失败时的兜底。
    """
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
        age = (time.time() - float(blob.get("ts", 0))) / 3600.0
        if age > max_age_hours:
            return None
        return blob.get("data")
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def cache_read_stale(key: str) -> Any | None:
    return cache_read(key, max_age_hours=24 * 365)


def cache_write(key: str, data: Any) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(
            json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


# ---------------------------------------------------------------- 数据抓取

def fetch_nav_series(code: str, *, use_cache: bool = True) -> tuple[dict[str, float], str]:
    """返回 ({日期: 累计净值}, 基金名)。累计净值已还原份额折算/分红，可直接算长期收益。"""
    key = f"nav_{code}"
    if use_cache:
        hit = cache_read(key)
        if hit:
            return {k: float(v) for k, v in hit["series"].items()}, hit.get("name") or code
    try:
        txt = _fetch_text(PZ_URL.format(code=code))
        m = re.search(r"Data_ACWorthTrend\s*=\s*(\[\[.*?\]\])\s*;", txt, re.S)
        if not m:
            raise RuntimeError(f"{code}: 未找到 Data_ACWorthTrend")
        name_m = re.search(r'fS_name\s*=\s*"([^"]*)"', txt)
        out: dict[str, float] = {}
        for ts, v in json.loads(m.group(1)):
            if v is None:
                continue
            out[datetime.fromtimestamp(ts / 1000, tz=CST).strftime("%Y-%m-%d")] = float(v)
        name = name_m.group(1) if name_m else code
        cache_write(key, {"series": out, "name": name})
        return out, name
    except (RuntimeError, json.JSONDecodeError):
        stale = cache_read_stale(key)
        if stale:
            print(f"  [warn] {code}: 抓取失败，使用本地缓存", file=sys.stderr)
            return {k: float(v) for k, v in stale["series"].items()}, stale.get("name") or code
        raise


def fetch_yahoo_series(symbol: str, rng: str = "15y", *, use_cache: bool = True) -> dict[str, float]:
    """Yahoo 日线 adjclose（含分红再投）。429 时轮换 host 并退避，最后退回本地缓存。"""
    key = f"yahoo_{symbol}_{rng}"
    if use_cache:
        hit = cache_read(key)
        if hit:
            return {k: float(v) for k, v in hit.items()}

    last: Exception | None = None
    for attempt in range(4):
        host = YAHOO_HOSTS[attempt % len(YAHOO_HOSTS)]
        url = f"https://{host}" + YAHOO_PATH.format(sym=urllib.parse.quote(symbol), rng=rng)
        try:
            d = json.loads(_fetch_text(url, retries=1))
            res = ((d.get("chart") or {}).get("result") or [None])[0]
            if not res:
                raise RuntimeError(f"{symbol}: Yahoo 无数据")
            ts = res.get("timestamp") or []
            ind = res.get("indicators") or {}
            adj = ((ind.get("adjclose") or [{}])[0] or {}).get("adjclose")
            close = ((ind.get("quote") or [{}])[0] or {}).get("close")
            vals = adj if adj else close
            if not vals:
                raise RuntimeError(f"{symbol}: Yahoo 无收盘价")
            out: dict[str, float] = {}
            for t, v in zip(ts, vals):
                if v is None:
                    continue
                out[datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")] = float(v)
            cache_write(key, out)
            return out
        except (RuntimeError, json.JSONDecodeError) as e:
            last = e
            if attempt < 3:
                time.sleep(8.0 * (attempt + 1))

    stale = cache_read_stale(key)
    if stale:
        print(f"  [warn] {symbol}: 抓取失败（{last}），使用本地缓存", file=sys.stderr)
        return {k: float(v) for k, v in stale.items()}
    raise RuntimeError(f"{symbol}: 抓取失败且无缓存 → {last}")


# ---------------------------------------------------------------- 序列工具

def sorted_items(s: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(s.items())


def value_at(s: dict[str, float], day: str, *, keys: list[str] | None = None) -> tuple[str, float] | None:
    """取 <= day 的最近一个值（前向填充）。用于跨市场日期对齐（美股/A股休市日不同）。"""
    ks = keys if keys is not None else sorted(s)
    lo, hi, best = 0, len(ks) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if ks[mid] <= day:
            best = ks[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return (best, s[best]) if best else None


def value_from(s: dict[str, float], day: str, keys: list[str] | None = None) -> tuple[str, float] | None:
    """取 >= day 的第一个值。用于窗口起点（不能用还没上市时的价格）。"""
    ks = keys if keys is not None else sorted(s)
    for k in ks:
        if k >= day:
            return k, s[k]
    return None


def to_cny(bench: dict[str, float], fx: dict[str, float]) -> dict[str, float]:
    """美元序列 → 人民币口径序列（用当日或最近汇率折算）。"""
    fx_keys = sorted(fx)
    out: dict[str, float] = {}
    for d, v in bench.items():
        hit = value_at(fx, d, keys=fx_keys)
        if hit:
            out[d] = v * hit[1]
    return out


def shift_forward(s: dict[str, float], days: int = 1) -> dict[str, float]:
    """
    把序列日期整体后移 days 天。
    QDII 的 T 日净值反映的是美股 T−1 收盘（美股收盘在北京时间凌晨），不后移就会拿
    「还没发生」的美股涨跌去比，1 年窗口能凭空差出 1 个百分点。
    """
    out: dict[str, float] = {}
    for d, v in s.items():
        out[(date.fromisoformat(d) + timedelta(days=days)).isoformat()] = v
    return out


def month_end_series(s: dict[str, float]) -> dict[str, float]:
    """降采样为「年-月 → 该月最后一个可用值」。"""
    out: dict[str, float] = {}
    for d, v in sorted_items(s):
        out[d[:7]] = v
    return out


def cagr(v0: float, v1: float, years: float) -> float | None:
    if v0 <= 0 or years <= 0:
        return None
    return ((v1 / v0) ** (1.0 / years) - 1.0) * 100.0


def perf(s: dict[str, float], start: str, end: str, keys: list[str] | None = None) -> dict[str, Any] | None:
    ks = keys if keys is not None else sorted(s)
    a = value_from(s, start, ks)
    b = value_at(s, end, keys=ks)
    if not a or not b or a[0] >= b[0]:
        return None
    years = (date.fromisoformat(b[0]) - date.fromisoformat(a[0])).days / 365.25
    if years < 0.15:
        return None
    return {
        "start": a[0],
        "end": b[0],
        "years": round(years, 2),
        "cum_pct": round((b[1] / a[1] - 1.0) * 100.0, 2),
        "cagr_pct": round(cagr(a[1], b[1], years) or 0.0, 2),
    }


def perf_on(
    s: dict[str, float], day_a: str, day_b: str, years: float, keys: list[str] | None = None
) -> dict[str, Any] | None:
    """在给定的两个日期上取值算收益：让基准与 QDII 用完全相同的起止日，避免错位比较。"""
    ks = keys if keys is not None else sorted(s)
    a = value_at(s, day_a, keys=ks)
    b = value_at(s, day_b, keys=ks)
    if not a or not b or a[1] <= 0 or years <= 0:
        return None
    return {
        "cum_pct": round((b[1] / a[1] - 1.0) * 100.0, 2),
        "cagr_pct": round(cagr(a[1], b[1], years) or 0.0, 2),
    }


# ---------------------------------------------------------------- 组装

def load_watchlist() -> dict[str, Any]:
    cfg = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    return cfg


def load_fees() -> dict[str, dict[str, Any]]:
    if not FEES_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(FEES_CACHE_FILE.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def yahoo_symbol(code: str) -> str:
    return f"{code}.SS" if code.startswith(("5", "6")) else f"{code}.SZ"


def build_chart(
    years: int,
    end_day: str,
    candidates: list[dict[str, Any]],
    bench_cny: dict[str, float],
    bench_usd: dict[str, float],
    bench_name: str,
    *,
    max_qdii: int = 4,
) -> dict[str, Any] | None:
    """
    统一起点、统一归一到 100 的月度对比曲线。
    只收窗口起点前就已上市的标的（否则起点归一没有意义），并限制条数，避免十几条线糊成一团。
    """
    start_day = (date.fromisoformat(end_day) - timedelta(days=int(365.25 * years))).isoformat()
    eligible = [c for c in candidates if c["nav_keys"][0] <= start_day]
    if not eligible:
        return None
    # 优先低费率，且始终保留历史最长的一只
    picked = sorted(eligible, key=lambda f: (f["fee_total_pct"] if f["fee_total_pct"] is not None else 9, f["inception"]))[:max_qdii]
    oldest = min(eligible, key=lambda f: f["inception"])
    if oldest["code"] not in {p["code"] for p in picked}:
        picked = picked[: max_qdii - 1] + [oldest]

    members: list[tuple[str, str, str, dict[str, float]]] = [
        (p["code"], p["short"], "qdii", p["nav"]) for p in sorted(picked, key=lambda f: f["inception"])
    ]
    members.append((f"{bench_name}_CNY", f"{bench_name}（人民币口径）", "bench_cny", bench_cny))
    members.append((f"{bench_name}_USD", f"{bench_name}（美元口径）", "bench_usd", bench_usd))

    months: list[str] = []
    cur = date.fromisoformat(start_day).replace(day=1)
    last = date.fromisoformat(end_day).replace(day=1)
    while cur <= last:
        months.append(cur.strftime("%Y-%m"))
        cur = (cur.replace(day=28) + timedelta(days=7)).replace(day=1)

    series = []
    for key, label, kind, s in members:
        me = month_end_series(s)
        ms = sorted(me)
        base_hit = None
        vals: list[float | None] = []
        for ym in months:
            hit = value_at(me, ym, keys=ms)
            v = hit[1] if hit else None
            if v is not None and base_hit is None:
                base_hit = v
            vals.append(None if (v is None or base_hit is None) else round(v / base_hit * 100.0, 2))
        if base_hit is None:
            continue
        last_v = next((v for v in reversed(vals) if v is not None), None)
        series.append({
            "key": key,
            "label": label,
            "kind": kind,
            "values": vals,
            "end_index": last_v,
            "cum_pct": None if last_v is None else round(last_v - 100.0, 1),
        })

    return {
        "window": f"{years}y",
        "title": f"近 {years} 年（统一起点归一到 100）",
        "start": months[0],
        "end": months[-1],
        "dates": months,
        "series": series,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="QDII 长期走势 vs QQQ/SPY")
    ap.add_argument("--out", type=Path, default=ROOT / "qdii-history.json")
    ap.add_argument("--sample", action="store_true", help="同时写 qdii-history.sample.json")
    ap.add_argument("--refresh", action="store_true", help="忽略本地缓存，强制重新抓取")
    args = ap.parse_args()
    use_cache = not args.refresh

    cfg = load_watchlist()
    fees = load_fees()
    watch = cfg.get("items") or []

    print("拉取美股基准与汇率 …")
    fx_raw = fetch_yahoo_series(FX_SYMBOL, use_cache=use_cache)
    bench_usd: dict[str, dict[str, float]] = {}
    bench_cny: dict[str, dict[str, float]] = {}
    for sym in sorted(set(BENCH.values())):
        raw = fetch_yahoo_series(sym, use_cache=use_cache)
        # 后移 1 天，对齐到 QDII 净值日历（T 日净值 ≈ 美股 T−1 收盘）
        bench_usd[sym] = shift_forward(raw)
        bench_cny[sym] = shift_forward(to_cny(raw, fx_raw))
        print(f"  {sym}: {len(raw)} 个交易日")

    fx = shift_forward(fx_raw)
    last_bench_day = min(max(bench_usd[s]) for s in bench_usd)
    fx_keys = sorted(fx)

    print("拉取各 QDII 全历史净值 …")
    funds: list[dict[str, Any]] = []
    for it in watch:
        code = str(it["code"]).strip()
        try:
            nav, name = fetch_nav_series(code, use_cache=use_cache)
        except RuntimeError as e:
            print(f"  [warn] {code}: {e}", file=sys.stderr)
            continue
        if len(nav) < 60:
            print(f"  [warn] {code}: 净值点太少（{len(nav)}），跳过", file=sys.stderr)
            continue
        keys = sorted(nav)
        fee = fees.get(code) or {}
        mgmt = fee.get("mgmt") if fee.get("mgmt") is not None else it.get("fee_mgmt_pct")
        custody = fee.get("custody") if fee.get("custody") is not None else it.get("fee_custody_pct")
        total = None if (mgmt is None and custody is None) else round((mgmt or 0) + (custody or 0), 3)
        funds.append({
            "code": code,
            "name": it.get("name") or name,
            "short": f"{code} {it.get('manager') or ''}".strip(),
            "manager": it.get("manager") or "",
            "group": it.get("group") or "其他",
            "fee_mgmt_pct": mgmt,
            "fee_custody_pct": custody,
            "fee_total_pct": total,
            "nav": nav,
            "nav_keys": keys,
            "inception": keys[0],
        })
        print(f"  {code} {it.get('manager','')}: {keys[0]} → {keys[-1]}（{len(nav)} 天）")

    if not funds:
        print("ERROR: 没有任何基金净值数据", file=sys.stderr)
        return 1

    # 统一截止日：QDII 最新净值日与基准最新可用日取更早者
    end_day = min(last_bench_day, max(f["nav_keys"][-1] for f in funds))

    groups_out: dict[str, Any] = {}
    for group in cfg.get("groups_order") or sorted({f["group"] for f in funds}):
        members = [f for f in funds if f["group"] == group]
        if not members:
            continue
        bsym = BENCH.get(group)
        if not bsym:
            continue
        b_usd, b_cny = bench_usd[bsym], bench_cny[bsym]
        b_usd_keys, b_cny_keys = sorted(b_usd), sorted(b_cny)

        rows = []
        for f in members:
            row: dict[str, Any] = {
                "code": f["code"],
                "name": f["name"],
                "manager": f["manager"],
                "fee_mgmt_pct": f["fee_mgmt_pct"],
                "fee_custody_pct": f["fee_custody_pct"],
                "fee_total_pct": f["fee_total_pct"],
                "inception": f["inception"],
                "windows": {},
            }
            spans: list[tuple[str, str]] = []
            for wkey, wyears in WINDOWS:
                start_day = (date.fromisoformat(end_day) - timedelta(days=int(365.25 * wyears))).isoformat()
                if f["inception"] > start_day:
                    continue
                spans.append((wkey, start_day))
            spans.append(("since", f["inception"]))

            for wkey, start_day in spans:
                p = perf(f["nav"], start_day, end_day, f["nav_keys"])
                if not p:
                    continue
                # 基准/汇率都在 QDII 的实际净值起止日上取值，窗口完全一致
                a0, b0, yrs = p["start"], p["end"], p["years"]
                pb_cny = perf_on(b_cny, a0, b0, yrs, b_cny_keys)
                pb_usd = perf_on(b_usd, a0, b0, yrs, b_usd_keys)
                pfx = perf_on(fx, a0, b0, yrs, fx_keys)
                if not pb_cny or not pb_usd:
                    continue
                row["windows"][wkey] = {
                    "start": a0,
                    "end": b0,
                    "years": yrs,
                    "cum_pct": p["cum_pct"],
                    "cagr_pct": p["cagr_pct"],
                    "bench_cny_cum_pct": pb_cny["cum_pct"],
                    "bench_cny_cagr_pct": pb_cny["cagr_pct"],
                    "bench_usd_cum_pct": pb_usd["cum_pct"],
                    "bench_usd_cagr_pct": pb_usd["cagr_pct"],
                    "fx_cum_pct": None if not pfx else pfx["cum_pct"],
                    "fx_cagr_pct": None if not pfx else pfx["cagr_pct"],
                    "gap_cagr_pct": round(p["cagr_pct"] - pb_cny["cagr_pct"], 2),
                    "gap_cum_pct": round(p["cum_pct"] - pb_cny["cum_pct"], 2),
                }
            rows.append(row)

        rows.sort(key=lambda r: (r["fee_total_pct"] if r["fee_total_pct"] is not None else 9, r["inception"]))

        charts = []
        for wyears in (10, 5, 3):
            ch = build_chart(wyears, end_day, members, b_cny, b_usd, bsym)
            if ch and any(s["kind"] == "qdii" for s in ch["series"]):
                charts.append(ch)

        groups_out[group] = {
            "benchmark": bsym,
            "benchmark_label": {"QQQ": "QQQ 纳指100ETF-Invesco", "SPY": "SPY 标普500ETF-SPDR"}.get(bsym, bsym),
            "count": len(members),
            "charts": charts,
            "table": rows,
        }

    fx_now = value_at(fx, end_day, keys=fx_keys)
    fx_windows = {}
    for wkey, wyears in WINDOWS:
        start_day = (date.fromisoformat(end_day) - timedelta(days=int(365.25 * wyears))).isoformat()
        p = perf(fx, start_day, end_day, fx_keys)
        if p:
            fx_windows[wkey] = {"cum_pct": p["cum_pct"], "cagr_pct": p["cagr_pct"], "start": p["start"]}

    now = datetime.now(CST)
    payload = {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_text": now.strftime("%Y-%m-%d %H:%M:%S") + " CST",
        "as_of": end_day,
        "title": "A股场内 QDII vs 美股原生 ETF · 长期走势对比",
        "method": {
            "qdii": "东财累计净值（Data_ACWorthTrend，已还原份额折算与分红），净值口径，不含场内溢价波动",
            "bench": "Yahoo adjclose（含分红再投）",
            "fx": "Yahoo CNY=X（USDCNY），美元序列×汇率 = 人民币口径",
            "gap": "gap_cagr_pct = QDII 年化 − 基准人民币口径年化，负值表示每年落后多少",
            "note": "净值口径已剔除买入时的溢价成本；场内溢价 8% 相当于在此基础上再打一次折扣。",
        },
        "fx": {
            "symbol": FX_SYMBOL,
            "latest": None if not fx_now else round(fx_now[1], 4),
            "latest_date": None if not fx_now else fx_now[0],
            "windows": fx_windows,
        },
        "windows_order": [w for w, _ in WINDOWS] + ["since"],
        "windows_label": {
            "1y": "近 1 年", "3y": "近 3 年", "5y": "近 5 年", "10y": "近 10 年", "since": "成立以来",
        },
        "groups_order": [g for g in (cfg.get("groups_order") or []) if g in groups_out],
        "groups": groups_out,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out}  as_of={end_day}")
    if args.sample:
        sample = args.out.with_name(args.out.stem + ".sample" + args.out.suffix)
        sample.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {sample}")

    for g, gd in groups_out.items():
        print(f"\n=== {g} vs {gd['benchmark']} ===")
        for r in gd["table"]:
            w = r["windows"].get("5y") or r["windows"].get("3y") or r["windows"].get("since") or {}
            print(
                f"  {r['code']} {r['manager']:<5} 费率{r['fee_total_pct']}%/年 "
                f"成立{r['inception']} | 年化{w.get('cagr_pct')}% vs 基准(人民币){w.get('bench_cny_cagr_pct')}% "
                f"→ 差 {w.get('gap_cagr_pct')}%/年"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
