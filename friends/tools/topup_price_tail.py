#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补齐日线 CSV 的尾部缺口（东财 kline 接口限流时的兜底）。

东财 push2his 偶发连续拒连，fetch_qdii_quant_data.py 会整只失败；
这里改走腾讯（A股）/新浪（美股）只抓最近一段接到原序列尾部。

两类目标处理方式不同，因为口径不同：
  不复权序列（raw_price/、USDCNY）——远端与东财逐日完全一致（已用 513390 全序列
    796/796 对齐验证），故直接采信远端，重叠日一并覆盖。覆盖是必要的：若上次抓取
    发生在 A 股盘中，本地最后一行是盘中快照而非收盘价，留着会把溢价算错。
  后复权序列（QQQ.csv）——远端给不复权，两者相差一个常数因子。取最后一个重叠日
    定标后缩放，缺口内无分红时精确成立。

净值另走一条路：东财 pingzhongdata 一次返回全历史且很少限流，直接整段覆盖，
复用 fetch_qdii_quant_data.fetch_navs，不重复实现。

用法：
  python3 friends/tools/topup_price_tail.py            # 补 raw_price + 净值 + QQQ + 汇率
  python3 friends/tools/topup_price_tail.py --only 159501,QQQ
  python3 friends/tools/topup_price_tail.py --no-nav --days 120
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
DATA_DIR = TOOLS_DIR / "backtest_data"
CST = timezone(timedelta(hours=8))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# 目标 -> (相对 backtest_data 的路径, 腾讯 symbol)
TARGETS: dict[str, tuple[str, str]] = {
    "513870": ("raw_price/513870.csv", "sh513870"),
    "159696": ("raw_price/159696.csv", "sz159696"),
    "513390": ("raw_price/513390.csv", "sh513390"),
    "159660": ("raw_price/159660.csv", "sz159660"),
    "159501": ("raw_price/159501.csv", "sz159501"),
}


def _get(url: str, tries: int = 6) -> str:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * 1.6**attempt)
    raise RuntimeError(f"请求失败（{tries} 次）：{last}")


def read_csv(path: Path, col: str) -> list[tuple[str, float]]:
    with path.open(encoding="utf-8") as fh:
        return [(r["date"], float(r[col])) for r in csv.DictReader(fh) if r[col]]


def write_csv(path: Path, rows: list[tuple[str, float]], col: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", col])
        w.writerows(rows)


def fetch_tencent(sym: str, start: str, end: str) -> dict[str, float]:
    """不复权日收盘 {date: close}。美股当日那场收在北京次日凌晨，未完成的剔除。"""
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={sym},day,{start},{end},1200,")
    blk = (json.loads(_get(url)).get("data") or {}).get(sym) or {}
    rows = blk.get("day") or blk.get("qfqday") or []
    today = datetime.now(CST).strftime("%Y-%m-%d")
    out: dict[str, float] = {}
    for r in rows:
        d = str(r[0])[:10]
        if start <= d <= end and not (sym.startswith("us") and d >= today):
            out[d] = float(r[2])
    return out


def fetch_sina_us(sym: str, start: str, end: str) -> dict[str, float]:
    """新浪美股日线 {date: 不复权收盘}。腾讯 fqkline 对美股只返回边界行，故走新浪。

    美股交易日 == 北京当日的那场收在北京次日凌晨，未完成的剔除。
    """
    url = ("https://stock.finance.sina.com.cn/usstock/api/json_v2.php/"
           f"US_MinKService.getDailyK?symbol={sym}")
    text = _get(url)
    i = text.find("[")
    rows = json.loads(text[i:]) if i >= 0 else []
    today = datetime.now(CST).strftime("%Y-%m-%d")
    out: dict[str, float] = {}
    for r in rows:
        d = str(r.get("d") or "")[:10]
        c = r.get("c")
        if d and c not in (None, "") and start <= d <= end and d < today:
            out[d] = float(c)
    return out


def fetch_fx(start: str, end: str) -> dict[str, float]:
    url = f"https://api.frankfurter.app/{start}..{end}?from=USD&to=CNY"
    payload = json.loads(_get(url))
    return {k: float(v["CNY"]) for k, v in (payload.get("rates") or {}).items()
            if v.get("CNY")}


def topup(name: str, rel: str, col: str, fetcher, days: int, rescale: bool) -> str:
    path = DATA_DIR / rel
    if not path.exists():
        return f"skip  {name}: 本地无序列，先跑 fetch_qdii_quant_data.py"
    have = dict(read_csv(path, col))
    if not have:
        return f"skip  {name}: 本地序列为空"
    last = max(have)
    start = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now(CST).strftime("%Y-%m-%d")

    new = fetcher(start, end)
    if not new:
        return f"FAIL  {name}: 接口无数据"

    note = ""
    if rescale:
        # 后复权本地序列：用最后一个重叠日把远端不复权值定标到本地尺度
        overlap = sorted(set(new) & set(have))
        if not overlap:
            return f"FAIL  {name}: 与本地序列无重叠日，无法定标"
        anchor = overlap[-1]
        factor = have[anchor] / new[anchor]
        add = {d: round(v * factor, 6) for d, v in new.items() if d > last}
        note = f"因子 {factor:.6f} @ {anchor}；"
    else:
        # 同口径：重叠日一并覆盖，顺手修掉可能存在的盘中快照
        fixed = sum(1 for d, v in new.items() if d in have and abs(have[d] - v) > 1e-9)
        add = dict(new)
        if fixed:
            note = f"修正重叠日 {fixed} 天；"

    fresh = [d for d in add if d > last]
    if not fresh and not note:
        return f"skip  {name}: 无新交易日（本地已到 {last}）"
    have.update(add)
    rows = sorted(have.items())
    write_csv(path, rows, col)
    tail = "，".join(f"{d} {v:g}" for d, v in rows[-3:])
    return f"ok    {name}: +{len(fresh)} 天 → {rows[-1][0]}（{note}{tail}）"


def topup_nav(code: str) -> str:
    """单位净值与累计净值：pingzhongdata 一次给全历史，整段覆盖即可。"""
    from fetch_qdii_quant_data import fetch_navs  # 同目录，避免重复实现

    nav, acc = fetch_navs(code)
    if not nav:
        return f"FAIL  {code}/nav: 净值为空"
    write_csv(DATA_DIR / "nav" / f"{code}.csv", nav, "nav")
    parts = [f"单位净值 {len(nav)} 天 → {nav[-1][0]}"]
    if acc:
        write_csv(DATA_DIR / "nav_acc" / f"{code}.csv", acc, "acc")
        parts.append(f"累计净值 {len(acc)} 天")
    return f"ok    {code}/nav: " + "，".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90, help="向前取多少天以保证有重叠")
    ap.add_argument("--only", default="", help="只补这些目标，逗号分隔（含 USDCNY）")
    ap.add_argument("--no-nav", action="store_true", help="跳过净值刷新")
    args = ap.parse_args()

    keep = {s.strip() for s in args.only.split(",") if s.strip()}
    # (名称, 路径, 列名, 取数, 是否需要定标缩放)
    jobs: list[tuple[str, str, str, object, bool]] = [
        (name, rel, "close", (lambda s, e, sym=sym: fetch_tencent(sym, s, e)), False)
        for name, (rel, sym) in TARGETS.items()
    ]
    jobs.append(("QQQ", "QQQ.csv", "close",
                 lambda s, e: fetch_sina_us("QQQ", s, e), True))
    jobs.append(("USDCNY", "USDCNY.csv", "close", fetch_fx, False))

    failed = 0
    for name, rel, col, fetcher, rescale in jobs:
        if keep and name not in keep:
            continue
        try:
            msg = topup(name, rel, col, fetcher, args.days, rescale)
        except Exception as exc:  # noqa: BLE001
            msg = f"FAIL  {name}: {exc}"
        if msg.startswith("FAIL"):
            failed += 1
        print(msg, flush=True)
        time.sleep(0.6)

    if not args.no_nav:
        for code in TARGETS:
            if keep and code not in keep:
                continue
            try:
                msg = topup_nav(code)
            except Exception as exc:  # noqa: BLE001
                msg = f"FAIL  {code}/nav: {exc}"
            if msg.startswith("FAIL"):
                failed += 1
            print(msg, flush=True)
            time.sleep(0.5)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
