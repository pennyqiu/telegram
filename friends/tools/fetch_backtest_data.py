#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拉取回测所需的历史日线（东方财富，与 fetch_qdii_premium.py 同源），缓存为 CSV。

为「大陆 ETF 定投策略」历史回测提供数据：
  - 大陆场内 ETF：fqt=2 后复权收盘价（分红再投），真实成交价已含 QDII 溢价波动、
    汇率、跟踪误差与费率，比「指数年化」更贴近实盘
    ※ 必须用后复权：像 510880 这种高股息长历史标的，前复权会把早年价格
      减到负数（累计分红超过当年价格），完全不能用来算收益率
  - QQQ / SPY：美元前复权（含股息再投），用于补齐大陆 QDII 上市前的长历史
  - USDCNY：用于把美元收益折算成人民币

secid 前缀：1=上交所，0=深交所，105=NASDAQ，107=NYSE Arca，133=外汇

输出：friends/tools/backtest_data/<code>.csv  (date, close)

用法：
  python3 friends/tools/fetch_backtest_data.py
  python3 friends/tools/fetch_backtest_data.py --force   # 忽略缓存重新下载
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "backtest_data"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# key(落盘文件名) -> (secid, 中文说明)
SYMBOLS: dict[str, tuple[str, str]] = {
    # ---- 大陆场内 ETF（人民币，前复权真实成交价）----
    "510880": ("1.510880", "华泰柏瑞红利ETF（上证红利）"),
    "515080": ("1.515080", "招商中证红利ETF"),
    "512890": ("1.512890", "华泰柏瑞红利低波ETF"),
    "513100": ("1.513100", "国泰纳斯达克100ETF"),
    "159941": ("0.159941", "广发纳斯达克100ETF"),
    "513500": ("1.513500", "博时标普500ETF"),
    "159612": ("0.159612", "平安标普500ETF"),
    "513050": ("1.513050", "易方达中概互联50ETF"),
    "159915": ("0.159915", "易方达创业板ETF"),
    "510300": ("1.510300", "华泰柏瑞沪深300ETF"),
    "588000": ("1.588000", "华夏科创50ETF"),
    "159509": ("0.159509", "纳指科技ETF"),
    "513330": ("1.513330", "华夏恒生互联网ETF"),
    "512100": ("1.512100", "南方中证1000ETF"),
    # ---- 美元基准（前复权含股息）----
    "QQQ": ("105.QQQ", "Invesco QQQ（纳指100）"),
    "SPY": ("107.SPY", "SPDR S&P500（标普500）"),
}

# 汇率走 frankfurter（ECB 口径），东财外汇 K 线接口不开放
FX_START_YEAR = 2006


def fetch(secid: str, tries: int = 8) -> list[tuple[str, float]]:
    """返回 [(YYYY-MM-DD, 后复权收盘), ...]，按日期升序。接口偶发断连，故重试。"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        "&klt=101&fqt=2&beg=0&end=20500101&lmt=1000000"
    )
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            data = payload.get("data")
            if not data or not data.get("klines"):
                raise RuntimeError(f"接口返回空数据 rc={payload.get('rc')}")
            rows: list[tuple[str, float]] = []
            for line in data["klines"]:
                parts = line.split(",")
                # f51=日期 f52=开 f53=收 f54=高 f55=低
                rows.append((parts[0], float(parts[2])))
            return rows
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(30, 2 * 1.7**attempt))
    raise RuntimeError(f"下载失败（{tries} 次重试）：{last}")


def fetch_fx() -> list[tuple[str, float]]:
    """美元兑人民币日度序列，按年分段抓取以避免单次请求过大。"""
    rows: dict[str, float] = {}
    this_year = time.localtime().tm_year
    for year in range(FX_START_YEAR, this_year + 1):
        url = (
            f"https://api.frankfurter.app/{year}-01-01..{year}-12-31"
            "?from=USD&to=CNY"
        )
        last: Exception | None = None
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as resp:
                    payload = json.load(resp)
                for day, quote in payload.get("rates", {}).items():
                    if "CNY" in quote:
                        rows[day] = float(quote["CNY"])
                last = None
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2 * 1.6**attempt)
        if last is not None:
            raise RuntimeError(f"{year} 年汇率下载失败：{last}")
        time.sleep(0.4)
    return sorted(rows.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略已有缓存重新下载")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for key, (secid, label) in SYMBOLS.items():
        out = DATA_DIR / f"{key}.csv"
        if out.exists() and not args.force:
            print(f"skip  {key:8s} {label}  (已缓存)", flush=True)
            continue
        try:
            rows = fetch(secid)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {key:8s} {label}  {exc}", flush=True)
            failed.append(key)
            continue
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "close"])
            w.writerows(rows)
        print(
            f"ok    {key:8s} {label}  n={len(rows)}  {rows[0][0]} → {rows[-1][0]}",
            flush=True,
        )
        time.sleep(1.2)

    fx_out = DATA_DIR / "USDCNY.csv"
    if fx_out.exists() and not args.force:
        print("skip  USDCNY   美元兑人民币  (已缓存)", flush=True)
    else:
        try:
            fx = fetch_fx()
            with fx_out.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "close"])
                w.writerows(fx)
            print(
                f"ok    USDCNY   美元兑人民币  n={len(fx)}  {fx[0][0]} → {fx[-1][0]}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  USDCNY   美元兑人民币  {exc}", flush=True)
            failed.append("USDCNY")

    if failed:
        print(f"\n未成功：{', '.join(failed)}", flush=True)


if __name__ == "__main__":
    main()
