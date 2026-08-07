#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拉取 A股场内「纳指100 / 标普500」全部 QDII ETF 现价与折溢价（东方财富）

字段（akshare fund_etf_spot_em 同源）：
  - f441 = IOPV 实时估值
  - f402 = 基金折价率%  → 溢价率% = -f402
  - f38  = 最新份额
  - f6   = 成交额

不含：纳指科技/生物等主题、标普油气/消费等非标普500、境内红利。

用法：
  python3 friends/tools/fetch_qdii_premium.py

建议 cron：
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

# 纳指100 / 纳斯达克100 全市场宽基（各家）；排除主题（科技/生物等）
# 标普500 全市场宽基（各家）；排除油气/消费/A股红利等
WATCHLIST = [
    # —— 纳指100 ——
    {"code": "513100", "secid": "1.513100", "name": "纳指ETF国泰", "group": "纳指100", "manager": "国泰"},
    {"code": "159941", "secid": "0.159941", "name": "纳指ETF广发", "group": "纳指100", "manager": "广发"},
    {"code": "513300", "secid": "1.513300", "name": "纳斯达克ETF华夏", "group": "纳指100", "manager": "华夏"},
    {"code": "159632", "secid": "0.159632", "name": "纳斯达克ETF华安", "group": "纳指100", "manager": "华安"},
    {"code": "513110", "secid": "1.513110", "name": "纳指ETF华泰柏瑞", "group": "纳指100", "manager": "华泰柏瑞"},
    {"code": "159513", "secid": "0.159513", "name": "纳斯达克100ETF大成", "group": "纳指100", "manager": "大成"},
    {"code": "159659", "secid": "0.159659", "name": "纳斯达克100ETF招商", "group": "纳指100", "manager": "招商"},
    {"code": "513390", "secid": "1.513390", "name": "纳指100ETF博时", "group": "纳指100", "manager": "博时"},
    {"code": "159660", "secid": "0.159660", "name": "纳指ETF汇添富", "group": "纳指100", "manager": "汇添富"},
    {"code": "159501", "secid": "0.159501", "name": "纳指ETF嘉实", "group": "纳指100", "manager": "嘉实"},
    {"code": "513870", "secid": "1.513870", "name": "纳指ETF富国", "group": "纳指100", "manager": "富国"},
    {"code": "159696", "secid": "0.159696", "name": "纳指ETF易方达", "group": "纳指100", "manager": "易方达"},
    # —— 标普500 ——
    {"code": "513500", "secid": "1.513500", "name": "标普500ETF博时", "group": "标普500", "manager": "博时"},
    {"code": "513650", "secid": "1.513650", "name": "标普500ETF南方", "group": "标普500", "manager": "南方"},
    {"code": "159655", "secid": "0.159655", "name": "标普500ETF华夏", "group": "标普500", "manager": "华夏"},
    {"code": "159612", "secid": "0.159612", "name": "标普500ETF国泰", "group": "标普500", "manager": "国泰"},
]

API = (
    "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
    "?fltt=2&invt=2"
    "&fields=f12,f14,f2,f3,f5,f6,f8,f18,f38,f152,f402,f441"
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


def signal_for(premium_pct: float | None) -> str:
    if premium_pct is None:
        return "unknown"
    if premium_pct < 2:
        return "buy"
    if premium_pct < 5:
        return "caution"
    return "avoid"


def liquidity_tier(amount: float, shares: float | None) -> str:
    """综合成交额与份额，粗分流动性档位（辅助决策，非官方评级）。"""
    amt_yi = amount / 1e8  # 亿
    share_yi = (shares or 0) / 1e8
    if amt_yi >= 1.0 or share_yi >= 50:
        return "高"
    if amt_yi >= 0.3 or share_yi >= 15:
        return "中"
    return "低"


def fetch_quotes() -> list[dict[str, Any]]:
    secids = ",".join(x["secid"] for x in WATCHLIST)
    url = API.format(secids=secids)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
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
                "manager": m["manager"],
                "kind": "qdii",
                "error": "未返回行情",
                "signal": "unknown",
            })
            continue

        price = _num(raw.get("f2"))
        chg = _num(raw.get("f3"))
        iopv = _num(raw.get("f441"))
        discount = _num(raw.get("f402"))
        amount = _num(raw.get("f6")) or 0.0
        volume = _num(raw.get("f5")) or 0.0
        turnover = _num(raw.get("f8"))
        shares = _num(raw.get("f38"))
        prev_close = _num(raw.get("f18"))
        name = raw.get("f14") or m["name"]

        premium = None
        if discount is not None:
            premium = -discount
        if iopv is not None and price is not None and abs(iopv) > 1e-9:
            premium_from_iopv = (price - iopv) / iopv * 100.0
            if premium is None or abs(premium_from_iopv - premium) > 0.3:
                premium = premium_from_iopv
                discount = -premium

        rows.append({
            "code": code,
            "name": name,
            "group": m["group"],
            "manager": m["manager"],
            "kind": "qdii",
            "price": round(price, 4) if price is not None else None,
            "change_pct": round(chg, 2) if chg is not None else None,
            "prev_close": round(prev_close, 4) if prev_close is not None else None,
            "iopv": round(iopv, 4) if iopv is not None else None,
            "discount_pct": round(discount, 2) if discount is not None else None,
            "premium_pct": round(premium, 2) if premium is not None else None,
            "volume": int(volume),
            "amount": round(amount, 2),
            "amount_wan": round(amount / 10000.0, 1),
            "turnover_pct": round(turnover, 2) if turnover is not None else None,
            "shares": int(shares) if shares is not None else None,
            "shares_yi": round(shares / 1e8, 2) if shares is not None else None,
            "liquidity": liquidity_tier(amount, shares),
            "signal": signal_for(premium),
            "eastmoney_url": f"https://quote.eastmoney.com/{'sh' if m['secid'].startswith('1.') else 'sz'}{code}.html",
        })

    # 组内：先按溢价升序，再按成交额降序
    def sort_key(r: dict[str, Any]):
        order = {"纳指100": 0, "标普500": 1}.get(r["group"], 9)
        p = r.get("premium_pct")
        return (order, 999 if p is None else p, -(r.get("amount") or 0))

    rows.sort(key=sort_key)
    return rows


def build_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(CST)
    best: dict[str, Any] = {}
    for g in ("纳指100", "标普500"):
        cands = [r for r in rows if r.get("group") == g and r.get("premium_pct") is not None]
        if not cands:
            continue
        # 综合：优先可买信号，再看溢价，再看流动性
        liq_rank = {"高": 0, "中": 1, "低": 2}

        def score(r):
            return (
                0 if r.get("signal") == "buy" else (1 if r.get("signal") == "caution" else 2),
                r["premium_pct"],
                liq_rank.get(r.get("liquidity"), 9),
            )

        best[g] = min(cands, key=score)

    return {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_text": now.strftime("%Y-%m-%d %H:%M:%S") + " CST",
        "source": "eastmoney push2delay ulist (f441=IOPV, f402=折价率, f38=份额)",
        "field_note": "展示全部纳指100/标普500场内宽基 QDII；决策请综合溢价、流动性、份额，勿只看溢价。",
        "rules": {
            "qdii_buy": "溢价 < 2%",
            "qdii_caution": "溢价 2%–5%",
            "qdii_avoid": "溢价 > 5%",
            "liquidity": "高≈日成交≥1亿或份额≥50亿份；中≈成交≥0.3亿或份额≥15亿；其余为低",
            "note": "同类比价时优先低溢价+够流动性；份额过小易流动性差、溢价更易失控。",
        },
        "counts": {
            "纳指100": sum(1 for r in rows if r.get("group") == "纳指100"),
            "标普500": sum(1 for r in rows if r.get("group") == "标普500"),
        },
        "best_by_group": {
            g: {
                "code": r["code"],
                "name": r["name"],
                "manager": r.get("manager"),
                "premium_pct": r["premium_pct"],
                "price": r["price"],
                "iopv": r.get("iopv"),
                "liquidity": r.get("liquidity"),
                "amount_wan": r.get("amount_wan"),
                "shares_yi": r.get("shares_yi"),
                "signal": r["signal"],
            }
            for g, r in best.items()
        },
        "items": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取场内纳指100/标普500全部 QDII 溢价")
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

    print(f"wrote {args.out}  ({payload['updated_at_text']})  n={len(rows)}")
    sig_map = {"buy": "✅可买", "caution": "⚠️谨慎", "avoid": "🛑回避", "unknown": "?"}
    print(f"{'代码':<8} {'分组':<8} {'公司':<8} {'现价':>7} {'IOPV':>8} {'溢价%':>7} {'份额亿':>7} {'成交万':>8} {'流动':>4} {'信号'}")
    for r in rows:
        if r.get("error"):
            print(f"{r['code']:<8} ERROR {r['error']}")
            continue
        print(
            f"{r['code']:<8} {r['group']:<8} {r['manager']:<8} "
            f"{r['price']:>7.3f} {r['iopv']:>8.4f} {r['premium_pct']:>7.2f} "
            f"{(r.get('shares_yi') or 0):>7.2f} {r['amount_wan']:>8.1f} "
            f"{r['liquidity']:>4} {sig_map.get(r['signal'], r['signal'])}"
        )
    print("\n各组综合参考（溢价优先，兼顾流动性）：")
    for g, b in payload["best_by_group"].items():
        print(f"  {g}: {b['code']} {b['name']} 溢价{b['premium_pct']}% 流动{b['liquidity']} → {b['signal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
