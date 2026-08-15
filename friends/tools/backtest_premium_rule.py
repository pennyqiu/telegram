#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检验「场内 QDII 只在低溢价时买」这条纪律，在长期定投里到底值多少钱。

yyang 方案的头号风险是溢价：场内价格高于净值时买入，等溢价回归就会白亏。
本脚本用真实历史数据回测四条买入规则，看纪律有没有兑现为收益。

数据：
  - 场内不复权收盘价：东财日 K（fqt=0）
  - 基金单位净值 DWJZ：东财 f10/lsjz（每页 20 条，需翻页）
  - 日溢价% =（收盘价 − 单位净值）/ 单位净值
    QDII 净值披露滞后约 1 日，按披露日对齐，与 fetch_qdii_premium.py 口径一致

规则：
  R0 无脑买   ：每月固定买入，不看溢价（基准）
  R1 溢价高改投红利：溢价 ≥ 阈值时，本月这笔钱改买红利 ETF
  R2 溢价高就等  ：溢价 ≥ 阈值时钱留现金，等溢价回落再补买
  R3 同类比价   ：在同指数的多只 ETF 里买溢价最低的那只

用法：
  python3 friends/tools/backtest_premium_rule.py
  python3 friends/tools/backtest_premium_rule.py --threshold 0.02 --json /tmp/prem.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
import urllib.request
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
DATA_DIR = TOOLS_DIR / "backtest_data"
NAV_DIR = DATA_DIR / "nav"
PRICE_DIR = DATA_DIR / "raw_price"

H = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Referer": "https://fundf10.eastmoney.com/",
}

# 同指数分组：用于 R3 比价
GROUPS = {
    "纳指100": ["513100", "159941", "513300"],
    "标普500": ["513500", "159612"],
}
DIVIDEND_ETF = "510880"   # 溢价过高时的替代去处（境内资产，无溢价问题）


def _get(url: str, tries: int = 6) -> str:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"请求失败 {url}：{last}")


def secid(code: str) -> str:
    return f"1.{code}" if code.startswith(("5", "6")) else f"0.{code}"


def fetch_raw_price(code: str) -> dict[str, float]:
    """不复权收盘价（算溢价必须用不复权，要和净值同口径）"""
    out = PRICE_DIR / f"{code}.csv"
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            return {r["date"]: float(r["close"]) for r in csv.DictReader(fh)}
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid(code)}&fields1=f1,f2,f3&fields2=f51,f53"
        "&klt=101&fqt=0&beg=0&end=20500101&lmt=1000000"
    )
    payload = json.loads(_get(url))
    rows = [(l.split(",")[0], float(l.split(",")[1]))
            for l in payload["data"]["klines"]]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close"])
        w.writerows(rows)
    print(f"    价格 {code}: {len(rows)} 天 {rows[0][0]}→{rows[-1][0]}", flush=True)
    return dict(rows)


def fetch_nav(code: str) -> dict[str, float]:
    """单位净值全历史。接口每页固定 20 条，只能翻页。"""
    out = NAV_DIR / f"{code}.csv"
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            return {r["date"]: float(r["nav"]) for r in csv.DictReader(fh)}
    navs: dict[str, float] = {}
    page, total = 1, None
    while True:
        url = (
            "https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery"
            f"&fundCode={code}&pageIndex={page}&pageSize=20"
            f"&startDate=&endDate=&_={int(time.time() * 1000)}"
        )
        text = _get(url)
        m = re.search(r"jQuery\((.*)\)", text, re.S)
        payload = json.loads(m.group(1) if m else text)
        if total is None:
            total = int(payload.get("TotalCount") or 0)
        rows = (payload.get("Data") or {}).get("LSJZList") or []
        if not rows:
            break
        for r in rows:
            if r.get("FSRQ") and r.get("DWJZ") not in (None, ""):
                try:
                    navs[r["FSRQ"]] = float(r["DWJZ"])
                except ValueError:
                    continue
        if total and len(navs) >= total:
            break
        page += 1
        if page > 400:
            break
        time.sleep(0.15)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "nav"])
        w.writerows(sorted(navs.items()))
    days = sorted(navs)
    print(f"    净值 {code}: {len(navs)} 天 {days[0]}→{days[-1]}", flush=True)
    return navs


def premium_series(code: str) -> dict[str, float]:
    """{YYYY-MM-DD: 溢价率}，仅保留价格与净值都有的交易日。

    份额折算日（如 159941 于 2022-07-04 做过 4:1 折算）净值会跳变而价格未同步，
    会算出 +297% 这种假溢价，按绝对值 50% 剔除。
    """
    price = fetch_raw_price(code)
    nav = fetch_nav(code)
    return {
        d: price[d] / nav[d] - 1
        for d in sorted(set(price) & set(nav))
        if nav[d] > 0 and abs(price[d] / nav[d] - 1) < 0.5
    }


def month_end_map(daily: dict[str, float]) -> dict[str, tuple[str, float]]:
    """{YYYY-MM: (该月最后一个有效交易日, 值)}"""
    out: dict[str, tuple[str, float]] = {}
    for d in sorted(daily):
        out[d[:7]] = (d, daily[d])
    return out


def total_return_series(code: str) -> dict[str, float]:
    """后复权月末净值（买入后的实际增值口径），来自 fetch_backtest_data.py 的缓存"""
    path = DATA_DIR / f"{code}.csv"
    with path.open(encoding="utf-8") as fh:
        daily = {r["date"]: float(r["close"]) for r in csv.DictReader(fh)}
    return {m: v for m, (_, v) in month_end_map(daily).items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.02,
                    help="溢价阈值，默认 2%%（yyang 规则）")
    ap.add_argument("--monthly", type=float, default=100_000 / 12,
                    help="每月投入金额")
    ap.add_argument("--json", help="结果写出到 JSON")
    args = ap.parse_args()

    thr = args.threshold
    print("=" * 82)
    print(f"拉取数据（溢价阈值 {thr:.0%}）")
    print("=" * 82)

    codes = sorted({c for g in GROUPS.values() for c in g})
    prem: dict[str, dict[str, float]] = {}
    for c in codes:
        print(f"  {c}")
        try:
            prem[c] = premium_series(c)
        except Exception as exc:  # noqa: BLE001
            print(f"    跳过（{exc}）")
    tr = {c: total_return_series(c) for c in prem if (DATA_DIR / f"{c}.csv").exists()}
    tr[DIVIDEND_ETF] = total_return_series(DIVIDEND_ETF)

    print()
    print("=" * 82)
    print("① 各 ETF 历史溢价分布（日频）")
    print("=" * 82)
    print(f"  {'代码':8s} {'区间':>21s} {'天数':>6s} {'中位':>7s} {'均值':>7s} "
          f"{'>2%占比':>8s} {'>5%占比':>8s} {'最大':>8s}")
    prem_stats = {}
    for c, s in prem.items():
        vals = list(s.values())
        days = sorted(s)
        prem_stats[c] = {
            "start": days[0], "end": days[-1], "n": len(vals),
            "median": statistics.median(vals),
            "mean": statistics.fmean(vals),
            "share_gt2": sum(v > 0.02 for v in vals) / len(vals),
            "share_gt5": sum(v > 0.05 for v in vals) / len(vals),
            "max": max(vals),
        }
        p = prem_stats[c]
        print(f"  {c:8s} {p['start']}→{p['end']} {p['n']:6d} "
              f"{p['median']:7.2%} {p['mean']:7.2%} {p['share_gt2']:8.1%} "
              f"{p['share_gt5']:8.1%} {p['max']:8.1%}")

    # ---- 逐组回测四条规则 ----
    results: dict[str, dict] = {}
    for gname, members in GROUPS.items():
        avail = [c for c in members if c in prem and c in tr]
        if not avail:
            continue
        primary = avail[0]
        pm_all = {c: month_end_map(prem[c]) for c in avail}
        pm_prem = pm_all[primary]
        months = sorted(
            m for m in pm_prem
            if m in tr[primary] and m in tr[DIVIDEND_ETF]
        )
        # 需要下个月才有收益，故最后一个月只作为终点
        months = [m for m in months if m >= min(months)]
        if len(months) < 24:
            continue

        print()
        print("=" * 82)
        print(f"② {gname}：四条买入规则对比（主标的 {primary}，"
              f"{months[0]}→{months[-1]}，每月 {args.monthly:,.0f} 元）")
        print("=" * 82)

        def run(rule: str) -> dict:
            units: dict[str, float] = {}      # code -> 累计"份额"(按后复权净值计)
            cash = 0.0
            invested = 0.0
            skipped = 0
            diverted = 0.0
            for m in months:
                invested += args.monthly
                budget = args.monthly + (cash if rule == "R2" else 0.0)
                p = pm_prem[m][1]
                if rule == "R0":
                    buy, code = budget, primary
                elif rule == "R1":
                    if p >= thr:
                        buy, code = budget, DIVIDEND_ETF
                        diverted += budget
                        skipped += 1
                    else:
                        buy, code = budget, primary
                elif rule == "R2":
                    if p >= thr:
                        cash += args.monthly
                        skipped += 1
                        continue
                    buy, code = budget, primary
                    cash = 0.0
                else:  # R3 同类比价
                    cands = [
                        (c, pm_all[c][m][1])
                        for c in avail
                        if m in pm_all[c] and m in tr[c]
                    ]
                    code = min(cands, key=lambda kv: kv[1])[0] if cands else primary
                    buy = budget
                    if code != primary:
                        diverted += budget
                        skipped += 1
                units[code] = units.get(code, 0.0) + buy / tr[code][m]
            final = sum(u * tr[c][months[-1]] for c, u in units.items()) + (
                cash if rule == "R2" else 0.0
            )
            return {
                "final": final,
                "invested": invested,
                "multiple": final / invested,
                "skipped_months": skipped,
                "diverted": diverted,
                "held": {c: u * tr[c][months[-1]] for c, u in units.items()},
            }

        labels = {
            "R0": "无脑按月买（基准）",
            "R1": f"溢价≥{thr:.0%} 改投红利",
            "R2": f"溢价≥{thr:.0%} 留现金等回落",
            "R3": "同类比价买最低溢价",
        }
        base = run("R0")
        rows = {}
        for rule in ("R0", "R1", "R2", "R3"):
            r = run(rule)
            r["vs_base"] = r["final"] / base["final"] - 1
            rows[rule] = r
            print(f"  {labels[rule]:22s} 终值={r['final']/1e4:7.1f}万  "
                  f"倍数={r['multiple']:5.3f}x  相对基准={r['vs_base']:+6.2%}  "
                  f"触发月数={r['skipped_months']:3d}/{len(months)}")
        results[gname] = {
            "primary": primary,
            "members": avail,
            "months": [months[0], months[-1]],
            "n_months": len(months),
            "rules": rows,
            "labels": labels,
        }

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"threshold": thr, "monthly": args.monthly,
                 "premium_stats": prem_stats, "results": results},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n已写出 {args.json}")


if __name__ == "__main__":
    main()
