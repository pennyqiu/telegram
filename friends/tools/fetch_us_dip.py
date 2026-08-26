#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股纳指/标普 ETF · 回撤阶梯买入监控

做什么：
  1. 取每只 ETF 的现价 + 历史最高收盘（ATH），算「距最高点回撤%」
  2. 按分组的阶梯规则（如纳指跌8%买30%、15%买40%、20%买30%）给出：
     - 已触发哪几档、累计应投入百分比
     - 距下一档还要再跌多少、对应目标价
  3. 用状态文件区分「本轮首次触发某一档」与「仍停在同一档」，只为前者提醒
  4. 读待投资金台账，算等待天数与现金拖累成本（README 5.5：等待确定亏钱）
  5. 写入 friends/us-dip-signal.json（供 us-dip.html 读取）
  6. 可选：--email 按 qdii_email.env / qdii_email_recipients.txt 发提醒

数据源：优先 yfinance（VPS 已装）；不可用时回退东方财富（stdlib）。

配置与状态：
  us_dip_watchlist.json    监控列表 + 阶梯阈值（git 可改）
  us_dip_cash.json         待投资金台账（含金额，不入库；见 .example）
  .us_dip_state.json       本轮已提醒档位（cron 自动维护，不入库）

用法：
  python3 friends/tools/fetch_us_dip.py
  python3 friends/tools/fetch_us_dip.py --email
  python3 friends/tools/fetch_us_dip.py --email-force

每日 cron（服务器 UTC；北京 09:30 = UTC 01:30，周二~周六）：
  30 1 * * 2-6 TZ=Asia/Shanghai /app/telegram/friends/tools/daily_us_dip_cron.sh >> /var/log/us-dip.log 2>&1

邮件投递（见 qdii_email_recipients.txt）：
  all  → 每次定时任务都发；含待投资金台账（自己的账目，不外发）
  us   → 仅「本轮新触发某一档」时发，不含台账

为什么按「新触发」而不是「有仓位」发信：回撤动辄持续数月，按 cum_buy_pct>0
判定会让同一句「累计应买 30%」天天重复，真正跌到深档那天反而被忽略。
回测（backtest_dip_rolling.py）里阶梯本就有 re-arm 语义——创新高才重新武装，
线上补上状态机后两边才是同一套规则。
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape as _html_escape
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))
TOOLS_DIR = Path(__file__).resolve().parent
ENV_FILE = TOOLS_DIR / "qdii_email.env"
RECIPIENTS_FILE = TOOLS_DIR / "qdii_email_recipients.txt"
WATCHLIST_FILE = TOOLS_DIR / "us_dip_watchlist.json"
CASH_FILE = TOOLS_DIR / "us_dip_cash.json"
STATE_FILE = TOOLS_DIR / ".us_dip_state.json"

# 台账没写 assumptions 时的兜底。股票年化取长期名义回报的保守值，现金取货基。
DEFAULT_EQUITY_ANNUAL_PCT = 9.0
DEFAULT_CASH_ANNUAL_PCT = 1.5
DEFAULT_MAX_WAIT_TRADING_DAYS = 10

# 行情停更多少个工作日算「过期」。正常滞后 1~2 个（cron 用前一晚美股收盘），
# 留到 5 个是给假日长周末的余量。SPLG 改名 SPYM 后停更了 10 个月都没被发现，
# 因为过期价格配过期 ATH 算出来的回撤看着很正常——所以必须盯「数据有多旧」。
STALE_AFTER_WEEKDAYS = 5

EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
def load_watchlist(path: Path = WATCHLIST_FILE) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"缺少监控列表配置：{path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not cfg.get("items"):
        raise ValueError(f"监控列表为空：{path}")
    groups_order = list(cfg.get("groups_order") or [])
    for it in cfg["items"]:
        g = it.get("group") or "其他"
        if g not in groups_order:
            groups_order.append(g)
    cfg["groups_order"] = groups_order
    cfg.setdefault("groups", {})
    for g in groups_order:
        cfg["groups"].setdefault(g, {"ladder": []})
        cfg["groups"][g].setdefault("ladder", [])
        cfg["groups"][g]["ladder"] = sorted(
            cfg["groups"][g]["ladder"], key=lambda r: r["drop"]
        )
    return cfg


# ---------------------------------------------------------------------------
# 数据源：yfinance 主
# ---------------------------------------------------------------------------
def fetch_via_yfinance(symbols: list[str]) -> dict[str, dict[str, Any]]:
    import yfinance as yf  # 延迟导入：本地无此依赖时可回退东财

    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period="max", auto_adjust=False)
            if hist is None or hist.empty:
                continue
            closes = hist["Close"].dropna()
            highs = hist["High"].dropna()
            if closes.empty or highs.empty:
                continue
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else price
            change_pct = (price - prev) / prev * 100 if prev else 0.0
            ath = float(highs.max())
            ath_dt = highs.idxmax()
            ath_date = ath_dt.strftime("%Y-%m-%d") if hasattr(ath_dt, "strftime") else str(ath_dt)
            last_dt = closes.index[-1]
            out[sym] = {
                "price": price,
                "change_pct": change_pct,
                "ath": ath,
                "ath_date": ath_date,
                "last_date": last_dt.strftime("%Y-%m-%d") if hasattr(last_dt, "strftime") else str(last_dt)[:10],
                "n": int(len(closes)),
            }
        except Exception as e:  # noqa: BLE001
            out[sym] = {"error": f"yfinance: {e}"}
    return out


# ---------------------------------------------------------------------------
# 数据源：东方财富 兜底（stdlib）
# ---------------------------------------------------------------------------
def _em_get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=EM_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_via_eastmoney(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        sym = it["symbol"]
        secid = it.get("secid")
        if not secid:
            out[sym] = {"error": "缺少 secid，无法用东财兜底"}
            continue
        try:
            kurl = (
                "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=" + secid +
                "&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=0&beg=0&end=20500101&lmt=100000"
            )
            kd = _em_get(kurl)["data"]
            klines = kd.get("klines") or []
            ath = 0.0
            ath_date = None
            last_close = None
            prev_close = None
            for row in klines:
                p = row.split(",")
                high = float(p[3])
                close = float(p[2])
                if high > ath:
                    ath = high
                    ath_date = p[0]
                prev_close = last_close
                last_close = (p[0], close)
            price = last_close[1] if last_close else None
            change_pct = (
                (price - prev_close[1]) / prev_close[1] * 100
                if (price is not None and prev_close) else 0.0
            )
            out[sym] = {
                "price": price,
                "change_pct": change_pct,
                "ath": ath,
                "ath_date": ath_date,
                "last_date": last_close[0] if last_close else None,
                "n": len(klines),
            }
        except Exception as e:  # noqa: BLE001
            out[sym] = {"error": f"eastmoney: {e}"}
    return out


def fetch_quotes(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = cfg["items"]
    symbols = [it["symbol"] for it in items]
    data: dict[str, dict[str, Any]] = {}
    try:
        data = fetch_via_yfinance(symbols)
    except Exception as e:  # noqa: BLE001  (yfinance 未安装/导入失败)
        print(f"[info] yfinance 不可用，改用东方财富兜底：{e}", file=sys.stderr)

    missing = [it for it in items if it["symbol"] not in data or data[it["symbol"]].get("error")]
    if missing:
        em = fetch_via_eastmoney(missing)
        for sym, v in em.items():
            if not v.get("error") or sym not in data:
                data[sym] = v
    return data


# ---------------------------------------------------------------------------
# 阶梯信号
# ---------------------------------------------------------------------------
def _ladder_status(drawdown: float, ladder: list[dict[str, Any]], ath: float) -> dict[str, Any]:
    """drawdown 为正数（跌幅%）。返回已触发档、累计买入%、下一档、各档目标价。"""
    rungs = []
    cum = 0
    triggered = 0
    for r in ladder:
        hit = drawdown >= r["drop"] - 1e-9
        if hit:
            cum += r["buy"]
            triggered += 1
        rungs.append({
            "drop": r["drop"],
            "buy": r["buy"],
            "target_price": round(ath * (1 - r["drop"] / 100.0), 2) if ath else None,
            "hit": hit,
        })
    nxt = None
    for r in ladder:
        if drawdown < r["drop"] - 1e-9:
            nxt = {
                "drop": r["drop"],
                "buy": r["buy"],
                "gap_pct": round(r["drop"] - drawdown, 2),
                "target_price": round(ath * (1 - r["drop"] / 100.0), 2) if ath else None,
            }
            break
    if triggered == 0:
        signal = "观望"
    elif cum >= 100:
        signal = "已到底档"
    else:
        signal = "分批买入"
    return {
        "rungs": rungs,
        "cum_buy_pct": cum,
        "triggered": triggered,
        "next": nxt,
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# 触发状态：一轮回撤 = 从上一次创新高算起，同一档只提醒一次
# ---------------------------------------------------------------------------
def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    """状态文件损坏时退化为空状态：宁可多发一次，不可因此中断当日信号。"""
    if not path.exists():
        return {"version": 1, "symbols": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # noqa: BLE001
        print(f"[warn] 状态文件不可读，按空状态处理：{e}", file=sys.stderr)
        return {"version": 1, "symbols": {}}
    if not isinstance(state, dict):
        return {"version": 1, "symbols": {}}
    state.setdefault("version", 1)
    state.setdefault("symbols", {})
    return state


def save_state(state: dict[str, Any], path: Path = STATE_FILE) -> None:
    state["updated_at"] = datetime.now(CST).isoformat(timespec="seconds")
    try:
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as e:  # noqa: BLE001  写不进去不该影响已发出的邮件
        print(f"[warn] 状态文件写入失败：{e}", file=sys.stderr)


def apply_ladder_state(rows: list[dict[str, Any]], state: dict[str, Any], today: str) -> None:
    """
    给每行补上「本轮」视角的字段，但**不**把新档位记为已提醒——那要等邮件真的发出去，
    否则一次 SMTP 故障就会让这档永久沉默。

    本轮的定义：创新高即重新武装（与 backtest_us_dip.py 的 armed 语义一致）。
    回测里另有「水下满 N 个月补装一档」，线上暂不实现，见 README 待办。
    """
    symbols = state.setdefault("symbols", {})
    for r in rows:
        if r.get("error"):
            continue
        st = symbols.setdefault(r["symbol"], {})
        ath = r["ath"]
        prev_ath = st.get("cycle_ath")

        new_cycle = prev_ath is None or ath > prev_ath + 1e-9
        if new_cycle:
            st["cycle_ath"] = ath
            st["cycle_started"] = today
            st["max_drawdown_pct"] = 0.0
            st["notified"] = {}

        notified: dict[str, Any] = st.setdefault("notified", {})
        st["max_drawdown_pct"] = round(
            max(st.get("max_drawdown_pct") or 0.0, r["drawdown_pct"]), 2
        )

        hit_drops = [g["drop"] for g in r["rungs"] if g["hit"]]
        new_drops = [d for d in hit_drops if str(d) not in notified]

        # 本轮已提醒过、且比新触发档更浅的那一档，用来在邮件里写「上一档何时触发」
        prev_rung = None
        if new_drops:
            shallower = [
                (float(k), v) for k, v in notified.items() if float(k) < min(new_drops)
            ]
            if shallower:
                drop, ev = max(shallower, key=lambda kv: kv[0])
                prev_rung = {"drop": drop, **ev}

        r["cycle_ath"] = st["cycle_ath"]
        r["cycle_started"] = st.get("cycle_started")
        r["cycle_max_drawdown_pct"] = st["max_drawdown_pct"]
        r["cycle_is_new"] = new_cycle
        r["new_rungs"] = new_drops
        r["notified_rungs"] = sorted(float(k) for k in notified)
        r["prev_rung"] = prev_rung


def commit_ladder_state(rows: list[dict[str, Any]], state: dict[str, Any], today: str) -> None:
    """邮件确认发出后才把新档位落盘为「已提醒」。"""
    symbols = state.setdefault("symbols", {})
    for r in rows:
        if r.get("error") or not r.get("new_rungs"):
            continue
        notified = symbols.setdefault(r["symbol"], {}).setdefault("notified", {})
        for drop in r["new_rungs"]:
            notified[str(drop)] = {
                "date": today,
                "price": r["price"],
                "drawdown_pct": r["drawdown_pct"],
            }


# ---------------------------------------------------------------------------
# 待投资金：README 5.2/5.5 —— 阶梯跑赢立投的概率只有 3.7%，等待本身才是确定的成本
# ---------------------------------------------------------------------------
def load_cash_ledger(path: Path = CASH_FILE) -> dict[str, Any] | None:
    """台账不存在即视为未启用该功能（不报错，邮件里也不出现相关段落）。"""
    if not path.exists():
        return None
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # noqa: BLE001
        print(f"[warn] 待投资金台账不可读，本次跳过：{e}", file=sys.stderr)
        return None
    return ledger if isinstance(ledger, dict) else None


def _weekdays_between(d0: date, d1: date) -> int:
    """(d0, d1] 之间的工作日数。不含美股假日，宁可少算也不引入日历依赖。"""
    if d1 <= d0:
        return 0
    days = (d1 - d0).days
    full_weeks, rem = divmod(days, 7)
    n = full_weeks * 5
    wd = d0.weekday()
    for i in range(1, rem + 1):
        if (wd + i) % 7 < 5:
            n += 1
    return n


def compute_cash_status(ledger: dict[str, Any] | None, today: date) -> dict[str, Any] | None:
    a = (ledger or {}).get("assumptions") or {}
    if ledger is None:
        return None
    equity = float(a.get("equity_annual_pct", DEFAULT_EQUITY_ANNUAL_PCT))
    cash_rate = float(a.get("cash_annual_pct", DEFAULT_CASH_ANNUAL_PCT))
    limit = int(a.get("max_wait_trading_days", DEFAULT_MAX_WAIT_TRADING_DAYS))
    spread = equity - cash_rate

    pending: list[dict[str, Any]] = []
    for e in ledger.get("entries") or []:
        if e.get("invested_on"):
            continue
        try:
            arrived = date.fromisoformat(str(e["date"]))
            amount = float(e["amount"])
        except (KeyError, TypeError, ValueError):
            print(f"[warn] 台账条目格式不对，已跳过：{e}", file=sys.stderr)
            continue
        cal_days = (today - arrived).days
        if cal_days < 0:  # 预登记的未来入账
            continue
        trading_days = _weekdays_between(arrived, today)
        pending.append({
            "date": e["date"],
            "amount": amount,
            "note": e.get("note") or "",
            "calendar_days": cal_days,
            "trading_days": trading_days,
            # 拖累按自然日算：钱在周末同样没在市场里
            "drag_cost": round(amount * spread / 100.0 * cal_days / 365.0, 2),
            "over_limit": trading_days > limit,
        })

    pending.sort(key=lambda p: p["calendar_days"], reverse=True)
    return {
        "enabled": True,
        "currency": ledger.get("currency") or "CNY",
        "assumptions": {
            "equity_annual_pct": equity,
            "cash_annual_pct": cash_rate,
            "max_wait_trading_days": limit,
        },
        "pending_count": len(pending),
        "pending_total": round(sum(p["amount"] for p in pending), 2),
        "drag_cost_total": round(sum(p["drag_cost"] for p in pending), 2),
        "max_trading_days": max((p["trading_days"] for p in pending), default=0),
        "over_limit_count": sum(1 for p in pending if p["over_limit"]),
        "entries": pending,
    }


def build_payload(
    cfg: dict[str, Any],
    quotes: dict[str, dict[str, Any]],
    state: dict[str, Any] | None = None,
    cash: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(CST)
    groups_order = cfg["groups_order"]
    group_rank = {g: i for i, g in enumerate(groups_order)}
    rows: list[dict[str, Any]] = []

    for it in cfg["items"]:
        sym = it["symbol"]
        g = it.get("group") or "其他"
        q = quotes.get(sym) or {}
        if q.get("error") or q.get("price") is None or not q.get("ath"):
            rows.append({
                "symbol": sym, "name": it.get("name") or sym, "group": g,
                "error": q.get("error") or "无行情", "signal": "未知",
            })
            continue

        # 停更的行情必须挡在信号之前：过期价格配过期 ATH，回撤算出来毫无异常之处。
        last_date = q.get("last_date")
        stale_weekdays = 0
        if last_date:
            try:
                stale_weekdays = _weekdays_between(date.fromisoformat(str(last_date)[:10]), now.date())
            except ValueError:
                last_date = None
        if stale_weekdays > STALE_AFTER_WEEKDAYS:
            rows.append({
                "symbol": sym, "name": it.get("name") or sym, "group": g,
                "error": f"行情停更：最后交易日 {last_date}，已 {stale_weekdays} 个工作日没有新数据"
                         f"（代码是否已改名或退市？）",
                "signal": "未知", "stale": True,
                "last_date": last_date, "stale_weekdays": stale_weekdays,
                "price": round(float(q["price"]), 2),
            })
            continue

        price = float(q["price"])
        ath = float(q["ath"])
        drawdown = (ath - price) / ath * 100.0 if ath else 0.0
        ladder = cfg["groups"].get(g, {}).get("ladder", [])
        st = _ladder_status(drawdown, ladder, ath)
        rows.append({
            "symbol": sym,
            "name": it.get("name") or sym,
            "group": g,
            "price": round(price, 2),
            "change_pct": round(q.get("change_pct") or 0.0, 2),
            "ath": round(ath, 2),
            "ath_date": q.get("ath_date"),
            "last_date": last_date,
            "drawdown_pct": round(drawdown, 2),
            "cum_buy_pct": st["cum_buy_pct"],
            "next": st["next"],
            "rungs": st["rungs"],
            "signal": st["signal"],
            "yahoo_url": f"https://finance.yahoo.com/quote/{sym}",
        })

    def sort_key(r: dict[str, Any]):
        return (group_rank.get(r["group"], 99), -(r.get("drawdown_pct") or -999))

    rows.sort(key=sort_key)

    if state is not None:
        apply_ladder_state(rows, state, now.strftime("%Y-%m-%d"))

    return {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_text": now.strftime("%Y-%m-%d %H:%M:%S") + " CST",
        "title": cfg.get("title") or "美股回撤阶梯买入监控",
        "field_note": cfg.get("field_note") or "",
        "groups_order": groups_order,
        "ladders": {
            g: {
                "benchmark": cfg["groups"].get(g, {}).get("benchmark"),
                "note": cfg["groups"].get(g, {}).get("note"),
                "ladder": cfg["groups"].get(g, {}).get("ladder", []),
            }
            for g in groups_order
        },
        "counts": {g: sum(1 for r in rows if r.get("group") == g) for g in groups_order},
        "cash": cash,
        "items": rows,
    }


# ---------------------------------------------------------------------------
# 邮件（复用 qdii_email.env 与收件人列表）
# ---------------------------------------------------------------------------
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


_KIND_ALIASES = {
    "qdii": "qdii", "a": "qdii", "cn": "qdii", "国内": "qdii",
    "us": "us", "b": "us", "美股": "us", "qqq": "us", "spy": "us",
    "all": "all", "both": "all", "*": "all", "": "all",
}


def _parse_recipient_line(line: str) -> tuple[str, set[str]] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    email = parts[0].strip()
    if "@" not in email:
        return None
    raw_tags = " ".join(parts[1:]).replace(";", ",").replace("，", ",")
    tags = {_KIND_ALIASES.get(t.strip().lower(), t.strip().lower())
            for t in raw_tags.split(",") if t.strip()}
    if not tags:
        tags = {"all"}
    return email, tags


def load_recipients_split(
    path: Path = RECIPIENTS_FILE, kind: str = "us"
) -> tuple[list[str], list[str]]:
    """
    按投递策略拆分收件人。kind='us'|'qdii'。
    返回 (always, alert_only)：
      - always: 标签含 all → 每次定时任务都发（心跳日报；失败也通知）
      - alert_only: 标签含 kind 且不含 all → 仅机会触发时发
    """
    always: list[str] = []
    alert: list[str] = []
    seen_a: set[str] = set()
    seen_b: set[str] = set()
    if not path.exists():
        return always, alert
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_recipient_line(line)
        if not parsed:
            continue
        email, tags = parsed
        key = email.lower()
        if "all" in tags:
            if key not in seen_a:
                seen_a.add(key)
                always.append(email)
        elif kind in tags:
            if key not in seen_b:
                seen_b.add(key)
                alert.append(email)
    return always, alert


def load_recipients(path: Path = RECIPIENTS_FILE, kind: str | None = None) -> list[str]:
    """兼容旧接口：kind 下 always + alert_only 合并去重。"""
    if kind is None:
        always, alert = load_recipients_split(path, "us")
        always2, alert2 = load_recipients_split(path, "qdii")
        out, seen = [], set()
        for e in always + alert + always2 + alert2:
            if e.lower() not in seen:
                seen.add(e.lower())
                out.append(e)
        return out
    always, alert = load_recipients_split(path, kind)
    return always + [e for e in alert if e.lower() not in {x.lower() for x in always}]


def _email_config() -> dict[str, Any]:
    _load_env_file(ENV_FILE)
    always, alert = load_recipients_split(kind="us")
    if not always and not alert:
        fallback = [x.strip() for x in os.getenv("EMAIL_RECIPIENTS", "").split(",") if x.strip()]
        always = fallback  # 环境变量备用视为心跳收件人
    return {
        "enabled": _bool_env("EMAIL_ENABLED", False),
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "use_tls": _bool_env("SMTP_USE_TLS", True),
        "username": os.getenv("SMTP_USERNAME", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": os.getenv("EMAIL_SENDER") or os.getenv("SMTP_USERNAME", ""),
        "always": always,
        "alert": alert,
        "monitor_url": os.getenv("US_DIP_URL", "https://learn.tgfootclub.com/friends/us-dip.html"),
    }


def _has_buy(payload: dict[str, Any]) -> bool:
    return any(r.get("cum_buy_pct", 0) > 0 for r in payload.get("items") or [])


def _has_new_trigger(payload: dict[str, Any]) -> bool:
    return any(r.get("new_rungs") for r in payload.get("items") or [])


def _trigger_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """展开成「每个新触发的档位一条」，深档在前。"""
    out: list[dict[str, Any]] = []
    for r in payload.get("items") or []:
        by_drop = {g["drop"]: g for g in r.get("rungs") or []}
        for drop in r.get("new_rungs") or []:
            out.append({
                "symbol": r["symbol"],
                "name": r.get("name") or "",
                "drop": drop,
                "buy": (by_drop.get(drop) or {}).get("buy"),
                "price": r.get("price"),
                "drawdown_pct": r.get("drawdown_pct"),
                "cum_buy_pct": r.get("cum_buy_pct"),
                "prev_rung": r.get("prev_rung"),
            })
    out.sort(key=lambda e: (-e["drop"], e["symbol"]))
    return out


def _fmt_amount(v: float) -> str:
    return f"{v:,.0f}" if abs(v - round(v)) < 0.005 else f"{v:,.2f}"


def _cash_lines(cash: dict[str, Any]) -> list[str]:
    """待投资金段落。没有待投资金时也给一行，确认这条纪律today是过了的。"""
    cur = cash.get("currency") or "CNY"
    a = cash["assumptions"]
    limit = a["max_wait_trading_days"]
    if not cash["pending_count"]:
        return ["【待投资金】无。新钱都已投出，本条纪律今日通过。", ""]

    total = _fmt_amount(cash["pending_total"])
    lines = [
        f"【待投资金】{total} {cur} 待投，最长已等 {cash['max_trading_days']} 个交易日"
        f"（规则上限 {limit} 个）",
        f"　按股票年化 {a['equity_annual_pct']}%、现金 {a['cash_annual_pct']}% 估算，"
        f"至今等待成本约 {_fmt_amount(cash['drag_cost_total'])} {cur}",
    ]
    for e in cash["entries"]:
        flag = "⚠ 已超期 " if e["over_limit"] else ""
        note = f"（{e['note']}）" if e["note"] else ""
        lines.append(
            f"　- {flag}{_fmt_amount(e['amount'])} {cur} 于 {e['date']} 到账{note}，"
            f"已等 {e['trading_days']} 个交易日 / {e['calendar_days']} 天，"
            f"拖累约 {_fmt_amount(e['drag_cost'])} {cur}"
        )
    if cash["over_limit_count"]:
        lines.append(
            "　动作：立即投出。回撤阶梯只决定「今天多投还是少投」，不决定「投不投」——"
            "SPY 187 个 10 年滚动窗口里，纯阶梯跑赢全额立投的概率是 3.7%。"
        )
    lines.append("")
    return lines


def render_email(
    payload: dict[str, Any], cfg: dict[str, Any], include_cash: bool = True
) -> tuple[str, str, str]:
    items = [r for r in (payload.get("items") or []) if not r.get("error")]
    # 取不到数的标的以前会从邮件里直接消失，看不见就等于没发生——必须显式列出来
    problems = [r for r in (payload.get("items") or []) if r.get("error")]
    groups_order = payload.get("groups_order") or []
    title = payload.get("title") or "美股回撤阶梯买入监控"
    events = _trigger_events(payload)
    cash = payload.get("cash") if include_cash else None

    if events:
        tag = "【新触发档位】"
    elif problems:
        tag = "【数据异常】"
    elif cash and cash.get("over_limit_count"):
        tag = "【资金待投超期】"
    else:
        tag = "【日报】"
    subject = f"{tag}{title} · {payload.get('updated_at_text', '')}"

    lines = [f"更新时间：{payload.get('updated_at_text')}", ""]
    if problems:
        lines.append(f"⚠ 数据异常（以下 {len(problems)} 只本封不可用，未参与任何信号判定）")
        for r in problems:
            lines.append(f"　- {r['symbol']} {r.get('name','')}：{r['error']}")
        lines.append("")
    if cash:
        lines += _cash_lines(cash)
    if events:
        lines.append("★ 本轮新触发档位")
        for e in events:
            lines.append(
                f"{e['symbol']} {e['name']} 跌破 -{e['drop']}%（本轮首次）"
                f"　现价{e['price']} 距高点{e['drawdown_pct']}% "
                f"本档应买{e['buy']}% 本轮累计{e['cum_buy_pct']}%"
            )
            p = e.get("prev_rung")
            if p:
                lines.append(
                    f"　上一档 -{p['drop']:g}% 触发于 {p['date']}，当时价 {p['price']}"
                )
        lines.append("")

    for g in groups_order:
        gitems = [r for r in items if r.get("group") == g]
        if not gitems:
            continue
        lines.append(f"—— {g} ——")
        for r in gitems:
            nxt = r.get("next")
            nxt_txt = (f"，距下一档 -{nxt['drop']}% 还需跌 {nxt['gap_pct']}%" if nxt else "，已到底档")
            lines.append(
                f"{r['symbol']} {r.get('name','')} 现价{r['price']} "
                f"距高点{r['drawdown_pct']}% 累计应买{r['cum_buy_pct']}% [{r['signal']}]{nxt_txt}"
            )
        lines.append("")
    plain = "\n".join(lines)

    def row_html(r: dict[str, Any]) -> str:
        dd = r.get("drawdown_pct")
        color = "#057a55" if (r.get("cum_buy_pct") or 0) > 0 else "#6b7280"
        nxt = r.get("next")
        nxt_txt = (f"-{nxt['drop']}% (再跌{nxt['gap_pct']}%→{nxt['target_price']})" if nxt else "已到底档")
        badge = (
            "<span style='background:#fef3c7;color:#92400e;padding:1px 5px;"
            "border-radius:3px;font-size:11px;margin-left:4px'>新</span>"
            if r.get("new_rungs") else ""
        )
        return (
            f"<tr>"
            f"<td>{r.get('group')}</td><td><b>{r.get('symbol')}</b>{badge}</td>"
            f"<td>{r.get('name')}</td><td>{r.get('price')}</td>"
            f"<td>{r.get('ath')}<br><span style='color:#9ca3af;font-size:11px'>{r.get('ath_date')}</span></td>"
            f"<td style='color:#b91c1c;font-weight:700'>-{dd}%</td>"
            f"<td style='color:{color};font-weight:700'>{r.get('cum_buy_pct')}%</td>"
            f"<td>{r.get('signal')}</td><td>{nxt_txt}</td>"
            f"</tr>"
        )

    ladder_html = ""
    for g in groups_order:
        lad = (payload.get("ladders") or {}).get(g, {})
        rungs = " · ".join(f"跌{r['drop']}%买{r['buy']}%" for r in lad.get("ladder", []))
        ladder_html += f"<li><b>{g}</b>（{lad.get('benchmark','')}）：{rungs}</li>"

    cash_html = ""
    if cash:
        cur = _html_escape(cash.get("currency") or "CNY")
        a = cash["assumptions"]
        if not cash["pending_count"]:
            cash_html = (
                "<p style='background:#f0fdf4;border-left:4px solid #16a34a;padding:10px;"
                "margin:12px 0'>待投资金：无。新钱都已投出，本条纪律今日通过。</p>"
            )
        else:
            over = cash["over_limit_count"] > 0
            bg, bar = ("#fef2f2", "#dc2626") if over else ("#f8fafc", "#64748b")
            rows_html = "".join(
                "<li>{flag}{amt} {cur} 于 {d} 到账{note}，已等 <b>{td}</b> 个交易日 / "
                "{cd} 天，拖累约 {drag} {cur}</li>".format(
                    flag="⚠ 已超期 " if e["over_limit"] else "",
                    amt=_fmt_amount(e["amount"]), cur=cur, d=_html_escape(str(e["date"])),
                    note=f"（{_html_escape(e['note'])}）" if e["note"] else "",
                    td=e["trading_days"], cd=e["calendar_days"],
                    drag=_fmt_amount(e["drag_cost"]),
                )
                for e in cash["entries"]
            )
            action = (
                "<p style='margin:6px 0 0'><b>动作：立即投出。</b>回撤阶梯只决定"
                "「今天多投还是少投」，不决定「投不投」——SPY 187 个 10 年滚动窗口里，"
                "纯阶梯跑赢全额立投的概率是 3.7%。</p>" if over else ""
            )
            cash_html = (
                f"<div style='background:{bg};border-left:4px solid {bar};padding:10px 14px;"
                f"margin:12px 0'>"
                f"<b>待投资金 {_fmt_amount(cash['pending_total'])} {cur}</b>"
                f"，最长已等 {cash['max_trading_days']} 个交易日（规则上限 "
                f"{a['max_wait_trading_days']} 个）<br>"
                f"<span style='color:#6b7280;font-size:12px'>按股票年化 "
                f"{a['equity_annual_pct']}%、现金 {a['cash_annual_pct']}% 估算，至今等待成本约 "
                f"{_fmt_amount(cash['drag_cost_total'])} {cur}</span>"
                f"<ul style='margin:8px 0 0;font-size:13px'>{rows_html}</ul>{action}</div>"
            )

    events_html = ""
    if events:
        li = "".join(
            "<li><b>{sym}</b> {name} 跌破 <b>-{drop}%</b>（本轮首次）：现价 {price}，"
            "距高点 {dd}%，本档应买 {buy}%，本轮累计 {cum}%{prev}</li>".format(
                sym=_html_escape(e["symbol"]), name=_html_escape(e["name"]),
                drop=e["drop"], price=e["price"], dd=e["drawdown_pct"],
                buy=e["buy"], cum=e["cum_buy_pct"],
                prev=(
                    f"　<span style='color:#6b7280;font-size:12px'>上一档 "
                    f"-{e['prev_rung']['drop']:g}% 触发于 {e['prev_rung']['date']}，"
                    f"当时价 {e['prev_rung']['price']}</span>"
                ) if e.get("prev_rung") else "",
            )
            for e in events
        )
        events_html = (
            "<div style='background:#fffbeb;border-left:4px solid #d97706;padding:10px 14px;"
            f"margin:12px 0'><b>本轮新触发档位</b><ul style='margin:8px 0 0'>{li}</ul></div>"
        )

    problems_html = ""
    if problems:
        li = "".join(
            f"<li><b>{_html_escape(r['symbol'])}</b> {_html_escape(r.get('name') or '')}："
            f"{_html_escape(str(r['error']))}</li>"
            for r in problems
        )
        problems_html = (
            "<div style='background:#fef2f2;border-left:4px solid #dc2626;padding:10px 14px;"
            f"margin:12px 0'><b>数据异常</b>：以下 {len(problems)} 只本封不可用，"
            f"未参与任何信号判定<ul style='margin:8px 0 0'>{li}</ul></div>"
        )

    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;color:#111">
<h2 style="color:#1e429f">{title}</h2>
<p>更新：{payload.get('updated_at_text')}</p>
{problems_html}
{cash_html}
{events_html}
<h3>阶梯规则</h3>
<ul>{ladder_html}</ul>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<thead style="background:#eff6ff"><tr>
<th>分组</th><th>代码</th><th>名称</th><th>现价</th><th>历史最高</th>
<th>距高点</th><th>累计应买</th><th>信号</th><th>下一档</th>
</tr></thead>
<tbody>
{''.join(row_html(r) for r in items)}
</tbody></table>
<p style="color:#6b7280;font-size:12px">回撤=(现价−历史最高收盘)/历史最高收盘。仓位为“计划投入资金”的百分比，逐档累计。
「距下一档」只用于挂限价单，不是等待的理由：该投的钱按期投出，阶梯只调节当天投多投少。非投资建议。</p>
</body></html>"""
    return subject, plain, html


def _smtp_send(cfg: dict[str, Any], subject: str, plain: str, html: str, recipients: list[str]) -> str:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        if cfg["use_tls"]:
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
                server.starttls(context=context)
                if cfg["username"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
                if cfg["username"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        return f"sent: → {', '.join(recipients)} | {subject}"
    except Exception as e:  # noqa: BLE001
        return f"error: 邮件发送失败：{e}"


def send_email(payload: dict[str, Any], force: bool = False) -> tuple[str, bool]:
    """
    投递规则（收件人标签优先，不再依赖 EMAIL_MODE）：
      - all（自己）→ 每次都发，含待投资金台账
      - us（朋友）→ 仅「本轮新触发某一档」或 --email-force 时发，不含台账

    两组分开发信，因为台账里是自己的金额，不该出现在转发给朋友的那封里。

    返回 (状态文本, 新触发档位是否已送达)。第二个值决定要不要把这些档位记为
    「已提醒」——发失败就不记，下次继续提醒。
    """
    cfg = _email_config()
    if not cfg["enabled"]:
        return "skip: EMAIL_ENABLED=false（配置 friends/tools/qdii_email.env 后开启）", False
    if not cfg["host"] or not cfg["sender"]:
        return "skip: SMTP 未配置完整", False
    if not cfg["always"] and not cfg["alert"]:
        return "skip: 收件人为空", False

    has_new = _has_new_trigger(payload)
    results: list[str] = []
    delivered = False

    if cfg["always"]:
        subject, plain, html = render_email(payload, cfg, include_cash=True)
        status = _smtp_send(cfg, subject, plain, html, cfg["always"])
        results.append(f"all[{len(cfg['always'])}] {status}")
        delivered = delivered or status.startswith("sent:")

    always_lower = {x.lower() for x in cfg["always"]}
    alert = [e for e in cfg["alert"] if e.lower() not in always_lower]
    if alert and (force or has_new):
        subject, plain, html = render_email(payload, cfg, include_cash=False)
        status = _smtp_send(cfg, subject, plain, html, alert)
        results.append(f"us[{len(alert)}] {status}")
        delivered = delivered or status.startswith("sent:")
    elif alert:
        results.append(f"us[{len(alert)}] skip: 本轮无新触发档位")

    return " | ".join(results), (delivered and has_new)


def send_failure_email(error: str) -> str:
    """流程失败时只通知 all（心跳）收件人，便于区分「挂了」还是「没触发」。"""
    cfg = _email_config()
    if not cfg["enabled"]:
        return "skip: EMAIL_ENABLED=false"
    if not cfg["host"] or not cfg["sender"] or not cfg["always"]:
        return "skip: SMTP/all 收件人未配置"
    title = "美股回撤阶梯买入监控"
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    subject = f"【失败】{title} · {now}"
    plain = (
        f"定时任务执行失败，请检查服务器日志 /var/log/us-dip.log\n\n"
        f"时间：{now}\n错误：{error}\n"
    )
    html = (
        f"<!DOCTYPE html><html><body style='font-family:sans-serif'>"
        f"<h2 style='color:#b91c1c'>【失败】{title}</h2>"
        f"<p>时间：{now}</p><pre style='background:#fef2f2;padding:12px'>{_html_escape(error)}</pre>"
        f"<p style='color:#6b7280;font-size:12px'>日志：/var/log/us-dip.log</p>"
        f"</body></html>"
    )
    return _smtp_send(cfg, subject, plain, html, cfg["always"])


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="美股纳指/标普 ETF 回撤阶梯买入监控")
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--out", type=Path, default=root / "us-dip-signal.json")
    ap.add_argument("--email", action="store_true", help="按 qdii_email.env 发送邮件")
    ap.add_argument("--email-force", action="store_true", help="强制发邮件（忽略 alert 过滤）")
    args = ap.parse_args()

    try:
        cfg = load_watchlist()
        quotes = fetch_quotes(cfg)
    except (FileNotFoundError, ValueError, KeyError, urllib.error.URLError, TimeoutError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if args.email or args.email_force:
            status = send_failure_email(str(e))
            print(f"email: {status}")
        return 1

    state = load_state()
    cash = compute_cash_status(load_cash_ledger(), datetime.now(CST).date())
    payload = build_payload(cfg, quotes, state=state, cash=cash)
    today = payload["updated_at"][:10]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {args.out}  ({payload['updated_at_text']})  n={len(payload['items'])}")
    if cash:
        print(
            f"cash: 待投 {cash['pending_count']} 笔 / {_fmt_amount(cash['pending_total'])} "
            f"{cash['currency']}，最长 {cash['max_trading_days']} 个交易日，"
            f"超期 {cash['over_limit_count']} 笔，拖累约 {_fmt_amount(cash['drag_cost_total'])}"
        )

    # 控制台摘要仅供人看；任何格式化异常都不得阻断邮件推送。
    try:
        print(f"{'代码':<6} {'分组':<8} {'现价':>9} {'历史最高':>9} {'距高点%':>8} {'累计买%':>7} {'信号'}")
        for r in payload["items"]:
            if r.get("error"):
                print(f"{r['symbol']:<6} {r.get('group',''):<8} ERROR {r['error']}")
                continue
            new_txt = (
                "  ← 本轮新触发 " + "/".join(f"-{d}%" for d in r["new_rungs"])
                if r.get("new_rungs") else ""
            )
            print(
                f"{r['symbol']:<6} {r['group']:<8} {r['price']:>9.2f} {r['ath']:>9.2f} "
                f"{r['drawdown_pct']:>7.2f}% {r['cum_buy_pct']:>6}% {r['signal']}{new_txt}"
            )
    except Exception as e:  # noqa: BLE001  控制台摘要失败不影响邮件推送
        print(f"[warn] 控制台摘要渲染失败（不影响邮件）：{e}", file=sys.stderr)

    rc = 0
    if args.email or args.email_force:
        status, delivered = send_email(payload, force=args.email_force)
        print(f"email: {status}")
        if delivered:
            commit_ladder_state(payload["items"], state, today)
        if "error:" in status:
            rc = 2

    # 无论发信与否都要落盘：创新高重置本轮、本轮最深回撤这些是纯观测，不该依赖邮件。
    save_state(state)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
