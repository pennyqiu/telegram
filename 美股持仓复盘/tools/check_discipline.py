#!/usr/bin/env python3
"""
组合纪律检查 · 日期层

把「写在规则里的时限」和「今天的日期」放在一起比对，这是决策日志第 118 行认定的缺失动作：
「纪律条文本身写得很好，缺的是定期把条文和当前数字放在一起比对的动作。」

本脚本只做**不需要行情**的那一层，因此没有数据源可以静默失效：

  1. 决策日志 §一 里所有未结案条目的失效期限 —— 逾期与临期
  2. 期权 21 DTE 时间闸门（规则 A3 / T5）—— 由 §B 的到期日反推
  3. §B 里到期日已过却还挂着的行 —— 台账没跟上，也可能是被行权了没记
  4. 距上次复盘多少天 —— 月度 / 季度节奏是否已经拖过

规则原文不在本文件里抄写，而是运行时从 `投资规则卡.md` 解析，
避免出现「知识在仓库里，但没有传导到配置」那类漂移。

数据以 `决策日志.md` 为准。已经处理但没更新状态的条目会一直被报出来——
这是刻意的：让台账不更新的成本立刻显现，而不是攒到下次复盘。

用法：
    python check_discipline.py                    # 打印报告
    python check_discipline.py --json             # 机器可读
    python check_discipline.py --email            # 发邮件（收件人见 discipline_recipients.txt）
    python check_discipline.py --today 2026-09-20 # 指定日期，用于自查与测试
    python check_discipline.py --earnings         # 额外查财报日（需要网络）

解析不到表格时会大声报错并以非零码退出，不会安静地少检查几行。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REVIEW_DIR = TOOLS_DIR.parent
REPO_ROOT = REVIEW_DIR.parent

DECISION_LOG = REVIEW_DIR / "决策日志.md"
RULES_CARD = REVIEW_DIR / "投资规则卡.md"
SNAPSHOT_DIR = REVIEW_DIR / "历史复盘"

# SMTP 凭证与 friends 那两个策略共用；收件人不共用，见 load_recipients。
ENV_FILE = REPO_ROOT / "friends" / "tools" / "qdii_email.env"
RECIPIENTS_FILE = TOOLS_DIR / "discipline_recipients.txt"

# 规则 A3：「到 21 DTE 无条件处理……绝不进入 21 DTE 以内」。
# 规则 T5 用的是同一条边界，所以一次检查覆盖两条。
DTE_GATE = 21

DEFAULT_GATE_LEAD_DAYS = 7
DEFAULT_DUE_SOON_DAYS = 7

# 复盘节奏来自 README 的四层设计：月度、季度。留几天余量再报。
MONTHLY_DAYS = 31
QUARTERLY_DAYS = 92

CALENDAR_API = "https://api.tgfootclub.com/api/calendar/{symbol}"
EARNINGS_LOOKAHEAD_DAYS = 14
ETF_SYMBOLS = {"QQQ", "QQQM", "IQQ", "SPY", "SPYM", "VOO", "IVV", "DRAM", "SGOV"}


# ---------------------------------------------------------------------------
# Markdown 解析
# ---------------------------------------------------------------------------

_SEPARATOR_RE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
_DATE_RE = re.compile(r"(20\d{2})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})")
_RULE_REF_RE = re.compile(r"\b([PCOTAF]\d+[a-z]?)\b")


def _clean(cell: str) -> str:
    """去掉 markdown 修饰，只留下人读的文字。"""
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    return cell.replace("**", "").replace("`", "").strip()


def _split_row(line: str) -> list[str]:
    return [_clean(c) for c in line.strip().strip("|").split("|")]


def find_tables(text: str, required: set[str]) -> list[list[dict[str, str]]]:
    """找出所有表头包含 required 全部列名的表格，按出现顺序返回。"""
    lines = text.splitlines()
    tables: list[list[dict[str, str]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.lstrip().startswith("|"):
            i += 1
            continue
        header = _split_row(line)
        if not required.issubset(set(header)) or i + 1 >= len(lines):
            i += 1
            continue
        if not _SEPARATOR_RE.match(lines[i + 1]):
            i += 1
            continue
        rows: list[dict[str, str]] = []
        j = i + 2
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            cells = _split_row(lines[j])
            if len(cells) == len(header):
                rows.append(dict(zip(header, cells)))
            j += 1
        tables.append(rows)
        i = j
    return tables


def find_table(text: str, required: set[str]) -> list[dict[str, str]]:
    tables = find_tables(text, required)
    return tables[0] if tables else []


def parse_date(raw: str) -> date | None:
    m = _DATE_RE.search(raw or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 规则卡
# ---------------------------------------------------------------------------

def load_rules(path: Path = RULES_CARD) -> dict[str, str]:
    """
    从投资规则卡里把「编号 → 规则原文」抽出来。

    P/C/O/T/A/F 六类表格的列名各不相同，统一取「编号之后的所有列」拼起来，
    这样规则卡改了措辞这边自动跟上，不需要两处维护。
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    rules: dict[str, str] = {}
    for table in find_tables(text, {"编号"}):
        for row in table:
            # 编号列有时带小标题，如「A3 时间闸门」。
            m = re.match(r"^([PCOTAF]\d+[a-z]?)\b(.*)$", row.get("编号", "").strip())
            if not m:
                continue
            code, label = m.group(1), m.group(2).strip()
            parts = [label] if label else []
            for k, v in row.items():
                # 「当前值」是快照时点的数据（列名还带着日期），不属于规则本身。
                if k == "编号" or k == "状态" or "当前值" in k:
                    continue
                if not v or v in {"—", "-"}:
                    continue
                parts.append(v if k in {"规则", "触发条件"} else f"{k}：{v}")
            if parts and code not in rules:
                rules[code] = " ｜ ".join(parts)
    return rules


def rule_refs(*texts: str) -> list[str]:
    """从决策条目的文字里挑出它引用了哪几条规则。"""
    found: list[str] = []
    for t in texts:
        for code in _RULE_REF_RE.findall(t or ""):
            if code not in found:
                found.append(code)
    return found


# ---------------------------------------------------------------------------
# 决策日志
# ---------------------------------------------------------------------------

# 状态列是自由文本，会写成「已决策：……理由待补」这种既结案又留尾巴的形式。
# 先判未结案标记，再判结案标记；两边都没有的按未结案处理，宁可多报一条。
OPEN_MARKERS = ("等待", "执行中", "已触发", "待落地", "待补", "待确认", "待填", "待办")
CLOSED_MARKERS = ("已完成", "已失效", "主动放弃", "已推翻", "已决策", "已结案")


@dataclass
class Decision:
    code: str
    symbol: str
    action: str
    trigger: str
    deadline: date | None
    deadline_raw: str
    rationale: str
    status: str

    @property
    def is_open(self) -> bool:
        s = self.status
        if any(m in s for m in OPEN_MARKERS):
            return True
        if any(m in s for m in CLOSED_MARKERS):
            return False
        return True

    @property
    def rules(self) -> list[str]:
        return rule_refs(self.trigger, self.rationale, self.action)


@dataclass
class Option:
    symbol: str
    intent: str
    strike: str
    expiry: date | None
    expiry_raw: str
    qty: int
    notional: float | None
    pnl: str


def parse_decisions(text: str) -> list[Decision]:
    rows = find_table(text, {"编号", "失效期限", "当前状态"})
    out: list[Decision] = []
    for row in rows:
        code = row.get("编号", "").strip()
        if not re.fullmatch(r"D\d+", code):
            continue
        raw_deadline = row.get("失效期限", "")
        out.append(
            Decision(
                code=code,
                symbol=row.get("标的", ""),
                action=row.get("判断内容", ""),
                trigger=row.get("目标价位或触发条件", ""),
                deadline=parse_date(raw_deadline),
                deadline_raw=raw_deadline,
                rationale=row.get("当时的理由", ""),
                status=row.get("当前状态", ""),
            )
        )
    return out


def parse_options(text: str) -> list[Option]:
    rows = find_table(text, {"标的", "到期日", "行权价", "张数"})
    out: list[Option] = []
    for row in rows:
        symbol = row.get("标的", "").strip()
        if not symbol:
            continue
        try:
            qty = int(re.sub(r"[^\d\-]", "", row.get("张数", "0")) or 0)
        except ValueError:
            qty = 0
        notional = None
        m = re.search(r"名义\s*([\d,]+)", row.get("盈亏平衡 / 名义", ""))
        if m:
            notional = float(m.group(1).replace(",", ""))
        raw_expiry = row.get("到期日", "")
        out.append(
            Option(
                symbol=symbol,
                intent=row.get("意图", ""),
                strike=row.get("行权价", ""),
                expiry=parse_date(raw_expiry),
                expiry_raw=raw_expiry,
                qty=qty,
                notional=notional,
                pnl=row.get("浮盈%", ""),
            )
        )
    return out


def parse_holdings(text: str) -> list[str]:
    """§A 速查表的代码列，用于财报日查询。"""
    rows = find_table(text, {"代码", "股数"})
    out: list[str] = []
    for row in rows:
        code = row.get("代码", "").strip().upper()
        if re.fullmatch(r"[A-Z.]{1,6}", code) and code not in out:
            out.append(code)
    return out


def last_review_date(directory: Path = SNAPSHOT_DIR) -> date | None:
    if not directory.exists():
        return None
    dates = [d for f in directory.glob("持仓快照-*.md") if (d := parse_date(f.name))]
    return max(dates) if dates else None


# ---------------------------------------------------------------------------
# 财报（可选，需要网络）
# ---------------------------------------------------------------------------

def fetch_earnings(symbols: list[str], today: date, lookahead: int) -> tuple[list[dict], str | None]:
    """取未来若干天内的财报日。失败时返回错误说明，由调用方显式展示，不装作没事。"""
    out: list[dict[str, Any]] = []
    failures: list[str] = []
    for sym in symbols:
        if sym in ETF_SYMBOLS:
            continue
        try:
            req = urllib.request.Request(
                CALENDAR_API.format(symbol=sym),
                headers={"User-Agent": "check_discipline/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            failures.append(f"{sym}({e.__class__.__name__})")
            continue
        for raw in data.get("earningsDate") or []:
            d = parse_date(str(raw))
            if d and today <= d <= today + timedelta(days=lookahead):
                out.append({"symbol": sym, "date": d.isoformat(), "days": (d - today).days})
                break
    out.sort(key=lambda x: x["date"])
    err = f"{len(failures)} 只查询失败：{', '.join(failures)}" if failures else None
    return out, err


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

@dataclass
class Report:
    today: date
    errors: list[str] = field(default_factory=list)
    overdue: list[dict] = field(default_factory=list)
    due_soon: list[dict] = field(default_factory=list)
    gate_breached: list[dict] = field(default_factory=list)
    gate_upcoming: list[dict] = field(default_factory=list)
    stale_options: list[dict] = field(default_factory=list)
    review: dict = field(default_factory=dict)
    earnings: list[dict] = field(default_factory=list)
    earnings_error: str | None = None
    rules: dict[str, str] = field(default_factory=dict)
    open_count: int = 0

    @property
    def alert_count(self) -> int:
        return (
            len(self.overdue)
            + len(self.gate_breached)
            + len(self.gate_upcoming)
            + len(self.stale_options)
            + (1 if self.review.get("overdue") else 0)
        )

    @property
    def has_any(self) -> bool:
        return bool(self.errors) or self.alert_count > 0 or bool(self.due_soon)


def build_report(
    today: date,
    due_soon_days: int = DEFAULT_DUE_SOON_DAYS,
    gate_lead_days: int = DEFAULT_GATE_LEAD_DAYS,
    with_earnings: bool = False,
) -> Report:
    # 路径显式传入，不靠默认参数——默认参数在函数定义时就绑死了，打桩会静默失效。
    rep = Report(today=today, rules=load_rules(RULES_CARD))

    if not DECISION_LOG.exists():
        rep.errors.append(f"找不到决策日志：{DECISION_LOG}")
        return rep

    text = DECISION_LOG.read_text(encoding="utf-8")
    decisions = parse_decisions(text)
    options = parse_options(text)

    # 解析不到就大声说，不要安静地报「全部合规」。
    if not decisions:
        rep.errors.append("决策日志 §一 表格解析失败，本次未检查任何决策期限")
    if not options:
        rep.errors.append("决策日志 §B 表格解析失败，本次未检查期权时间闸门")

    for d in (x for x in decisions if x.is_open):
        rep.open_count += 1
        if d.deadline is None:
            continue
        days = (d.deadline - today).days
        item = {
            "code": d.code,
            "symbol": d.symbol,
            "action": d.action,
            "deadline": d.deadline.isoformat(),
            "days": days,
            "status": d.status,
            "rules": d.rules,
        }
        if days < 0:
            item["overdue_days"] = -days
            rep.overdue.append(item)
        elif days <= due_soon_days:
            rep.due_soon.append(item)

    rep.overdue.sort(key=lambda x: -x["overdue_days"])
    rep.due_soon.sort(key=lambda x: x["days"])

    # 期权按到期日分组：A3 闸门是对整个到期日生效的，逐张报会淹没重点。
    groups: dict[date, list[Option]] = {}
    for o in options:
        if o.expiry is None:
            rep.errors.append(f"期权行到期日无法解析：{o.symbol} {o.strike} 「{o.expiry_raw}」")
            continue
        groups.setdefault(o.expiry, []).append(o)

    for expiry in sorted(groups):
        legs = groups[expiry]
        notional = sum(o.notional or 0 for o in legs)
        contracts = sum(abs(o.qty) for o in legs)
        detail = {
            "expiry": expiry.isoformat(),
            "gate_date": (expiry - timedelta(days=DTE_GATE)).isoformat(),
            "dte": (expiry - today).days,
            "contracts": contracts,
            "notional": notional,
            "legs": [f"{o.symbol} {o.strike}P×{abs(o.qty)}（{o.intent}）" for o in legs],
        }
        if expiry < today:
            detail["expired_days"] = (today - expiry).days
            rep.stale_options.append(detail)
            continue
        days_to_gate = (expiry - timedelta(days=DTE_GATE) - today).days
        detail["days_to_gate"] = days_to_gate
        if days_to_gate < 0:
            rep.gate_breached.append(detail)
        elif days_to_gate <= gate_lead_days:
            rep.gate_upcoming.append(detail)

    last = last_review_date(SNAPSHOT_DIR)
    if last is None:
        rep.review = {"last": None, "overdue": True, "note": "历史复盘目录下没有任何持仓快照"}
    else:
        gap = (today - last).days
        rep.review = {
            "last": last.isoformat(),
            "days": gap,
            "overdue": gap > MONTHLY_DAYS,
            "quarterly_overdue": gap > QUARTERLY_DAYS,
        }

    if with_earnings:
        rep.earnings, rep.earnings_error = fetch_earnings(
            parse_holdings(text), today, EARNINGS_LOOKAHEAD_DAYS
        )

    return rep


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def subject_of(rep: Report) -> str:
    stamp = rep.today.strftime("%m-%d")
    if rep.errors:
        return f"【解析失败】组合纪律 {stamp}"
    bits = []
    if rep.overdue:
        bits.append(f"逾期 {len(rep.overdue)}")
    if rep.gate_breached:
        bits.append(f"已越闸门 {len(rep.gate_breached)}")
    if rep.gate_upcoming:
        bits.append(f"闸门 {len(rep.gate_upcoming)}")
    if rep.stale_options:
        bits.append(f"台账过期 {len(rep.stale_options)}")
    if rep.review.get("overdue"):
        bits.append("复盘逾期")
    if not bits and rep.due_soon:
        bits.append(f"临期 {len(rep.due_soon)}")
    return f"【{' · '.join(bits)}】组合纪律 {stamp}" if bits else f"【全部合规】组合纪律 {stamp}"


def _rule_lines(rep: Report, codes: list[str], indent: str) -> list[str]:
    out = []
    for c in codes:
        if c in rep.rules:
            out.append(f"{indent}规则 {c}：{rep.rules[c]}")
    return out


def _money(v: float) -> str:
    return f"{v:,.0f}"


def _brief(text: str, limit: int = 48) -> str:
    """状态列常常写成整段核对记录，报告里只取开头，细节回原文件看。"""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def render_plain(rep: Report) -> str:
    L: list[str] = []
    L.append(subject_of(rep))
    L.append(f"检查日期 {rep.today.isoformat()} ｜ 数据源 决策日志.md、投资规则卡.md")
    L.append("=" * 60)

    if rep.errors:
        L.append("")
        L.append("■ 解析异常（下列检查本次没有执行）")
        for e in rep.errors:
            L.append(f"  · {e}")

    L.append("")
    L.append(f"■ 已逾期（{len(rep.overdue)}）")
    if not rep.overdue:
        L.append("  今日无")
    for it in rep.overdue:
        L.append(f"  {it['code']}  {it['symbol']}｜{_brief(it['action'], 90)}")
        L.append(f"        期限 {it['deadline']}，已逾期 {it['overdue_days']} 天，状态「{_brief(it['status'])}」")
        L.extend(_rule_lines(rep, it["rules"], "        "))

    if rep.gate_breached:
        L.append("")
        L.append(f"■ 已进入 21 DTE 以内（{len(rep.gate_breached)}）")
        for g in rep.gate_breached:
            L.append(f"  {g['expiry']} 到期 · {g['contracts']} 张 · 名义 {_money(g['notional'])}")
            L.append(f"        闸门日 {g['gate_date']} 已过 {-g['days_to_gate']} 天，当前 DTE {g['dte']}")
            L.append(f"        {'、'.join(g['legs'])}")
        L.extend(_rule_lines(rep, ["A3", "T5"], "        "))

    L.append("")
    L.append(f"■ 时间闸门临近（{len(rep.gate_upcoming)}）")
    if not rep.gate_upcoming:
        L.append("  今日无")
    for g in rep.gate_upcoming:
        L.append(f"  {g['expiry']} 到期 · {g['contracts']} 张 · 名义 {_money(g['notional'])}")
        L.append(f"        {g['gate_date']} 进入 21 DTE，还有 {g['days_to_gate']} 天")
        L.append(f"        {'、'.join(g['legs'])}")
    if rep.gate_upcoming:
        L.extend(_rule_lines(rep, ["A3", "T5"], "        "))

    if rep.stale_options:
        L.append("")
        L.append(f"■ 台账过期（{len(rep.stale_options)}）")
        L.append("  下列头寸的到期日已过，但仍挂在决策日志 §B。请确认是已平仓、还是被行权后没记。")
        for g in rep.stale_options:
            L.append(f"  {g['expiry']} 到期 · 已过 {g['expired_days']} 天 · {'、'.join(g['legs'])}")

    L.append("")
    L.append(f"■ {DEFAULT_DUE_SOON_DAYS} 天内到期的决策（{len(rep.due_soon)}）")
    if not rep.due_soon:
        L.append("  今日无")
    for it in rep.due_soon:
        L.append(f"  {it['code']}  {it['symbol']}｜{_brief(it['action'], 90)}")
        L.append(f"        期限 {it['deadline']}，还有 {it['days']} 天，状态「{_brief(it['status'])}」")

    L.append("")
    L.append("■ 复盘节奏")
    if rep.review.get("last") is None:
        L.append(f"  {rep.review.get('note', '无快照')}")
    else:
        tag = "已超季度节奏" if rep.review.get("quarterly_overdue") else (
            "已超月度节奏" if rep.review.get("overdue") else "正常"
        )
        L.append(f"  上次快照 {rep.review['last']}，距今 {rep.review['days']} 天 — {tag}")
    L.append(f"  未结案决策共 {rep.open_count} 条")

    if rep.earnings or rep.earnings_error:
        L.append("")
        L.append(f"■ {EARNINGS_LOOKAHEAD_DAYS} 天内财报")
        if rep.earnings_error:
            L.append(f"  ⚠ {rep.earnings_error}")
        if not rep.earnings:
            L.append("  今日无")
        for e in rep.earnings:
            L.append(f"  {e['symbol']}  {e['date']}（{e['days']} 天后）— 财报后核对标的档案第三节失效条件")

    L.append("")
    L.append("-" * 60)
    L.append("本报告以决策日志的状态列为准。已处理但未更新状态的条目会持续出现，")
    L.append("这是刻意设计：让台账不更新的成本立刻显现，而不是攒到下次复盘。")
    return "\n".join(L)


def _h(section: str, body: str, tone: str = "") -> str:
    color = {"bad": "#c0392b", "warn": "#b9770e", "ok": "#7f8c8d"}.get(tone, "#2c3e50")
    return (
        f'<h3 style="margin:22px 0 8px;font-size:15px;color:{color};'
        f'border-left:3px solid {color};padding-left:8px;">{escape(section)}</h3>{body}'
    )


def render_html(rep: Report) -> str:
    def card(lines: list[str], tone: str = "") -> str:
        bg = {"bad": "#fdedec", "warn": "#fef5e7", "ok": "#f8f9f9"}.get(tone, "#f8f9f9")
        inner = "".join(f"<div style='margin:4px 0;'>{x}</div>" for x in lines)
        return (
            f"<div style='background:{bg};border-radius:6px;padding:10px 12px;"
            f"margin:6px 0;font-size:13px;line-height:1.7;'>{inner}</div>"
        )

    def rules_html(codes: list[str]) -> str:
        out = []
        for c in codes:
            if c in rep.rules:
                out.append(
                    f"<div style='color:#7f8c8d;font-size:12px;margin-top:4px;'>"
                    f"规则 {escape(c)}：{escape(rep.rules[c])}</div>"
                )
        return "".join(out)

    P: list[str] = []
    P.append(
        f"<div style='font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;"
        f"max-width:720px;margin:0 auto;color:#2c3e50;'>"
    )
    P.append(f"<h2 style='margin:0 0 4px;font-size:18px;'>{escape(subject_of(rep))}</h2>")
    P.append(
        f"<div style='color:#7f8c8d;font-size:12px;'>检查日期 {rep.today.isoformat()}"
        f" ｜ 数据源 决策日志.md、投资规则卡.md</div>"
    )

    if rep.errors:
        P.append(_h("解析异常（下列检查本次没有执行）", card(
            [escape(e) for e in rep.errors], "bad"), "bad"))

    body = []
    for it in rep.overdue:
        body.append(card([
            f"<b>{escape(it['code'])}</b>　{escape(it['symbol'])}｜{escape(_brief(it['action'], 90))}",
            f"<span style='color:#c0392b;'>期限 {it['deadline']}，已逾期 "
            f"<b>{it['overdue_days']}</b> 天</span>，状态「{escape(_brief(it['status']))}」"
            + rules_html(it["rules"]),
        ], "bad"))
    P.append(_h(f"已逾期（{len(rep.overdue)}）", "".join(body) or card(["今日无"], "ok"),
                "bad" if rep.overdue else "ok"))

    if rep.gate_breached:
        body = []
        for g in rep.gate_breached:
            body.append(card([
                f"<b>{g['expiry']} 到期</b>　{g['contracts']} 张　名义 {_money(g['notional'])}",
                f"<span style='color:#c0392b;'>闸门日 {g['gate_date']} 已过 "
                f"{-g['days_to_gate']} 天，当前 DTE {g['dte']}</span>",
                escape("、".join(g["legs"])) + rules_html(["A3", "T5"]),
            ], "bad"))
        P.append(_h(f"已进入 21 DTE 以内（{len(rep.gate_breached)}）", "".join(body), "bad"))

    body = []
    for g in rep.gate_upcoming:
        body.append(card([
            f"<b>{g['expiry']} 到期</b>　{g['contracts']} 张　名义 {_money(g['notional'])}",
            f"<span style='color:#b9770e;'>{g['gate_date']} 进入 21 DTE，还有 "
            f"<b>{g['days_to_gate']}</b> 天</span>",
            escape("、".join(g["legs"])) + rules_html(["A3", "T5"]),
        ], "warn"))
    P.append(_h(f"时间闸门临近（{len(rep.gate_upcoming)}）",
                "".join(body) or card(["今日无"], "ok"),
                "warn" if rep.gate_upcoming else "ok"))

    if rep.stale_options:
        body = [card(["到期日已过但仍挂在决策日志 §B，请确认是已平仓、还是被行权后没记。"], "warn")]
        for g in rep.stale_options:
            body.append(card([
                f"<b>{g['expiry']} 到期</b>　已过 {g['expired_days']} 天",
                escape("、".join(g["legs"])),
            ], "warn"))
        P.append(_h(f"台账过期（{len(rep.stale_options)}）", "".join(body), "warn"))

    body = []
    for it in rep.due_soon:
        body.append(card([
            f"<b>{escape(it['code'])}</b>　{escape(it['symbol'])}｜{escape(_brief(it['action'], 90))}",
            f"期限 {it['deadline']}，还有 <b>{it['days']}</b> 天，状态「{escape(_brief(it['status']))}」",
        ], "warn"))
    P.append(_h(f"{DEFAULT_DUE_SOON_DAYS} 天内到期的决策（{len(rep.due_soon)}）",
                "".join(body) or card(["今日无"], "ok"),
                "warn" if rep.due_soon else "ok"))

    if rep.review.get("last") is None:
        review_line = escape(rep.review.get("note", "无快照"))
    else:
        tag = "已超季度节奏" if rep.review.get("quarterly_overdue") else (
            "已超月度节奏" if rep.review.get("overdue") else "正常"
        )
        review_line = f"上次快照 {rep.review['last']}，距今 <b>{rep.review['days']}</b> 天 — {tag}"
    P.append(_h("复盘节奏", card([review_line, f"未结案决策共 {rep.open_count} 条"],
                                 "warn" if rep.review.get("overdue") else "ok")))

    if rep.earnings or rep.earnings_error:
        lines = []
        if rep.earnings_error:
            lines.append(f"<span style='color:#b9770e;'>⚠ {escape(rep.earnings_error)}</span>")
        for e in rep.earnings:
            lines.append(
                f"<b>{escape(e['symbol'])}</b>　{e['date']}（{e['days']} 天后）"
                f"　— 财报后核对标的档案第三节失效条件"
            )
        P.append(_h(f"{EARNINGS_LOOKAHEAD_DAYS} 天内财报", card(lines or ["今日无"], "ok")))

    P.append(
        "<div style='margin-top:24px;padding-top:12px;border-top:1px solid #ecf0f1;"
        "color:#95a5a6;font-size:12px;line-height:1.7;'>"
        "本报告以决策日志的状态列为准。已处理但未更新状态的条目会持续出现，"
        "这是刻意设计：让台账不更新的成本立刻显现，而不是攒到下次复盘。</div>"
    )
    P.append("</div>")
    return "".join(P)


def to_dict(rep: Report) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": rep.today.isoformat(),
        "subject": subject_of(rep),
        "ok": not rep.errors,
        "errors": rep.errors,
        "alert_count": rep.alert_count,
        "overdue": rep.overdue,
        "due_soon": rep.due_soon,
        "gate_breached": rep.gate_breached,
        "gate_upcoming": rep.gate_upcoming,
        "stale_options": rep.stale_options,
        "review": rep.review,
        "earnings": rep.earnings,
        "earnings_error": rep.earnings_error,
        "open_count": rep.open_count,
    }


# ---------------------------------------------------------------------------
# 邮件
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


def load_recipients(path: Path = RECIPIENTS_FILE) -> list[str]:
    """
    收件人独立维护，**不复用** friends/tools/qdii_email_recipients.txt。

    那份名单里有朋友，而本报告含持仓、期权义务与现金缺口。共用名单迟早会把
    这些内容发出去，所以物理上不给它这条路径。
    """
    out: list[str] = []
    seen: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            email = line.split()[0].strip()
            if "@" in email and email.lower() not in seen:
                seen.add(email.lower())
                out.append(email)
    if not out:
        for e in os.getenv("DISCIPLINE_RECIPIENTS", "").split(","):
            e = e.strip()
            if "@" in e and e.lower() not in seen:
                seen.add(e.lower())
                out.append(e)
    return out


def send_email(rep: Report, only_alerts: bool = False) -> str:
    _load_env_file(ENV_FILE)
    if not _bool_env("EMAIL_ENABLED", False):
        return "skip: EMAIL_ENABLED=false"
    host = os.getenv("SMTP_HOST", "")
    sender = os.getenv("EMAIL_SENDER") or os.getenv("SMTP_USERNAME", "")
    if not host or not sender:
        return "skip: SMTP 未配置完整"
    recipients = load_recipients(RECIPIENTS_FILE)
    if not recipients:
        return f"skip: 收件人为空（{RECIPIENTS_FILE.name} 或 DISCIPLINE_RECIPIENTS）"
    if only_alerts and not rep.has_any:
        return "skip: 全部合规且已开启 --email-only-alerts"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject_of(rep)
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(render_plain(rep), "plain", "utf-8"))
    msg.attach(MIMEText(render_html(rep), "html", "utf-8"))

    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = _bool_env("SMTP_USE_TLS", True)
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, password)
            server.send_message(msg)
        return f"sent: → {', '.join(recipients)} | {msg['Subject']}"
    except Exception as e:  # noqa: BLE001
        return f"error: 邮件发送失败：{e}"


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="组合纪律检查（日期层）")
    ap.add_argument("--today", help="指定检查日期 YYYY-MM-DD，用于自查与测试")
    ap.add_argument("--due-soon", type=int, default=DEFAULT_DUE_SOON_DAYS,
                    help=f"决策临期提前天数，默认 {DEFAULT_DUE_SOON_DAYS}")
    ap.add_argument("--gate-lead", type=int, default=DEFAULT_GATE_LEAD_DAYS,
                    help=f"21 DTE 闸门提前天数，默认 {DEFAULT_GATE_LEAD_DAYS}")
    ap.add_argument("--earnings", action="store_true", help="额外查财报日（需要网络）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--email", action="store_true", help="发送邮件")
    ap.add_argument("--email-only-alerts", action="store_true",
                    help="全部合规时不发信（默认每次都发，用于确认任务还活着）")
    args = ap.parse_args()

    today = parse_date(args.today) if args.today else date.today()
    if today is None:
        print(f"无法解析日期：{args.today}", file=sys.stderr)
        return 2

    rep = build_report(today, args.due_soon, args.gate_lead, args.earnings)

    if args.json:
        print(json.dumps(to_dict(rep), ensure_ascii=False, indent=2))
    else:
        print(render_plain(rep))

    if args.email:
        status = send_email(rep, args.email_only_alerts)
        print(f"\n[email] {status}", file=sys.stderr)

    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
