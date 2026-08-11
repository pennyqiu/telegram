#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QDII 场内「真溢价」回测：用估算净值（IOPV 口径）替代滞后的披露净值。

问题背景
--------
backtest_qdii_premium.py 用的是：
    naive溢价 = (场内收盘价 − 当日披露单位净值) / 单位净值
若披露净值参考的美股收盘 ≠ A股收盘时刻已知的最新美股收盘，这个口径就混入了
「隔夜标的涨跌」的噪音：美股夜里大涨 → 场内价先反应、净值还是旧的 → 显示假溢价。

本脚本做三件事
--------------
1) 经验判定净值的参考时点：不假设滞后几天，而是用「净值日收益」与「基准人民币日收益」
   在多个候选对齐方式下的相关性，挑相关性最高的那个（数据说话）。
     候选 A0：净值(D) 参考「美股交易日 == D」那一场（即 D 当晚，收在 D+1 凌晨）
     候选 A1：净值(D) 参考「D 之前最后一个美股交易日」（收在 D 当天凌晨）
     候选 A2：再往前一个美股交易日
2) 按判定结果算真溢价：把净值折算到「A股收盘时刻已知的最新美股收盘」这个统一时点。
     基准人民币值 = 标的美元收盘 × USDCNY
     NAV_est(D) = 单位净值(D) × [基准RMB(cur)] / [基准RMB(ref)]
     真溢价(D)  = 场内收盘价(D) / NAV_est(D) − 1
   其中 cur = D 之前最后一个美股交易日（A股收盘时已知的最新信息）
        ref = 由第 1 步判定的净值参考日
3) 新旧信号对比：分布、可投日(<2%)占比、信号翻转天数，以及
   「溢价 vs 隔夜涨跌」的相关性（污染程度的直接体检指标）。
   并给出成交额过滤后的同组最低溢价（避免被引到买不进去的小 ETF）。

数据源（本机可用性已验证）
--------------------------
  A股收盘价/成交量 : 腾讯 web.ifzq.gtimg.cn（sh/sz 日K）
  单位/累计净值    : 东财 api.fund.eastmoney.com/f10/lsjz（DWJZ / LJJZ）
  基准 QQQ/SPY     : 腾讯 web.ifzq.gtimg.cn（usQQQ / usSPY 日K）
  汇率 USDCNY      : api.frankfurter.app（ECB 口径日度）

用法
----
  python backtest_qdii_true_premium.py
  python backtest_qdii_true_premium.py --start 20250101 --json out.json
  python backtest_qdii_true_premium.py --codes 513100,159941 --start 20250601

仅供研究，非投资建议。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
WATCHLIST_FILE = TOOLS_DIR / "qdii_watchlist.json"
CACHE_DIR = TOOLS_DIR / ".bt_cache" / "true_premium"
CACHE_TTL = 6 * 3600

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}

BENCH_SYM = {"纳指100": "QQQ", "标普500": "SPY"}
# 信号阈值（与现有脚本一致）
BUY_TH, CAUTION_TH = 2.0, 5.0
# 成交额过滤：日成交额下限（元）。0.3 亿对应现有 liquidity_tier 的「中」档
MIN_AMOUNT = 0.3e8


# ---------------------------------------------------------------- 基础工具
def _get(url: str, tries: int = 4, timeout: int = 30) -> str:
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


def _sym_cn(code: str) -> str:
    return ("sh" if code.startswith(("5", "6")) else "sz") + code


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


class Tee:
    """把报告同时写到 stdout 与 UTF-8 文件（Windows 控制台常是 GBK，中文会乱码）。"""

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


def signal_for(prem: float) -> str:
    if prem < BUY_TH:
        return "可投"
    if prem < CAUTION_TH:
        return "谨慎"
    return "不投"


# ---------------------------------------------------------------- 数据抓取
def load_watchlist(only: set[str] | None) -> list[dict[str, Any]]:
    cfg = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    out = []
    for it in cfg.get("items") or []:
        code = str(it["code"]).strip()
        if only and code not in only:
            continue
        out.append({
            "code": code,
            "name": it.get("name") or code,
            "group": it.get("group") or "其他",
            "manager": it.get("manager") or "",
            "fee_mgmt_pct": it.get("fee_mgmt_pct"),
            "fee_custody_pct": it.get("fee_custody_pct"),
        })
    return out


def fetch_cn_daily(code: str, start: str, end: str) -> dict[str, dict[str, float]]:
    """A股场内日线 → {date: {close, amount}}；amount 用 成交量(手)×100×收盘 估算。"""
    sd = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    ed = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    sym = _sym_cn(code)

    def _fetch():
        url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
               f"param={sym},day,{sd},{ed},1200,")
        d = json.loads(_get(url))
        blk = (d.get("data") or {}).get(sym) or {}
        rows = blk.get("day") or blk.get("qfqday") or []
        out = {}
        for r in rows:
            dt = r[0][:10]
            if not (sd <= dt <= ed):
                continue
            close = float(r[2])
            vol_hand = float(r[5]) if len(r) > 5 and r[5] not in ("", None) else 0.0
            out[dt] = {"close": close, "amount": vol_hand * 100.0 * close}
        return out

    return _cache(f"cn_{code}_{start}_{end}.json", _fetch)


def fetch_navs(code: str, start: str, end: str) -> dict[str, dict[str, float]]:
    """东财 lsjz → {date: {dwjz(单位净值), ljjz(累计净值)}}。分页从新到旧翻。"""
    sd = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    ed = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

    def _fetch():
        out: dict[str, dict[str, float]] = {}
        page, page_size, total = 1, 20, None
        while True:
            url = ("https://api.fund.eastmoney.com/f10/lsjz?"
                   f"callback=jQuery&fundCode={code}&pageIndex={page}&pageSize={page_size}"
                   f"&startDate=&endDate=&_={int(time.time()*1000)}")
            text = _get(url)
            m = re.search(r"jQuery\((.*)\)\s*$", text, re.S)
            payload = json.loads(m.group(1) if m else text)
            data = payload.get("Data") or {}
            rows = data.get("LSJZList") or []
            if not rows:
                break
            if total is None:
                total = int(payload.get("TotalCount") or data.get("TotalCount") or 0)
            oldest = None
            for r in rows:
                dt, dw, lj = r.get("FSRQ"), r.get("DWJZ"), r.get("LJJZ")
                if not dt or dw in (None, ""):
                    continue
                oldest = dt
                if dt < sd or dt > ed:
                    continue
                try:
                    out[dt] = {"dwjz": float(dw), "ljjz": float(lj) if lj not in (None, "") else float(dw)}
                except (TypeError, ValueError):
                    continue
            if oldest is not None and oldest < sd:
                break
            if total and page * page_size >= total:
                break
            if page >= 60:
                break
            page += 1
            time.sleep(0.12)
        return out

    return _cache(f"nav_{code}_{start}_{end}.json", _fetch)


def fetch_bench(sym: str, start: str, end: str) -> dict[str, float]:
    """新浪美股日线 → {us_date: close}。剔除尚未收盘的当日在途 K。

    腾讯 fqkline 对美股只返回边界行、Yahoo 被 403，故用新浪 US_MinKService。
    口径为不复权收盘；本脚本只用它算「跨日涨跌比例」，QQQ/SPY 股息率极低，
    对 1~2 日折算因子的影响可忽略。
    """
    sd = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    ed = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    today_s = (datetime.now(UTC) + timedelta(hours=8)).strftime("%Y-%m-%d")

    def _fetch():
        url = ("https://stock.finance.sina.com.cn/usstock/api/json_v2.php/"
               f"US_MinKService.getDailyK?symbol={sym}")
        text = _get(url)
        i = text.find("[")
        rows = json.loads(text[i:]) if i >= 0 else []
        out = {}
        for r in rows:
            dt = str(r.get("d") or "")[:10]
            c = r.get("c")
            if not dt or c in (None, ""):
                continue
            # 美股交易日 == 北京当日的那场收在北京次日凌晨 → 尚未完成，剔除
            if dt >= today_s:
                continue
            if sd <= dt <= ed:
                out[dt] = float(c)
        return out

    return _cache(f"bench_{sym}_{start}_{end}.json", _fetch)


def fetch_fx(start: str, end: str) -> dict[str, float]:
    """Frankfurter(ECB) USD→CNY 日度 → {date: rate}。"""
    sd = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    ed = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

    def _fetch():
        url = f"https://api.frankfurter.app/{sd}..{ed}?from=USD&to=CNY"
        d = json.loads(_get(url))
        return {k: float(v["CNY"]) for k, v in (d.get("rates") or {}).items() if v.get("CNY")}

    return _cache(f"fx_{start}_{end}.json", _fetch)


# ---------------------------------------------------------------- 对齐与计算
class BenchRMB:
    """基准的人民币口径序列：bench_usd(us_date) × fx(<=us_date)。"""

    def __init__(self, bench: dict[str, float], fx: dict[str, float]):
        self.us_dates = sorted(bench)
        self.bench = bench
        self.fx_dates = sorted(fx)
        self.fx = fx
        self._rmb: dict[str, float] = {}
        for u in self.us_dates:
            r = self._fx_on_or_before(u)
            if r:
                self._rmb[u] = bench[u] * r

    def _fx_on_or_before(self, d: str) -> float | None:
        lo, hi, best = 0, len(self.fx_dates) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.fx_dates[mid] <= d:
                best = self.fx_dates[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return self.fx.get(best) if best else None

    def rmb(self, us_date: str | None) -> float | None:
        return self._rmb.get(us_date) if us_date else None

    def us_on_or_before(self, d: str) -> str | None:
        """美股交易日 <= d 中最新的一个（含 d 当晚那场，若已收盘）。"""
        lo, hi, best = 0, len(self.us_dates) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.us_dates[mid] <= d:
                best = self.us_dates[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

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


CANDS = ["A0", "A1", "A2"]
CAND_DESC = {
    "A0": "净值(D)参考「美股交易日==D」那一场（D当晚，收在D+1凌晨）",
    "A1": "净值(D)参考「D之前最后一个美股交易日」（收在D当天凌晨）",
    "A2": "净值(D)再往前一个美股交易日",
}


def detect_lag(navs: dict[str, dict[str, float]], br: BenchRMB) -> dict[str, Any]:
    """用净值日收益 vs 基准RMB日收益的相关性，判定净值参考时点。"""
    ds = sorted(navs)
    res: dict[str, Any] = {"corr": {}, "n": {}}
    for cand in CANDS:
        xs, ys = [], []
        for i in range(1, len(ds)):
            d0, d1 = ds[i - 1], ds[i]
            n0, n1 = navs[d0]["ljjz"], navs[d1]["ljjz"]
            if n0 <= 0 or n1 <= 0:
                continue
            r0, r1 = br.ref_for(d0, cand), br.ref_for(d1, cand)
            b0, b1 = br.rmb(r0), br.rmb(r1)
            if not b0 or not b1 or r0 == r1:
                continue
            xs.append(n1 / n0 - 1.0)
            ys.append(b1 / b0 - 1.0)
        res["corr"][cand] = pearson(xs, ys)
        res["n"][cand] = len(xs)
    valid = {k: v for k, v in res["corr"].items() if v == v}
    res["best"] = max(valid, key=lambda k: valid[k]) if valid else "A1"
    return res


def compute_premiums(cn: dict[str, dict[str, float]],
                     navs: dict[str, dict[str, float]],
                     br: BenchRMB,
                     cand: str) -> list[dict[str, Any]]:
    """逐日：naive溢价、真溢价、隔夜基准涨跌、成交额。"""
    rows = []
    for d in sorted(navs):
        if d not in cn:
            continue
        nav = navs[d]["dwjz"]
        if nav <= 0:
            continue
        price = cn[d]["close"]
        cur = br.us_before(d, 1)          # A股收盘时已知的最新美股收盘
        ref = br.ref_for(d, cand)         # 净值参考的美股收盘
        b_cur, b_ref = br.rmb(cur), br.rmb(ref)
        naive = (price - nav) / nav * 100.0
        row = {
            "date": d, "price": price, "nav": nav,
            "naive_prem": naive, "amount": cn[d]["amount"],
            "us_cur": cur, "us_ref": ref,
        }
        if b_cur and b_ref:
            nav_est = nav * (b_cur / b_ref)
            row["nav_est"] = nav_est
            row["true_prem"] = (price / nav_est - 1.0) * 100.0
            row["adj_pct"] = (b_cur / b_ref - 1.0) * 100.0   # 折算幅度=隔夜/跨日基准涨跌
        rows.append(row)
    return rows


def stats_of(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    sv = sorted(vals)
    n = len(vals)
    buy = sum(1 for v in vals if v < BUY_TH)
    caution = sum(1 for v in vals if BUY_TH <= v < CAUTION_TH)
    avoid = sum(1 for v in vals if v >= CAUTION_TH)
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    return {
        "n": n, "mean": round(mean, 3), "sd": round(sd, 3),
        "median": round(pct(sv, 50), 3), "p10": round(pct(sv, 10), 3),
        "p25": round(pct(sv, 25), 3), "p75": round(pct(sv, 75), 3),
        "p90": round(pct(sv, 90), 3), "min": round(sv[0], 3), "max": round(sv[-1], 3),
        "buy_n": buy, "buy_pct": round(buy / n * 100, 1),
        "caution_n": caution, "caution_pct": round(caution / n * 100, 1),
        "avoid_n": avoid, "avoid_pct": round(avoid / n * 100, 1),
    }


def group_daily_best(items: list[dict[str, Any]], group: str, key: str,
                     min_amount: float | None) -> list[dict[str, Any]]:
    """每日同组最低溢价（可选成交额过滤）。"""
    by_date: dict[str, list[tuple[str, str, float, float]]] = {}
    for it in items:
        if it["group"] != group:
            continue
        for r in it["rows"]:
            v = r.get(key)
            if v is None:
                continue
            by_date.setdefault(r["date"], []).append((it["code"], it["name"], v, r["amount"]))
    out = []
    for d in sorted(by_date):
        pool = by_date[d]
        if min_amount is not None:
            filt = [x for x in pool if x[3] >= min_amount]
            if filt:
                pool = filt
        best = min(pool, key=lambda x: x[2])
        out.append({"date": d, "code": best[0], "name": best[1],
                    "prem": round(best[2], 3), "signal": signal_for(best[2]),
                    "amount_wan": round(best[3] / 1e4, 1), "n_pool": len(by_date[d])})
    return out


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="QDII 真溢价（估算净值口径）回测与新旧信号对比")
    ap.add_argument("--start", default="20250101")
    ap.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    ap.add_argument("--codes", default="", help="逗号分隔，只跑部分代码")
    ap.add_argument("--json", default="", help="结果 JSON 输出路径")
    ap.add_argument("--report", default="", help="报告文本输出路径(UTF-8)")
    ap.add_argument("--min-amount", type=float, default=MIN_AMOUNT, help="成交额过滤下限(元)")
    args = ap.parse_args()
    say = Tee(Path(args.report) if args.report else None)

    only = {c.strip() for c in args.codes.split(",") if c.strip()} or None
    watch = load_watchlist(only)
    say(f"标的 {len(watch)} 只 · 区间 {args.start} → {args.end}\n")

    # 基准与汇率（多取 15 天前置，供跨日折算）
    pad_start = (datetime.strptime(args.start, "%Y%m%d") - timedelta(days=20)).strftime("%Y%m%d")
    fx = fetch_fx(pad_start, args.end)
    say(f"汇率 USDCNY: {len(fx)} 日 · 最新 {max(fx)}={fx[max(fx)]:.4f}")
    bench_rmb: dict[str, BenchRMB] = {}
    for g, sym in BENCH_SYM.items():
        b = fetch_bench(sym, pad_start, args.end)
        bench_rmb[g] = BenchRMB(b, fx)
        say(f"基准 {g}({sym}): {len(b)} 个美股交易日 · 最新收盘日 {max(b)}")
    say()

    items: list[dict[str, Any]] = []
    for it in watch:
        code, g = it["code"], it["group"]
        br = bench_rmb.get(g)
        if br is None:
            continue
        say(f"  … {code} {it['name']}", flush=True)
        try:
            cn = fetch_cn_daily(code, args.start, args.end)
            navs = fetch_navs(code, args.start, args.end)
        except Exception as e:  # noqa: BLE001
            say(f"    FAIL {e}")
            continue
        if not cn or not navs:
            say(f"    跳过（价格 {len(cn)} 日 / 净值 {len(navs)} 日）")
            continue
        lag = detect_lag(navs, br)
        rows = compute_premiums(cn, navs, br, lag["best"])
        naive_vals = [r["naive_prem"] for r in rows]
        true_vals = [r["true_prem"] for r in rows if "true_prem" in r]
        both = [r for r in rows if "true_prem" in r]
        # 污染体检：溢价 vs 跨日基准涨跌 的相关性
        corr_naive_adj = pearson([r["naive_prem"] for r in both], [r["adj_pct"] for r in both])
        corr_true_adj = pearson([r["true_prem"] for r in both], [r["adj_pct"] for r in both])
        flip_to_avoid = sum(1 for r in both if r["naive_prem"] < BUY_TH <= r["true_prem"])
        flip_to_buy = sum(1 for r in both if r["true_prem"] < BUY_TH <= r["naive_prem"])
        items.append({
            **it, "rows": rows, "lag": lag,
            "naive": stats_of(naive_vals), "true": stats_of(true_vals),
            "corr_naive_adj": corr_naive_adj, "corr_true_adj": corr_true_adj,
            "flip_to_avoid": flip_to_avoid, "flip_to_buy": flip_to_buy,
            "n_both": len(both),
        })
        time.sleep(0.2)

    if not items:
        say("无可用数据")
        return 1

    # ---------------- 报告
    say("\n" + "=" * 108)
    say("一、净值参考时点判定（净值日收益 vs 基准人民币日收益 的相关系数，越高越吻合）")
    say("-" * 108)
    for c in CANDS:
        say(f"   {c}: {CAND_DESC[c]}")
    say("-" * 108)
    say(f"{'代码':<8}{'名称':<20}{'A0':>9}{'A1':>9}{'A2':>9}{'判定':>6}{'样本':>6}")
    for it in items:
        c = it["lag"]["corr"]
        f = lambda k: (f"{c[k]:.3f}" if c.get(k) == c.get(k) else "  n/a")
        say(f"{it['code']:<8}{it['name']:<20}{f('A0'):>9}{f('A1'):>9}{f('A2'):>9}"
              f"{it['lag']['best']:>6}{it['lag']['n'].get(it['lag']['best'],0):>6}")

    best_votes: dict[str, int] = {}
    for it in items:
        best_votes[it["lag"]["best"]] = best_votes.get(it["lag"]["best"], 0) + 1
    say(f"\n   判定汇总：{best_votes}")

    say("\n" + "=" * 108)
    say("二、新旧口径对比（naive=披露净值 / true=估算净值）")
    say("-" * 108)
    say(f"{'代码':<8}{'名称':<18}{'N':>4}"
          f"{'naive均':>8}{'true均':>8}{'naive中位':>10}{'true中位':>9}"
          f"{'naiveSD':>9}{'trueSD':>8}"
          f"{'naive可投%':>11}{'true可投%':>10}{'假绿灯':>7}{'漏买':>6}")
    for it in items:
        a, b = it["naive"], it["true"]
        if not b.get("n"):
            continue
        say(f"{it['code']:<8}{it['name']:<18}{b['n']:>4}"
              f"{a['mean']:>8.2f}{b['mean']:>8.2f}{a['median']:>10.2f}{b['median']:>9.2f}"
              f"{a['sd']:>9.2f}{b['sd']:>8.2f}"
              f"{a['buy_pct']:>10.1f}%{b['buy_pct']:>9.1f}%"
              f"{it['flip_to_avoid']:>7}{it['flip_to_buy']:>6}")
    say("\n   假绿灯 = naive说可投(<2%) 但 true≥2%（会让你在贵的时候买）")
    say("   漏买   = true说可投 但 naive≥2%（会让你错过便宜）")

    say("\n" + "=" * 108)
    say("三、污染体检：溢价与「跨日基准涨跌」的相关性（naive 越高说明混入越多隔夜噪音）")
    say("-" * 108)
    say(f"{'代码':<8}{'名称':<20}{'corr(naive,隔夜)':>18}{'corr(true,隔夜)':>17}")
    for it in items:
        cn_, ct = it["corr_naive_adj"], it["corr_true_adj"]
        say(f"{it['code']:<8}{it['name']:<20}"
              f"{(f'{cn_:.3f}' if cn_==cn_ else 'n/a'):>18}{(f'{ct:.3f}' if ct==ct else 'n/a'):>17}")

    say("\n" + "=" * 108)
    say(f"四、同组每日最低溢价（true 口径）· 成交额过滤下限 {args.min_amount/1e8:.2f} 亿")
    say("-" * 108)
    group_best: dict[str, Any] = {}
    for g in sorted({it["group"] for it in items}):
        raw = group_daily_best(items, g, "true_prem", None)
        filt = group_daily_best(items, g, "true_prem", args.min_amount)
        naive_raw = group_daily_best(items, g, "naive_prem", None)
        group_best[g] = {"true_filtered": filt, "true_raw": raw, "naive_raw": naive_raw}
        if not filt:
            continue
        def summarize(rows, label):
            vals = sorted(r["prem"] for r in rows)
            buy = sum(1 for r in rows if r["prem"] < BUY_TH)
            say(f"   {label}: 交易日 {len(rows)} · 可投日 {buy}({buy/len(rows)*100:.1f}%) · "
                  f"最低 {vals[0]:.2f}% · P25 {pct(vals,25):.2f}% · 中位 {pct(vals,50):.2f}%")
        say(f"\n【{g}】")
        summarize(naive_raw, "naive口径·不过滤")
        summarize(raw, "true 口径·不过滤 ")
        summarize(filt, "true 口径·成交额过滤")
        diff = sum(1 for x, y in zip(raw, filt) if x["date"] == y["date"] and x["code"] != y["code"])
        say(f"   过滤改变了 {diff} 天的「该买哪只」（避免被引到成交额不足的小 ETF）")
        latest = filt[-1]
        say(f"   最新 {latest['date']}：{latest['code']} {latest['name']} "
              f"真溢价 {latest['prem']:.2f}% ({latest['signal']}) 成交额 {latest['amount_wan']:.0f}万")

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start": args.start, "end": args.end,
        "method": {
            "naive": "(close - 披露单位净值)/披露单位净值",
            "true": "close / (单位净值 × 基准RMB(cur)/基准RMB(ref)) - 1",
            "cand_desc": CAND_DESC,
            "min_amount": args.min_amount,
            "thresholds": {"buy": BUY_TH, "caution": CAUTION_TH},
        },
        "items": [{k: v for k, v in it.items() if k != "rows"} | {"rows": it["rows"]} for it in items],
        "group_best": group_best,
    }
    path = Path(args.json) if args.json else (CACHE_DIR / f"true_premium_{args.start}_{args.end}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"\nJSON → {path}")
    if args.report:
        say(f"报告 → {args.report}")
    say.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
