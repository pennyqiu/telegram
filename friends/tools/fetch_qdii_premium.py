#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拉取 A股场内 QDII / 红利 ETF 现价与折溢价（东方财富）

用法：
  python3 friends/tools/fetch_qdii_premium.py
  python3 friends/tools/fetch_qdii_premium.py --out friends/qdii-premium.json

数据字段：
  - price: 场内最新价
  - iopv: 由折价率反推的参考净值（近似 IOPV）
  - premium_pct: 溢价率% = (price - iopv) / iopv * 100  （正数=溢价）
  - discount_pct: 东财「基金折价率」原值%（负数通常表示溢价）
  - signal: buy / caution / avoid  （对应 yyang 规则 <2% / 2–5% / >5%）

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
WATCHLIST = [
    {"code": "513100", "secid": "1.513100", "name": "纳指ETF国泰", "group": "纳指100", "priority": 1},
    {"code": "159941", "secid": "0.159941", "name": "纳指ETF广发", "group": "纳指100", "priority": 2},
    {"code": "513300", "secid": "1.513300", "name": "纳斯达克ETF华夏", "group": "纳指100", "priority": 3},
    {"code": "159632", "secid": "0.159632", "name": "纳斯达克ETF华安", "group": "纳指100", "priority": 4},
    {"code": "513500", "secid": "1.513500", "name": "标普500ETF博时", "group": "标普500", "priority": 1},
    {"code": "159612", "secid": "0.159612", "name": "标普500ETF国泰", "group": "标普500", "priority": 2},
    {"code": "510880", "secid": "1.510880", "name": "红利ETF华泰柏瑞", "group": "红利", "priority": 1},
    {"code": "515080", "secid": "1.515080", "name": "中证红利ETF招商", "group": "红利", "priority": 2},
    {"code": "512890", "secid": "1.512890", "name": "红利低波ETF华泰柏瑞", "group": "红利", "priority": 3},
]

API = (
    "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
    "?fltt=2&invt=2&fields=f12,f14,f2,f3,f5,f6,f8,f18,f152,f184"
    "&secids={secids}"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and v == v:  # not NaN
        return float(v)
    return None


def signal_for(premium_pct: float | None) -> str:
    if premium_pct is None:
        return "unknown"
    if premium_pct < 2:
        return "buy"
    if premium_pct < 5:
        return "caution"
    return "avoid"


def iopv_from_discount(price: float, discount_pct: float) -> float:
    """东财折价率% = (IOPV - price) / IOPV * 100 → IOPV = price / (1 - 折价率/100)"""
    d = discount_pct / 100.0
    if abs(1.0 - d) < 1e-9:
        return price
    return price / (1.0 - d)


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
                "priority": m["priority"],
                "error": "未返回行情",
                "signal": "unknown",
            })
            continue

        price = _num(raw.get("f2"))
        chg = _num(raw.get("f3"))
        discount = _num(raw.get("f184"))  # 基金折价率 %
        amount = _num(raw.get("f6")) or 0.0
        volume = _num(raw.get("f5")) or 0.0
        prev_close = _num(raw.get("f18"))
        name = raw.get("f14") or m["name"]

        iopv = None
        premium = None
        if price is not None and discount is not None:
            iopv = iopv_from_discount(price, discount)
            premium = -discount  # 溢价率 = -折价率

        rows.append({
            "code": code,
            "name": name,
            "group": m["group"],
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
            "signal": signal_for(premium),
            "eastmoney_url": f"https://quote.eastmoney.com/{'sh' if m['secid'].startswith('1.') else 'sz'}{code}.html",
        })

    # 组内按溢价升序（折价优先），同溢价按成交额
    def sort_key(r: dict[str, Any]):
        p = r.get("premium_pct")
        return (r["group"], 999 if p is None else p, -(r.get("amount") or 0))

    rows.sort(key=sort_key)
    return rows


def build_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(CST)
    # 各组最优（溢价最低且可买优先）
    best: dict[str, Any] = {}
    for g in ("纳指100", "标普500", "红利"):
        cands = [r for r in rows if r.get("group") == g and r.get("premium_pct") is not None]
        if cands:
            best[g] = min(cands, key=lambda r: r["premium_pct"])

    return {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_text": now.strftime("%Y-%m-%d %H:%M:%S") + " CST",
        "source": "eastmoney push2delay ulist (f184 折价率)",
        "rules": {
            "buy": "溢价 < 2%",
            "caution": "溢价 2%–5%",
            "avoid": "溢价 > 5%",
            "note": "同类多只比价，永远买溢价最低的那只；红利通常无 QDII 溢价问题，仍一并展示。",
        },
        "best_by_group": {
            g: {
                "code": r["code"],
                "name": r["name"],
                "premium_pct": r["premium_pct"],
                "price": r["price"],
                "signal": r["signal"],
            }
            for g, r in best.items()
        },
        "items": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取 A股场内 QDII/红利 ETF 溢价")
    root = Path(__file__).resolve().parents[1]  # friends/
    ap.add_argument("--out", type=Path, default=root / "qdii-premium.json")
    ap.add_argument("--pretty", action="store_true", help="打印摘要到 stdout")
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
    if args.pretty or True:
        print(f"{'代码':<8} {'分组':<8} {'名称':<16} {'现价':>8} {'溢价%':>8} {'信号':<8} {'成交额万':>10}")
        for r in rows:
            if r.get("error"):
                print(f"{r['code']:<8} {r['group']:<8} {r['name']:<16} ERROR {r['error']}")
                continue
            sig = {"buy": "✅可买", "caution": "⚠️谨慎", "avoid": "🛑回避"}.get(r["signal"], "?")
            print(
                f"{r['code']:<8} {r['group']:<8} {r['name']:<16} "
                f"{r['price']:>8.3f} {r['premium_pct']:>8.2f} {sig:<8} {r['amount_wan']:>10.1f}"
            )
        print("\n各组最低溢价:")
        for g, b in payload["best_by_group"].items():
            print(f"  {g}: {b['code']} {b['name']} 溢价 {b['premium_pct']}% → {b['signal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
