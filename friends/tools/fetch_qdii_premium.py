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
  python3 friends/tools/fetch_qdii_premium.py --email          # 按 qdii_email.env 发邮件
  python3 friends/tools/daily_qdii_cron.sh                     # 每日任务入口

收件人列表（git 可改，改完 push 后服务器 pull 即生效）：
  friends/tools/qdii_email_recipients.txt
监控标的列表：
  friends/tools/qdii_watchlist.json

每日 cron（服务器，中国时间工作日 15:20）：
  20 15 * * 1-5 /app/telegram/friends/tools/daily_qdii_cron.sh >> /var/log/qdii-premium.log 2>&1
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
WATCHLIST_FILE = TOOLS_DIR / "qdii_watchlist.json"


def _secid_for(code: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    # 51xxxx/5xxxxx 上交所；15xxxx 深交所
    return f"1.{code}" if code.startswith(("5", "6")) else f"0.{code}"


def load_watchlist(path: Path = WATCHLIST_FILE) -> dict[str, Any]:
    """从 git 配置文件加载监控列表。"""
    if not path.exists():
        raise FileNotFoundError(f"缺少监控列表配置：{path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    items = cfg.get("items") or []
    if not items:
        raise ValueError(f"监控列表为空：{path}")
    watch: list[dict[str, Any]] = []
    for it in items:
        code = str(it["code"]).strip()
        watch.append({
            "code": code,
            "secid": _secid_for(code, it.get("secid")),
            "name": it.get("name") or code,
            "group": it.get("group") or "其他",
            "manager": it.get("manager") or "",
        })
    cfg["watch"] = watch
    cfg.setdefault("title", "场内 QDII 溢价监控")
    cfg.setdefault("groups_order", [])
    return cfg

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


def fetch_quotes(watch_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    watchlist = watch_cfg["watch"]
    groups_order = list(watch_cfg.get("groups_order") or [])
    # 配置未写 groups_order 时，按首次出现顺序
    for x in watchlist:
        if x["group"] not in groups_order:
            groups_order.append(x["group"])
    group_rank = {g: i for i, g in enumerate(groups_order)}

    secids = ",".join(x["secid"] for x in watchlist)
    url = API.format(secids=secids)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("rc") != 0 or not payload.get("data") or not payload["data"].get("diff"):
        raise RuntimeError(f"eastmoney 返回异常: {payload.get('rc')} {payload.get('rt')}")

    by_code = {str(x.get("f12")): x for x in payload["data"]["diff"]}
    meta = {x["code"]: x for x in watchlist}
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

    def sort_key(r: dict[str, Any]):
        p = r.get("premium_pct")
        return (group_rank.get(r["group"], 99), 999 if p is None else p, -(r.get("amount") or 0))

    rows.sort(key=sort_key)
    return rows


def build_payload(rows: list[dict[str, Any]], watch_cfg: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(CST)
    groups_order = list(watch_cfg.get("groups_order") or [])
    for r in rows:
        if r.get("group") and r["group"] not in groups_order:
            groups_order.append(r["group"])

    best: dict[str, Any] = {}
    for g in groups_order:
        cands = [r for r in rows if r.get("group") == g and r.get("premium_pct") is not None]
        if not cands:
            continue
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
        "title": watch_cfg.get("title") or "场内 QDII 溢价监控",
        "watchlist_file": "friends/tools/qdii_watchlist.json",
        "source": "eastmoney push2delay ulist (f441=IOPV, f402=折价率, f38=份额)",
        "field_note": watch_cfg.get("field_note")
        or "决策请综合溢价、流动性、份额，勿只看溢价。",
        "groups_order": groups_order,
        "rules": {
            "qdii_buy": "溢价 < 2%",
            "qdii_caution": "溢价 2%–5%",
            "qdii_avoid": "溢价 > 5%",
            "liquidity": "高≈日成交≥1亿或份额≥50亿份；中≈成交≥0.3亿或份额≥15亿；其余为低",
            "note": "同类比价时优先低溢价+够流动性；份额过小易流动性差、溢价更易失控。",
        },
        "counts": {g: sum(1 for r in rows if r.get("group") == g) for g in groups_order},
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


def _load_env_file(path: Path) -> dict[str, str]:
    """简易 KEY=VALUE 加载（支持 # 注释），不覆盖已有环境变量。"""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
        out[k] = v
    return out


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def load_recipients(path: Path = RECIPIENTS_FILE) -> list[str]:
    """从 git 维护的收件人列表加载（一行一个邮箱）。"""
    out: list[str] = []
    seen: set[str] = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 兼容逗号分隔写在同一行
        for part in line.replace(";", ",").split(","):
            addr = part.strip()
            if addr and "@" in addr and addr.lower() not in seen:
                seen.add(addr.lower())
                out.append(addr)
    return out


def _email_config() -> dict[str, Any]:
    _load_env_file(ENV_FILE)
    # 优先用 git 收件人列表；文件为空时回退到 env 的 EMAIL_RECIPIENTS
    recipients = load_recipients()
    if not recipients:
        recipients = [x.strip() for x in os.getenv("EMAIL_RECIPIENTS", "").split(",") if x.strip()]
    return {
        "enabled": _bool_env("EMAIL_ENABLED", False),
        "mode": os.getenv("EMAIL_MODE", "daily").strip().lower(),  # daily|alert|both
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "use_tls": _bool_env("SMTP_USE_TLS", True),
        "username": os.getenv("SMTP_USERNAME", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": os.getenv("EMAIL_SENDER") or os.getenv("SMTP_USERNAME", ""),
        "recipients": recipients,
        "monitor_url": os.getenv(
            "MONITOR_URL", "https://learn.tgfootclub.com/friends/qdii-monitor.html"
        ),
    }


def _has_buy(payload: dict[str, Any]) -> bool:
    return any(r.get("signal") == "buy" for r in payload.get("items") or [])


def render_email(payload: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, str, str]:
    """返回 (subject, plain, html)。邮件内容完全跟随 git 配置的 qdii_watchlist.json。"""
    has_buy = _has_buy(payload)
    best = payload.get("best_by_group") or {}
    items = [r for r in (payload.get("items") or []) if not r.get("error")]
    groups_order = list(payload.get("groups_order") or best.keys())
    title = payload.get("title") or "场内 QDII 溢价监控"

    tag = "【可买机会】" if has_buy else "【日报】"
    subject = f"{tag}{title} · {payload.get('updated_at_text', '')}"

    lines = [
        f"标题：{title}",
        f"配置：friends/tools/qdii_watchlist.json（git）",
        f"更新时间：{payload.get('updated_at_text')}",
        f"监控页：{cfg['monitor_url']}",
        "",
        "—— 各组综合参考 ——",
    ]
    for g in groups_order:
        b = best.get(g)
        if not b:
            continue
        lines.append(
            f"{g}: {b['code']} {b['name']} | 溢价 {b['premium_pct']}% | "
            f"流动 {b.get('liquidity')} | 份额 {b.get('shares_yi')}亿 | {b['signal']}"
        )
    lines += ["", "—— 配置列表全部标的（按溢价升序）——"]
    for r in items:
        lines.append(
            f"{r['group']} {r['code']} {r.get('manager','')} "
            f"溢价{r.get('premium_pct')}% 流动{r.get('liquidity')} "
            f"份额{r.get('shares_yi')}亿 成交{r.get('amount_wan')}万 → {r.get('signal')}"
        )
    if has_buy:
        buys = [r for r in items if r.get("signal") == "buy"]
        lines += ["", "★ 当前可买（溢价<2%）："]
        for r in buys:
            lines.append(f"  {r['code']} {r['name']} 溢价 {r['premium_pct']}%")
    else:
        lines += ["", "当前无「可买」信号（全部溢价≥2%）。"]
    plain = "\n".join(lines)

    def row_html(r: dict[str, Any]) -> str:
        prem = r.get("premium_pct")
        color = "#b91c1c" if (prem is not None and prem > 5) else (
            "#c27803" if (prem is not None and prem >= 2) else "#057a55"
        )
        return (
            f"<tr>"
            f"<td>{r.get('group')}</td><td><b>{r.get('code')}</b></td>"
            f"<td>{r.get('name')}</td><td>{r.get('manager') or ''}</td>"
            f"<td>{r.get('price')}</td><td>{r.get('iopv')}</td>"
            f"<td style='color:{color};font-weight:700'>{prem}%</td>"
            f"<td>{r.get('signal')}</td><td>{r.get('liquidity')}</td>"
            f"<td>{r.get('shares_yi')}</td><td>{r.get('amount_wan')}</td>"
            f"</tr>"
        )

    best_html = "".join(
        f"<li><b>{g}</b>：{b['code']} {b['name']} · 溢价 <b>{b['premium_pct']}%</b> · "
        f"流动 {b.get('liquidity')} · {b['signal']}</li>"
        for g in groups_order if (b := best.get(g))
    )
    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;color:#111">
<h2 style="color:#b91c1c">{title}</h2>
<p>配置列表：<code>friends/tools/qdii_watchlist.json</code>（git 维护）<br>
更新：{payload.get('updated_at_text')}<br>
<a href="{cfg['monitor_url']}">{cfg['monitor_url']}</a></p>
<h3>各组综合参考</h3>
<ul>{best_html}</ul>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<thead style="background:#fef2f2"><tr>
<th>分组</th><th>代码</th><th>名称</th><th>公司</th><th>现价</th><th>IOPV</th>
<th>溢价%</th><th>信号</th><th>流动</th><th>份额亿</th><th>成交万</th>
</tr></thead>
<tbody>
{''.join(row_html(r) for r in items)}
</tbody></table>
<p style="color:#6b7280;font-size:12px">规则：溢价&lt;2%可买 · 2–5%谨慎 · &gt;5%回避。请综合流动性与份额，勿只看溢价。非投资建议。</p>
</body></html>"""
    return subject, plain, html


def send_email(payload: dict[str, Any], force: bool = False) -> str:
    """
    发送邮件。返回状态说明字符串。
    force=True 时忽略 EMAIL_MODE 的 alert 过滤（仍要求 EMAIL_ENABLED）。
    """
    cfg = _email_config()
    if not cfg["enabled"]:
        return "skip: EMAIL_ENABLED=false（配置 friends/tools/qdii_email.env 后开启）"
    if not cfg["host"] or not cfg["recipients"] or not cfg["sender"]:
        return "skip: SMTP/收件人未配置完整"

    mode = cfg["mode"]
    has_buy = _has_buy(payload)
    if not force:
        if mode == "alert" and not has_buy:
            return "skip: EMAIL_MODE=alert 且当前无可买信号"
        if mode not in {"daily", "alert", "both"}:
            return f"skip: 未知 EMAIL_MODE={mode}"

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
    except Exception as e:
        return f"error: 邮件发送失败：{e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取场内纳指100/标普500全部 QDII 溢价")
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--out", type=Path, default=root / "qdii-premium.json")
    ap.add_argument("--email", action="store_true", help="按 qdii_email.env 发送邮件提醒")
    ap.add_argument("--email-force", action="store_true", help="强制发邮件（忽略 alert 过滤）")
    args = ap.parse_args()

    try:
        watch_cfg = load_watchlist()
        rows = fetch_quotes(watch_cfg)
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError, FileNotFoundError, ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    payload = build_payload(rows, watch_cfg)
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

    if args.email or args.email_force:
        status = send_email(payload, force=args.email_force)
        print(f"email: {status}")
        if status.startswith("error:"):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
