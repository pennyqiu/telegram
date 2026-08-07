#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股纳指/标普 ETF · 回撤阶梯买入监控

做什么：
  1. 取每只 ETF 的现价 + 历史最高收盘（ATH），算「距最高点回撤%」
  2. 按分组的阶梯规则（如纳指跌8%买30%、15%买40%、20%买30%）给出：
     - 已触发哪几档、累计应投入百分比
     - 距下一档还要再跌多少、对应目标价
  3. 写入 friends/us-dip-signal.json（供 us-dip.html 读取）
  4. 可选：--email 按 qdii_email.env / qdii_email_recipients.txt 发提醒

数据源：优先 yfinance（VPS 已装）；不可用时回退东方财富（stdlib）。

监控列表（git 可改）：friends/tools/us_dip_watchlist.json

用法：
  python3 friends/tools/fetch_us_dip.py
  python3 friends/tools/fetch_us_dip.py --email
  python3 friends/tools/fetch_us_dip.py --email-force

每日 cron（服务器，美股常规时段收盘后，例：中国时间工作日 05:30）：
  30 5 * * 2-6 /app/telegram/friends/tools/daily_us_dip_cron.sh >> /var/log/us-dip.log 2>&1
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
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))
TOOLS_DIR = Path(__file__).resolve().parent
ENV_FILE = TOOLS_DIR / "qdii_email.env"
RECIPIENTS_FILE = TOOLS_DIR / "qdii_email_recipients.txt"
WATCHLIST_FILE = TOOLS_DIR / "us_dip_watchlist.json"

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
            out[sym] = {
                "price": price,
                "change_pct": change_pct,
                "ath": ath,
                "ath_date": ath_date,
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


def build_payload(cfg: dict[str, Any], quotes: dict[str, dict[str, Any]]) -> dict[str, Any]:
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


def load_recipients(path: Path = RECIPIENTS_FILE, kind: str | None = None) -> list[str]:
    """kind='qdii'/'us' 时只返回带该类型或 all 的收件人。"""
    out: list[str] = []
    seen: set[str] = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_recipient_line(line)
        if not parsed:
            continue
        email, tags = parsed
        if kind is not None and kind not in tags and "all" not in tags:
            continue
        if email.lower() not in seen:
            seen.add(email.lower())
            out.append(email)
    return out


def _email_config() -> dict[str, Any]:
    _load_env_file(ENV_FILE)
    recipients = load_recipients(kind="us")
    if not recipients:
        recipients = [x.strip() for x in os.getenv("EMAIL_RECIPIENTS", "").split(",") if x.strip()]
    return {
        "enabled": _bool_env("EMAIL_ENABLED", False),
        "mode": os.getenv("EMAIL_MODE", "daily").strip().lower(),
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "use_tls": _bool_env("SMTP_USE_TLS", True),
        "username": os.getenv("SMTP_USERNAME", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": os.getenv("EMAIL_SENDER") or os.getenv("SMTP_USERNAME", ""),
        "recipients": recipients,
        "monitor_url": os.getenv("US_DIP_URL", "https://learn.tgfootclub.com/friends/us-dip.html"),
    }


def _has_buy(payload: dict[str, Any]) -> bool:
    return any(r.get("cum_buy_pct", 0) > 0 for r in payload.get("items") or [])


def render_email(payload: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, str, str]:
    has_buy = _has_buy(payload)
    items = [r for r in (payload.get("items") or []) if not r.get("error")]
    groups_order = payload.get("groups_order") or []
    title = payload.get("title") or "美股回撤阶梯买入监控"

    tag = "【买点触发】" if has_buy else "【日报】"
    subject = f"{tag}{title} · {payload.get('updated_at_text', '')}"

    lines = [f"更新时间：{payload.get('updated_at_text')}", ""]
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
        return (
            f"<tr>"
            f"<td>{r.get('group')}</td><td><b>{r.get('symbol')}</b></td>"
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

    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;color:#111">
<h2 style="color:#1e429f">{title}</h2>
<p>更新：{payload.get('updated_at_text')}</p>
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
<p style="color:#6b7280;font-size:12px">回撤=(现价−历史最高收盘)/历史最高收盘。仓位为“计划投入资金”的百分比，逐档累计。非投资建议。</p>
</body></html>"""
    return subject, plain, html


def send_email(payload: dict[str, Any], force: bool = False) -> str:
    cfg = _email_config()
    if not cfg["enabled"]:
        return "skip: EMAIL_ENABLED=false（配置 friends/tools/qdii_email.env 后开启）"
    if not cfg["host"] or not cfg["recipients"] or not cfg["sender"]:
        return "skip: SMTP/收件人未配置完整"

    mode = cfg["mode"]
    has_buy = _has_buy(payload)
    if not force and mode == "alert" and not has_buy:
        return "skip: EMAIL_MODE=alert 且当前无买点触发"

    subject, plain, html = render_email(payload, cfg)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(cfg["recipients"])
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
        return f"sent: → {', '.join(cfg['recipients'])} | {subject}"
    except Exception as e:  # noqa: BLE001
        return f"error: 邮件发送失败：{e}"


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
        return 1

    payload = build_payload(cfg, quotes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {args.out}  ({payload['updated_at_text']})  n={len(payload['items'])}")
    print(f"{'代码':<6} {'分组':<8} {'现价':>9} {'历史最高':>9} {'距高点%':>8} {'累计买%':>7} {'信号'}")
    for r in payload["items"]:
        if r.get("error"):
            print(f"{r['symbol']:<6} {r.get('group',''):<8} ERROR {r['error']}")
            continue
        print(
            f"{r['symbol']:<6} {r['group']:<8} {r['price']:>9.2f} {r['ath']:>9.2f} "
            f"{r['drawdown_pct']:>7.2f}% {r['cum_buy_pct']:>6}% {r['signal']}"
        )

    if args.email or args.email_force:
        status = send_email(payload, force=args.email_force)
        print(f"email: {status}")
        if status.startswith("error:"):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
