#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拉取 A股场内 QDII / 红利 ETF 现价与折溢价（东方财富）

正确字段（akshare fund_etf_spot_em 同源）：
  - f441 = IOPV 实时估值
  - f402 = 基金折价率%  = (IOPV - 现价) / IOPV * 100
  - 溢价率% = -f402 = (现价 - IOPV) / IOPV * 100
  - ⚠️ f184 是「主力净流入-净占比」，不是折价率（曾误用）

用法：
  python3 friends/tools/fetch_qdii_premium.py

建议 cron（北京时间交易时段每 10 分钟）：
  */10 9-15 * * 1-5 cd /app/telegram && python3 friends/tools/fetch_qdii_premium.py >> /var/log/qdii-premium.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))

# secid: 1=沪市, 0=深市
# kind: qdii = 跨境（看溢价）；domestic = 境内股票ETF（套利畅通，溢价通常≈0）
WATCHLIST = [
    {"code": "513100", "secid": "1.513100", "name": "纳指ETF国泰", "group": "纳指100", "kind": "qdii", "priority": 1},
    {"code": "159941", "secid": "0.159941", "name": "纳指ETF广发", "group": "纳指100", "kind": "qdii", "priority": 2},
    {"code": "513300", "secid": "1.513300", "name": "纳斯达克ETF华夏", "group": "纳指100", "kind": "qdii", "priority": 3},
    {"code": "159632", "secid": "0.159632", "name": "纳斯达克ETF华安", "group": "纳指100", "kind": "qdii", "priority": 4},
    {"code": "513500", "secid": "1.513500", "name": "标普500ETF博时", "group": "标普500", "kind": "qdii", "priority": 1},
    {"code": "159612", "secid": "0.159612", "name": "标普500ETF国泰", "group": "标普500", "kind": "qdii", "priority": 2},
    {"code": "510880", "secid": "1.510880", "name": "红利ETF华泰柏瑞", "group": "红利", "kind": "domestic", "priority": 1},
    {"code": "515080", "secid": "1.515080", "name": "中证红利ETF招商", "group": "红利", "kind": "domestic", "priority": 2},
    {"code": "512890", "secid": "1.512890", "name": "红利低波ETF华泰柏瑞", "group": "红利", "kind": "domestic", "priority": 3},
]

# f441=IOPV, f402=基金折价率（正确）；勿再用 f184
API = (
    "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
    "?fltt=2&invt=2&fields=f12,f14,f2,f3,f5,f6,f8,f18,f152,f402,f441"
    "&secids={secids}"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and v == v:
        return float(v)
    return None


def signal_for(premium_pct: float | None, kind: str) -> str:
    """境内股票 ETF 不套用 QDII 溢价纪律；QDII 按 yyang 阈值。"""
    if kind == "domestic":
        if premium_pct is None:
            return "unknown"
        # 境内一般贴近净值；仅当异常偏离时提示
        if abs(premium_pct) < 0.5:
            return "ok"
        if abs(premium_pct) < 1.5:
            return "caution"
        return "anomaly"
    if premium_pct is None:
        return "unknown"
    if premium_pct < 2:
        return "buy"
    if premium_pct < 5:
        return "caution"
    return "avoid"


def fetch_quotes() -> list[dict[str, Any]]:
    secids = ",".join(x["secid"] for x in WATCHLIST)
    url = API.format(secids=secids)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("rc") != 0 or not payload.get("data") or not payload["data"].get("diff"):
        raise RuntimeError(f"eastmoney 返回异常: {payload.get('rc')} {payload.get('rt')}")

    by_code = {str(x.get("f12")): x for x in payload["data"]["diff"]}
    meta = {x["code"]: x for x in WATCHLIST}
    rows: list[dict[str, Any]] = []

    for code, m in meta.items():
        raw = by_code.get(code)
        if not raw:
            rows.append({
                "code": code,
                "name": m["name"],
                "group": m["group"],
                "kind": m["kind"],
                "priority": m["priority"],
                "error": "未返回行情",
                "signal": "unknown",
            })
            continue

        price = _num(raw.get("f2"))
        chg = _num(raw.get("f3"))
        iopv = _num(raw.get("f441"))
        discount = _num(raw.get("f402"))  # 基金折价率 %
        amount = _num(raw.get("f6")) or 0.0
        volume = _num(raw.get("f5")) or 0.0
        prev_close = _num(raw.get("f18"))
        name = raw.get("f14") or m["name"]

        premium = None
        if discount is not None:
            premium = -discount
        elif price is not None and iopv is not None and abs(iopv) > 1e-9:
            premium = (price - iopv) / iopv * 100.0
            discount = -premium

        # 若有 IOPV，用 IOPV 重算溢价更直观；优先官方 f402
        if iopv is not None and price is not None and abs(iopv) > 1e-9:
            premium_from_iopv = (price - iopv) / iopv * 100.0
            # 与 f402 差太大时以 IOPV 为准
            if premium is None or abs(premium_from_iopv - premium) > 0.3:
                premium = premium_from_iopv
                discount = -premium

        rows.append({
            "code": code,
            "name": name,
            "group": m["group"],
            "kind": m["kind"],
            "priority": m["priority"],
            "price": round(price, 4) if price is not None else None,
            "change_pct": round(chg, 2) if chg is not None else None,
            "prev_close": round(prev_close, 4) if prev_close is not None else None,
            "iopv": round(iopv, 4) if iopv is not None else None,
            "discount_pct": round(discount, 2) if discount is not None else None,
            "premium_pct": round(premium, 2) if premium is not None else None,
            "volume": int(volume),
            "amount": round(amount, 2),
            "amount_wan": round(amount / 10000.0, 1),
            "signal": signal_for(premium, m["kind"]),
            "eastmoney_url": f"https://quote.eastmoney.com/{'sh' if m['secid'].startswith('1.') else 'sz'}{code}.html",
        })

    def sort_key(r: dict[str, Any]):
        p = r.get("premium_pct")
        return (r["group"], 999 if p is None else p, -(r.get("amount") or 0))

    rows.sort(key=sort_key)
    return rows


def build_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(CST)
    best: dict[str, Any] = {}
    for g in ("纳指100", "标普500", "红利"):
        cands = [r for r in rows if r.get("group") == g and r.get("premium_pct") is not None]
        if not cands:
            continue
        if g in ("纳指100", "标普500"):
            # QDII：选溢价最低且优先可买
            best[g] = min(cands, key=lambda r: (0 if r.get("signal") == "buy" else 1, r["premium_pct"]))
        else:
            # 红利：展示贴近净值最好的一只
            best[g] = min(cands, key=lambda r: abs(r["premium_pct"]))

    return {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_text": now.strftime("%Y-%m-%d %H:%M:%S") + " CST",
        "source": "eastmoney push2delay ulist (f441=IOPV, f402=基金折价率)",
        "field_note": "f184 是主力净流入占比，不是折价率；已改用 f402/f441。",
        "rules": {
            "qdii_buy": "溢价 < 2%",
            "qdii_caution": "溢价 2%–5%",
            "qdii_avoid": "溢价 > 5%",
            "domestic": "境内股票 ETF（红利等）套利畅通，溢价通常接近 0；不做 QDII 式「可买/回避」判断。",
            "note": "同类 QDII 多只比价，永远买溢价最低的那只。",
        },
        "best_by_group": {
            g: {
                "code": r["code"],
                "name": r["name"],
                "premium_pct": r["premium_pct"],
                "price": r["price"],
                "iopv": r.get("iopv"),
                "signal": r["signal"],
                "kind": r.get("kind"),
            }
            for g, r in best.items()
        },
        "items": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取 A股场内 QDII/红利 ETF 溢价")
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--out", type=Path, default=root / "qdii-premium.json")
    args = ap.parse_args()

    try:
        rows = fetch_quotes()
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    payload = build_payload(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {args.out}  ({payload['updated_at_text']})")
    sig_map = {
        "buy": "✅可买", "caution": "⚠️谨慎", "avoid": "🛑回避",
        "ok": "✅贴净值", "anomaly": "❗异常偏离", "unknown": "?",
    }
    print(f"{'代码':<8} {'分组':<8} {'kind':<9} {'现价':>8} {'IOPV':>8} {'溢价%':>8} {'信号':<10}")
    for r in rows:
        if r.get("error"):
            print(f"{r['code']:<8} ERROR {r['error']}")
            continue
        print(
            f"{r['code']:<8} {r['group']:<8} {r['kind']:<9} "
            f"{r['price']:>8.3f} {r['iopv']:>8.4f} {r['premium_pct']:>8.2f} "
            f"{sig_map.get(r['signal'], r['signal']):<10}"
        )
    print("\n各组参考：")
    for g, b in payload["best_by_group"].items():
        print(f"  {g}: {b['code']} {b['name']} 溢价 {b['premium_pct']}% → {b['signal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
