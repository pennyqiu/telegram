#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拉取 A股场内「纳指100 / 标普500」全部 QDII ETF 现价与折溢价（东方财富）

字段（akshare fund_etf_spot_em 同源）：
  - f441 = IOPV 实时估值
  - f402 = 基金折价率%  → 溢价率% = -f402
  - f38  = 最新份额
  - f20  = 总市值（元）
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

每日 cron（服务器 UTC，工作日；邮件只由盘中两次发出）：
  0 3 * * 1-5  ... daily_qdii_cron.sh --light   # 北京 11:00 溢价 + 邮件
  0 6 * * 1-5  ... daily_qdii_cron.sh --light   # 北京 14:00 溢价 + 邮件
  30 7 * * 1-5 ... DAILY_QDII_EMAIL=0 daily_qdii_cron.sh   # 北京 15:30 收盘后只维护网页数据
完整命令见 daily_qdii_cron.sh 头部注释。

邮件投递（见 qdii_email_recipients.txt）：
  all  → 每次定时任务都发（心跳/失败通知）
  qdii → 仅「可投」机会时发
"""
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape as _html_escape
from pathlib import Path
from typing import Any

CST = timezone(timedelta(hours=8))
TOOLS_DIR = Path(__file__).resolve().parent
ENV_FILE = TOOLS_DIR / "qdii_email.env"
RECIPIENTS_FILE = TOOLS_DIR / "qdii_email_recipients.txt"
WATCHLIST_FILE = TOOLS_DIR / "qdii_watchlist.json"
FEES_CACHE_FILE = TOOLS_DIR / "qdii_fees_cache.json"


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
            # 抓不到费率页时的兜底值（可选，单位 %/年）
            "fee_mgmt_pct": it.get("fee_mgmt_pct"),
            "fee_custody_pct": it.get("fee_custody_pct"),
        })
    cfg["watch"] = watch
    cfg.setdefault("title", "场内 QDII 溢价监控")
    cfg.setdefault("groups_order", [])
    return cfg

API = (
    "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
    "?fltt=2&invt=2"
    "&fields=f12,f14,f2,f3,f5,f6,f8,f18,f20,f38,f152,f402,f441"
    "&secids={secids}"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def _fetch_json(url: str, *, timeout: int = 20, retries: int = 3, backoff: float = 3.0) -> dict[str, Any]:
    """带重试的 JSON GET：东财偶发 SSL 握手/连接超时，重试几次避免一次抖动就判失败。"""
    last_err: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
            last_err = e
            if i < retries - 1:
                time.sleep(backoff * (i + 1))
    raise RuntimeError(f"请求失败（已重试{retries}次）：{last_err}")


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and v == v:
        return float(v)
    return None


FEE_PAGE = "https://fundf10.eastmoney.com/jbgk_{code}.html"
FEE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}


def _fetch_text(url: str, headers: dict[str, str], *, timeout: int = 20, retries: int = 2) -> str:
    last_err: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
            last_err = e
            if i < retries - 1:
                time.sleep(2.0 * (i + 1))
    raise RuntimeError(f"请求失败：{last_err}")


def _parse_fee_pct(html: str, label: str) -> float | None:
    """从东财基金概况页取「管理费率 / 托管费率」的年费率百分数。"""
    flat = re.sub(r"\s+", "", html)
    m = re.search(label + r"</th><td[^>]*>(.*?)</td>", flat)
    if not m:
        return None
    m2 = re.search(r"([\d.]+)%", re.sub(r"<[^>]+>", "", m.group(1)))
    return float(m2.group(1)) if m2 else None


def load_fees_cache(path: Path = FEES_CACHE_FILE) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def fetch_fees(codes: list[str], *, use_cache_only: bool = False) -> dict[str, dict[str, Any]]:
    """
    抓每只基金的管理费率/托管费率。费率一年难得改一次，抓失败就用本地缓存兜底，
    保证行情正常时不会因为费率页抽风而整体失败。
    """
    cache = load_fees_cache()
    out: dict[str, dict[str, Any]] = {}
    today = datetime.now(CST).strftime("%Y-%m-%d")
    changed = False

    for code in codes:
        cached = cache.get(code) or {}
        if use_cache_only:
            if cached:
                out[code] = cached
            continue
        try:
            html = _fetch_text(FEE_PAGE.format(code=code), FEE_HEADERS)
            mgmt = _parse_fee_pct(html, "管理费率")
            custody = _parse_fee_pct(html, "托管费率")
        except RuntimeError:
            mgmt = custody = None
        if mgmt is None and custody is None:
            if cached:
                out[code] = cached
            continue
        rec = {"mgmt": mgmt, "custody": custody, "fetched_at": today}
        out[code] = rec
        if cached.get("mgmt") != mgmt or cached.get("custody") != custody:
            changed = True
        cache[code] = rec

    if changed or (not use_cache_only and out):
        try:
            FEES_CACHE_FILE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
    return out


def signal_for(premium_pct: float | None) -> str:
    """信号用中文：可投 / 谨慎 / 不投。"""
    if premium_pct is None:
        return "未知"
    if premium_pct < 2:
        return "可投"
    if premium_pct < 5:
        return "谨慎"
    return "不投"


def liquidity_tier(amount: float, shares: float | None) -> str:
    """综合成交额与份额，粗分流动性档位（辅助决策，非官方评级）。"""
    amt_yi = amount / 1e8  # 亿
    share_yi = (shares or 0) / 1e8
    if amt_yi >= 1.0 or share_yi >= 50:
        return "高"
    if amt_yi >= 0.3 or share_yi >= 15:
        return "中"
    return "低"


def fetch_quotes(watch_cfg: dict[str, Any], *, with_fees: bool = True) -> list[dict[str, Any]]:
    watchlist = watch_cfg["watch"]
    groups_order = list(watch_cfg.get("groups_order") or [])
    # 配置未写 groups_order 时，按首次出现顺序
    for x in watchlist:
        if x["group"] not in groups_order:
            groups_order.append(x["group"])
    group_rank = {g: i for i, g in enumerate(groups_order)}

    secids = ",".join(x["secid"] for x in watchlist)
    url = API.format(secids=secids)
    payload = _fetch_json(url)
    if payload.get("rc") != 0 or not payload.get("data") or not payload["data"].get("diff"):
        raise RuntimeError(f"eastmoney 返回异常: {payload.get('rc')} {payload.get('rt')}")

    by_code = {str(x.get("f12")): x for x in payload["data"]["diff"]}
    meta = {x["code"]: x for x in watchlist}
    fees = fetch_fees(list(meta.keys()), use_cache_only=not with_fees)
    rows: list[dict[str, Any]] = []

    for code, m in meta.items():
        fee = fees.get(code) or {}
        fee_mgmt = fee.get("mgmt") if fee.get("mgmt") is not None else m.get("fee_mgmt_pct")
        fee_custody = fee.get("custody") if fee.get("custody") is not None else m.get("fee_custody_pct")
        fee_total = None
        if fee_mgmt is not None or fee_custody is not None:
            fee_total = round((fee_mgmt or 0.0) + (fee_custody or 0.0), 3)

        raw = by_code.get(code)
        if not raw:
            rows.append({
                "code": code,
                "name": m["name"],
                "group": m["group"],
                "manager": m["manager"],
                "kind": "qdii",
                "fee_mgmt_pct": fee_mgmt,
                "fee_custody_pct": fee_custody,
                "fee_total_pct": fee_total,
                "error": "未返回行情",
                "signal": "未知",
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
        market_cap = _num(raw.get("f20"))  # 东财总市值
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

        # 缺 f20 时用 份额×现价 估算市值；净资产规模≈份额×IOPV
        if market_cap is None and shares is not None and price is not None:
            market_cap = shares * price
        aum = None
        if shares is not None and iopv is not None:
            aum = shares * iopv

        rows.append({
            "code": code,
            "name": name,
            "group": m["group"],
            "manager": m["manager"],
            "kind": "qdii",
            "fee_mgmt_pct": fee_mgmt,
            "fee_custody_pct": fee_custody,
            "fee_total_pct": fee_total,
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
            "market_cap": int(market_cap) if market_cap is not None else None,
            "market_cap_yi": round(market_cap / 1e8, 2) if market_cap is not None else None,
            "aum": int(aum) if aum is not None else None,
            "aum_yi": round(aum / 1e8, 2) if aum is not None else None,
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

    liq_rank = {"高": 0, "中": 1, "低": 2}
    sig_rank = {"可投": 0, "谨慎": 1, "不投": 2, "未知": 3}

    best: dict[str, Any] = {}
    cheapest: dict[str, Any] = {}
    for g in groups_order:
        cands = [r for r in rows if r.get("group") == g and r.get("premium_pct") is not None]
        if not cands:
            continue

        # 短期买点：优先可投，再低溢价，再流动性，再大市值
        def score(r):
            return (
                sig_rank.get(r.get("signal"), 9),
                r["premium_pct"],
                r.get("fee_total_pct") if r.get("fee_total_pct") is not None else 9,
                liq_rank.get(r.get("liquidity"), 9),
                -(r.get("market_cap") or 0),
            )

        # 长期持有：费率是每年确定要付的成本，先看费率，再看流动性/规模，溢价只作提示
        def score_longhold(r):
            return (
                r.get("fee_total_pct") if r.get("fee_total_pct") is not None else 9,
                liq_rank.get(r.get("liquidity"), 9),
                -(r.get("market_cap") or 0),
                r["premium_pct"],
            )

        best[g] = min(cands, key=score)
        with_fee = [r for r in cands if r.get("fee_total_pct") is not None]
        if with_fee:
            cheapest[g] = min(with_fee, key=score_longhold)

    def brief(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": r["code"],
            "name": r["name"],
            "manager": r.get("manager"),
            "premium_pct": r["premium_pct"],
            "price": r["price"],
            "iopv": r.get("iopv"),
            "fee_mgmt_pct": r.get("fee_mgmt_pct"),
            "fee_custody_pct": r.get("fee_custody_pct"),
            "fee_total_pct": r.get("fee_total_pct"),
            "liquidity": r.get("liquidity"),
            "amount_wan": r.get("amount_wan"),
            "shares_yi": r.get("shares_yi"),
            "market_cap_yi": r.get("market_cap_yi"),
            "aum_yi": r.get("aum_yi"),
            "signal": r["signal"],
        }

    return {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_text": now.strftime("%Y-%m-%d %H:%M:%S") + " CST",
        "title": watch_cfg.get("title") or "场内 QDII 溢价监控",
        "watchlist_file": "friends/tools/qdii_watchlist.json",
        "source": "eastmoney push2delay ulist (f441=IOPV, f402=折价率, f38=份额, f20=市值)",
        "field_note": watch_cfg.get("field_note")
        or "决策请综合溢价、流动性、市值，勿只看溢价。",
        "groups_order": groups_order,
        "rules": {
            "qdii_buy": "溢价 < 2% → 可投",
            "qdii_caution": "溢价 2%–5% → 谨慎",
            "qdii_avoid": "溢价 > 5% → 不投",
            "liquidity": "高≈日成交≥1亿或份额≥50亿份；中≈成交≥0.3亿或份额≥15亿；其余为低",
            "fee": "合计费率 = 管理费 + 托管费（每年从净值中扣，不单独收）；长期持有时每年少 0.2% 约等于 10 年少 2% 收益。",
            "note": "短期买点看溢价，长期持有看费率；两者都要够流动性与规模。",
        },
        "counts": {g: sum(1 for r in rows if r.get("group") == g) for g in groups_order},
        "best_by_group": {g: brief(r) for g, r in best.items()},
        "cheapest_by_group": {g: brief(r) for g, r in cheapest.items()},
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


_KIND_ALIASES = {
    "qdii": "qdii", "a": "qdii", "cn": "qdii", "国内": "qdii",
    "us": "us", "b": "us", "美股": "us", "qqq": "us", "spy": "us",
    "all": "all", "both": "all", "*": "all", "": "all",
}


def _parse_recipient_line(line: str) -> tuple[str, set[str]] | None:
    """解析一行：'email  qdii,us' → (email, {'qdii','us'})；无标签视为 {'all'}。"""
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
    path: Path = RECIPIENTS_FILE, kind: str = "qdii"
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
        always, alert = load_recipients_split(path, "qdii")
        always2, alert2 = load_recipients_split(path, "us")
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
    always, alert = load_recipients_split(kind="qdii")
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
        "monitor_url": os.getenv(
            "MONITOR_URL", "https://learn.tgfootclub.com/friends/qdii-monitor.html"
        ),
    }


def _has_buy(payload: dict[str, Any]) -> bool:
    return any(r.get("signal") == "可投" for r in payload.get("items") or [])


def render_email(payload: dict[str, Any], cfg: dict[str, Any]) -> tuple[str, str, str]:
    """返回 (subject, plain, html)。邮件内容完全跟随 git 配置的 qdii_watchlist.json。"""
    has_buy = _has_buy(payload)
    best = payload.get("best_by_group") or {}
    cheapest = payload.get("cheapest_by_group") or {}
    items = [r for r in (payload.get("items") or []) if not r.get("error")]
    groups_order = list(payload.get("groups_order") or best.keys())
    title = payload.get("title") or "场内 QDII 溢价监控"

    tag = "【可投机会】" if has_buy else "【日报】"
    subject = f"{tag}{title} · {payload.get('updated_at_text', '')}"

    lines = [
        f"更新时间：{payload.get('updated_at_text')}",
        "",
        "—— 短期买点参考（溢价优先）——",
    ]
    for g in groups_order:
        b = best.get(g)
        if not b:
            continue
        lines.append(
            f"{g}: {b['code']} {b.get('manager') or ''} | 溢价 {b['premium_pct']}% | "
            f"合计费率 {b.get('fee_total_pct')}%/年 | 市值 {b.get('market_cap_yi')}亿 | {b['signal']}"
        )
    if cheapest:
        lines += ["", "—— 长期持有参考（费率优先）——"]
        for g in groups_order:
            c = cheapest.get(g)
            if not c:
                continue
            lines.append(
                f"{g}: {c['code']} {c.get('manager') or ''} | 管理费 {c.get('fee_mgmt_pct')}% + 托管 {c.get('fee_custody_pct')}% "
                f"= {c.get('fee_total_pct')}%/年 | 当前溢价 {c['premium_pct']}%"
            )
    lines += ["", "—— 全部标的（按溢价升序）——"]
    for r in items:
        lines.append(
            f"{r['group']} {r['code']} {r.get('manager','')} "
            f"溢价{r.get('premium_pct')}% 合计费率{r.get('fee_total_pct')}%/年 "
            f"市值{r.get('market_cap_yi')}亿 → {r.get('signal')}"
        )
    if has_buy:
        buys = [r for r in items if r.get("signal") == "可投"]
        lines += ["", "★ 当前可投（溢价<2%）："]
        for r in buys:
            lines.append(
                f"  {r['group']} {r['code']} {r.get('manager') or ''} 溢价 {r['premium_pct']}% 市值 {r.get('market_cap_yi')}亿"
            )
    else:
        lines += ["", "当前无「可投」信号（全部溢价≥2%）。"]
    plain = "\n".join(lines)

    def row_html(r: dict[str, Any]) -> str:
        prem = r.get("premium_pct")
        color = "#b91c1c" if (prem is not None and prem > 5) else (
            "#c27803" if (prem is not None and prem >= 2) else "#057a55"
        )
        # 不列参考净值与管理费：溢价已含净值信息（现价/净值−1），费率决策只看合计。
        # 用公司名而非基金全名：「分组」已经说明跟的是哪个指数，全名只是第三次重复。
        return (
            f"<tr>"
            f"<td>{r.get('group')}</td><td><b>{r.get('code')}</b></td>"
            f"<td>{r.get('manager') or ''}</td>"
            f"<td>{r.get('price')}</td>"
            f"<td style='color:{color};font-weight:700'>{prem}%</td>"
            f"<td>{r.get('signal')}</td><td>{r.get('market_cap_yi')}</td>"
            f"<td><b>{r.get('fee_total_pct')}</b></td>"
            f"</tr>"
        )

    best_html = "".join(
        f"<li><b>{g}</b>：{b['code']} {b.get('manager') or ''} · 溢价 <b>{b['premium_pct']}%</b> · "
        f"合计费率 {b.get('fee_total_pct')}%/年 · 市值 {b.get('market_cap_yi')}亿 · {b['signal']}</li>"
        for g in groups_order if (b := best.get(g))
    )
    cheap_html = "".join(
        f"<li><b>{g}</b>：{c['code']} {c.get('manager') or ''} · 管理费 {c.get('fee_mgmt_pct')}% + 托管 "
        f"{c.get('fee_custody_pct')}% = <b>{c.get('fee_total_pct')}%/年</b> · 当前溢价 {c['premium_pct']}%</li>"
        for g in groups_order if (c := cheapest.get(g))
    )
    cheap_block = f"<h3>长期持有参考（费率优先）</h3><ul>{cheap_html}</ul>" if cheap_html else ""
    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;color:#111">
<h2 style="color:#b91c1c">{title}</h2>
<p>更新：{payload.get('updated_at_text')}</p>
<h3>短期买点参考（溢价优先）</h3>
<ul>{best_html}</ul>
{cheap_block}
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<thead style="background:#fef2f2"><tr>
<th>分组</th><th>代码</th><th>公司</th><th>现价</th>
<th>溢价%</th><th>信号</th><th>市值亿</th><th>合计费率%</th>
</tr></thead>
<tbody>
{''.join(row_html(r) for r in items)}
</tbody></table>
<p style="color:#6b7280;font-size:12px">规则：溢价&lt;2%可投 · 2–5%谨慎 · &gt;5%不投。费率为每年从净值中扣除，长期持有影响更大。非投资建议。</p>
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


def send_email(payload: dict[str, Any], force: bool = False) -> str:
    """
    投递规则（收件人标签优先，不再依赖 EMAIL_MODE）：
      - all  → 每次都发
      - qdii → 仅「可投」机会（或 --email-force）时发
    """
    cfg = _email_config()
    if not cfg["enabled"]:
        return "skip: EMAIL_ENABLED=false（配置 friends/tools/qdii_email.env 后开启）"
    if not cfg["host"] or not cfg["sender"]:
        return "skip: SMTP 未配置完整"

    has_buy = _has_buy(payload)
    recipients = list(cfg["always"])
    if force or has_buy:
        for e in cfg["alert"]:
            if e.lower() not in {x.lower() for x in recipients}:
                recipients.append(e)
    if not recipients:
        if not cfg["always"] and not cfg["alert"]:
            return "skip: 收件人为空"
        return "skip: 无可投信号；仅 all 类型收心跳日报（当前无 all 收件人）"

    subject, plain, html = render_email(payload, cfg)
    return _smtp_send(cfg, subject, plain, html, recipients)


def send_failure_email(error: str) -> str:
    """流程失败时只通知 all（心跳）收件人，便于区分「挂了」还是「没触发」。"""
    cfg = _email_config()
    if not cfg["enabled"]:
        return "skip: EMAIL_ENABLED=false"
    if not cfg["host"] or not cfg["sender"] or not cfg["always"]:
        return "skip: SMTP/all 收件人未配置"
    title = "场内 QDII 溢价监控"
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    subject = f"【失败】{title} · {now}"
    plain = (
        f"定时任务执行失败，请检查服务器日志 /var/log/qdii-premium.log\n\n"
        f"时间：{now}\n错误：{error}\n"
    )
    html = (
        f"<!DOCTYPE html><html><body style='font-family:sans-serif'>"
        f"<h2 style='color:#b91c1c'>【失败】{title}</h2>"
        f"<p>时间：{now}</p><pre style='background:#fef2f2;padding:12px'>{_html_escape(error)}</pre>"
        f"<p style='color:#6b7280;font-size:12px'>日志：/var/log/qdii-premium.log</p>"
        f"</body></html>"
    )
    return _smtp_send(cfg, subject, plain, html, cfg["always"])


def main() -> int:
    ap = argparse.ArgumentParser(description="拉取场内纳指100/标普500全部 QDII 溢价")
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--out", type=Path, default=root / "qdii-premium.json")
    ap.add_argument("--email", action="store_true", help="按 qdii_email.env 发送邮件提醒")
    ap.add_argument("--email-force", action="store_true", help="强制发邮件（忽略 alert 过滤）")
    ap.add_argument("--no-fees", action="store_true", help="不抓费率页，直接用本地缓存 qdii_fees_cache.json")
    args = ap.parse_args()

    try:
        watch_cfg = load_watchlist()
        rows = fetch_quotes(watch_cfg, with_fees=not args.no_fees)
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError, FileNotFoundError, ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if args.email or args.email_force:
            status = send_failure_email(str(e))
            print(f"email: {status}")
        return 1

    payload = build_payload(rows, watch_cfg)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {args.out}  ({payload['updated_at_text']})  n={len(rows)}")

    # 控制台摘要仅供人看；盘初个别 ETF 可能字段为 None，任何格式化异常都不得阻断邮件推送。
    def _n(v: Any, width: int, prec: int | None = None) -> str:
        if v is None:
            return f"{'-':>{width}}"
        return f"{v:>{width}}" if prec is None else f"{v:>{width}.{prec}f}"

    try:
        print(f"{'代码':<8} {'分组':<8} {'公司':<8} {'现价':>7} {'参考净值':>8} {'溢价%':>7} {'管理费%':>7} {'合计费%':>7} {'市值亿':>7} {'信号'}")
        for r in rows:
            if r.get("error"):
                print(f"{r['code']:<8} ERROR {r['error']}")
                continue
            print(
                f"{r['code']:<8} {r['group']:<8} {r['manager']:<8} "
                f"{_n(r.get('price'), 7, 3)} {_n(r.get('iopv'), 8, 4)} {_n(r.get('premium_pct'), 7, 2)} "
                f"{_n(r.get('fee_mgmt_pct'), 7, 2)} {_n(r.get('fee_total_pct'), 7, 2)} "
                f"{_n(r.get('market_cap_yi') or 0, 7, 2)} {r.get('signal')}"
            )
        print("\n短期买点参考（溢价优先）：")
        for g, b in payload["best_by_group"].items():
            print(
                f"  {g}: {b['code']} {b['name']} 溢价{b['premium_pct']}% "
                f"合计费率{b.get('fee_total_pct')}%/年 市值{b.get('market_cap_yi')}亿 → {b['signal']}"
            )
        print("\n长期持有参考（费率优先）：")
        for g, c in (payload.get("cheapest_by_group") or {}).items():
            print(
                f"  {g}: {c['code']} {c['name']} 管理费{c.get('fee_mgmt_pct')}%+托管{c.get('fee_custody_pct')}%"
                f"={c.get('fee_total_pct')}%/年 当前溢价{c['premium_pct']}%"
            )
    except Exception as e:  # noqa: BLE001  控制台摘要失败不影响邮件推送
        print(f"[warn] 控制台摘要渲染失败（不影响邮件）：{e}", file=sys.stderr)

    if args.email or args.email_force:
        status = send_email(payload, force=args.email_force)
        print(f"email: {status}")
        if status.startswith("error:"):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
