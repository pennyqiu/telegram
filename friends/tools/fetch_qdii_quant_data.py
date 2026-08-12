#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 QDII 量化策略回测准备历史序列，缓存成 CSV。

每只场内 QDII 都要四条线，因为它们回答不同的问题：
  backtest_data/{code}.csv           后复权成交价 → 你的钱实际怎么走（含溢价波动）
  backtest_data/raw_price/{code}.csv 不复权成交价 → 算溢价的分子（必须与净值同口径）
  backtest_data/nav/{code}.csv       单位净值     → 算溢价的分母
  backtest_data/nav_acc/{code}.csv   累计净值     → 基金真实业绩（不含溢价，已还原分红与折算）

「后复权成交价」与「累计净值」之差，就是溢价这件事到底花了多少钱。

另外三条辅助序列，回测同样离不开：
  backtest_data/510880.csv  红利 ETF → “溢价太高就改买境内”这条规则的去处
  backtest_data/QQQ.csv     纳指基准 ┐ 与累计净值比，才知道基金的跟踪质量
  backtest_data/SPY.csv     标普基准 ┘
  backtest_data/USDCNY.csv  汇率 → 把美元基准折成人民币口径

数据源：
  - 成交价：东财 push2his（fqt=2 后复权 / fqt=0 不复权），接口偶发断连，重试 + 退避
  - 净值：东财 pingzhongdata（一次给全历史，比 f10/lsjz 翻页快两个数量级）
  - 汇率：frankfurter（ECB 口径），东财外汇 K 线接口不开放

用法：
  python3 friends/tools/fetch_qdii_quant_data.py
  python3 friends/tools/fetch_qdii_quant_data.py --force            # 忽略缓存重抓
  python3 friends/tools/fetch_qdii_quant_data.py --stale-days 4     # 只补过期的（cron 用）
  python3 friends/tools/fetch_qdii_quant_data.py --only 513100,159941
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
DATA_DIR = TOOLS_DIR / "backtest_data"
RAW_DIR = DATA_DIR / "raw_price"
NAV_DIR = DATA_DIR / "nav"
ACC_DIR = DATA_DIR / "nav_acc"
WATCHLIST = TOOLS_DIR / "qdii_watchlist.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# 东财净值时间戳是北京时间 00:00 的毫秒数
CST = timezone(timedelta(hours=8))

# 辅助序列：key(落盘名) -> (secid, 用途)。105=NASDAQ，107=NYSE Arca
AUX_SYMBOLS: dict[str, tuple[str, str]] = {
    "510880": ("1.510880", "红利ETF（高溢价时的境内替代）"),
    "QQQ": ("105.QQQ", "纳指100 美元基准"),
    "SPY": ("107.SPY", "标普500 美元基准"),
}
FX_START_YEAR = 2013  # 最老的场内纳指 QDII 从 2013 年开始有净值


def _get(url: str, referer: str, tries: int = 10) -> str:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": referer}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(20, 1.5 * 1.6**attempt))
    raise RuntimeError(f"请求失败（{tries} 次）：{last}")


def secid(code: str) -> str:
    return f"1.{code}" if code.startswith(("5", "6")) else f"0.{code}"


def fetch_price(sec: str, fqt: int) -> list[tuple[str, float]]:
    """fqt=2 后复权 / fqt=0 不复权，返回按日期升序的 [(date, close)]"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={sec}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&klt=101&fqt={fqt}&beg=0&end=20500101&lmt=1000000"
    )
    payload = json.loads(_get(url, "https://quote.eastmoney.com/"))
    klines = (payload.get("data") or {}).get("klines")
    if not klines:
        raise RuntimeError(f"空数据 rc={payload.get('rc')}")
    return [(ln.split(",")[0], float(ln.split(",")[2])) for ln in klines]


def fetch_fx() -> list[tuple[str, float]]:
    """美元兑人民币日度序列，按年分段抓，避免单次请求过大"""
    rows: dict[str, float] = {}
    this_year = datetime.now(CST).year
    for year in range(FX_START_YEAR, this_year + 1):
        url = (
            f"https://api.frankfurter.app/{year}-01-01..{year}-12-31?from=USD&to=CNY"
        )
        payload = json.loads(_get(url, "https://www.frankfurter.app/", tries=5))
        for day, quote in (payload.get("rates") or {}).items():
            if "CNY" in quote:
                rows[day] = float(quote["CNY"])
        time.sleep(0.3)
    if not rows:
        raise RuntimeError("汇率为空")
    return sorted(rows.items())


def fetch_navs(code: str) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """(单位净值, 累计净值)，均为按日期升序的 [(date, value)]"""
    txt = _get(
        f"https://fund.eastmoney.com/pingzhongdata/{code}.js?v={int(time.time())}",
        "https://fund.eastmoney.com/",
    )

    def ts_to_date(ms: float) -> str:
        return datetime.fromtimestamp(ms / 1000, CST).strftime("%Y-%m-%d")

    m = re.search(r"Data_netWorthTrend\s*=\s*(\[.*?\])\s*;", txt, re.S)
    if not m:
        raise RuntimeError("未找到 Data_netWorthTrend")
    nav = [
        (ts_to_date(p["x"]), float(p["y"]))
        for p in json.loads(m.group(1))
        if p.get("y") not in (None, "")
    ]

    acc: list[tuple[str, float]] = []
    m2 = re.search(r"Data_ACWorthTrend\s*=\s*(\[.*?\])\s*;", txt, re.S)
    if m2:
        acc = [
            (ts_to_date(row[0]), float(row[1]))
            for row in json.loads(m2.group(1))
            if row[1] not in (None, "")
        ]
    return nav, acc


def write_csv(path: Path, rows: list[tuple[str, float]], header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", header])
        w.writerows(rows)


def is_stale(path: Path, stale_days: int) -> bool:
    """文件里最后一天距今超过 stale_days 就该重抓。

    净值比行情晚一两天披露，周末又没有交易日，所以 cron 里给到 4 天比较合适。
    """
    if not path.exists():
        return True
    if stale_days <= 0:
        return False
    try:
        with path.open(encoding="utf-8") as fh:
            last = None
            for row in csv.DictReader(fh):
                last = row["date"]
    except Exception:  # noqa: BLE001
        return True
    if not last:
        return True
    delta = datetime.now(CST).date() - datetime.strptime(last, "%Y-%m-%d").date()
    return delta.days > stale_days


def load_codes() -> list[tuple[str, str]]:
    cfg = json.loads(WATCHLIST.read_text(encoding="utf-8"))
    return [(str(it["code"]), it.get("name") or "") for it in cfg["items"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略缓存重抓")
    ap.add_argument("--stale-days", type=int, default=0,
                    help="缓存里最后一天距今超过 N 天才重抓（0=只补缺失的）")
    ap.add_argument("--only", default="", help="只抓这些代码，逗号分隔")
    args = ap.parse_args()

    codes = load_codes()
    if args.only:
        keep = {c.strip() for c in args.only.split(",") if c.strip()}
        codes = [(c, n) for c, n in codes if c in keep]

    failed: list[str] = []
    for code, name in codes:
        targets = [
            (DATA_DIR / f"{code}.csv", "close", lambda s=secid(code): fetch_price(s, 2)),
            (RAW_DIR / f"{code}.csv", "close", lambda s=secid(code): fetch_price(s, 0)),
        ]
        stale = args.stale_days
        todo = [
            (p, h, fn) for p, h, fn in targets
            if args.force or is_stale(p, stale)
        ]
        need_nav = args.force or is_stale(NAV_DIR / f"{code}.csv", stale) \
            or is_stale(ACC_DIR / f"{code}.csv", stale)

        if not todo and not need_nav:
            print(f"skip  {code} {name}", flush=True)
            continue

        parts: list[str] = []
        for path, header, fn in todo:
            try:
                rows = fn()
                write_csv(path, rows, header)
                tag = "后复权" if path.parent == DATA_DIR else "不复权"
                parts.append(f"{tag} {len(rows)}天 {rows[0][0]}→{rows[-1][0]}")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"{path.parent.name} FAIL({exc})")
                failed.append(f"{code}/{path.parent.name}")
            time.sleep(0.8)

        if need_nav:
            try:
                nav, acc = fetch_navs(code)
                write_csv(NAV_DIR / f"{code}.csv", nav, "nav")
                parts.append(f"单位净值 {len(nav)}天 {nav[0][0]}→{nav[-1][0]}")
                if acc:
                    write_csv(ACC_DIR / f"{code}.csv", acc, "acc")
                    parts.append(f"累计净值 {len(acc)}天")
                else:
                    parts.append("累计净值 缺失")
            except Exception as exc:  # noqa: BLE001
                parts.append(f"nav FAIL({exc})")
                failed.append(f"{code}/nav")
            time.sleep(0.5)

        print(f"ok    {code} {name}: " + " | ".join(parts), flush=True)

    # 辅助序列（--only 是用来补单只 QDII 的，这时不动它们）
    if not args.only:
        for key, (sec, label) in AUX_SYMBOLS.items():
            path = DATA_DIR / f"{key}.csv"
            if not (args.force or is_stale(path, args.stale_days)):
                print(f"skip  {key} {label}", flush=True)
                continue
            try:
                rows = fetch_price(sec, 2)
                write_csv(path, rows, "close")
                print(f"ok    {key} {label}: {len(rows)}天 {rows[0][0]}→{rows[-1][0]}",
                      flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  {key} {label}: {exc}", flush=True)
                failed.append(key)
            time.sleep(0.8)

        fx_path = DATA_DIR / "USDCNY.csv"
        if not (args.force or is_stale(fx_path, args.stale_days)):
            print("skip  USDCNY 美元兑人民币", flush=True)
        else:
            try:
                fx = fetch_fx()
                write_csv(fx_path, fx, "close")
                print(f"ok    USDCNY 美元兑人民币: {len(fx)}天 {fx[0][0]}→{fx[-1][0]}",
                      flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  USDCNY 美元兑人民币: {exc}", flush=True)
                failed.append("USDCNY")

    if failed:
        print(f"\n未成功：{', '.join(failed)}")
        return 1
    print("\n全部就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
