#!/usr/bin/env python3
"""
check_discipline.py 的自检。无第三方依赖，直接跑：

    python3 test_check_discipline.py

重点覆盖三类容易出错的地方：
  1. 边界日期 —— 逾期与临期的分界、21 DTE 闸门的前后一天
  2. 状态分类 —— 「已决策：……理由待补」这种既结案又留尾巴的写法
  3. 静默失败 —— 表格解析不了时必须报错并非零退出，而不是输出「全部合规」
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_discipline as m  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        FAILURES.append(name)


def make_log(decisions: str, options: str) -> str:
    """拼一份最小的决策日志，列名与真实文件保持一致。"""
    return f"""# 决策日志

### B. 期权 Sell Put 义务一览

| 标的 | 意图 | 行权价 | 到期日 | 张数 | 开仓权利金 | 当前标记 | 浮盈% | 盈亏平衡 / 名义 |
|------|------|--------|--------|------|------------|----------|-------|-----------------|
{options}

## 一、进行中的决策（等待条件）

| 编号 | 建立日期 | 标的 | 判断内容 | 目标价位或触发条件 | 失效期限 | 当时的理由 | 当前状态 |
|------|----------|------|----------|-------------------|----------|------------|----------|
{decisions}
"""


def with_log(text: str, today: date, **kw):
    """把 DECISION_LOG 指到临时文件后跑一次 build_report。"""
    original = m.DECISION_LOG
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "决策日志.md"
        p.write_text(text, encoding="utf-8")
        m.DECISION_LOG = p
        try:
            return m.build_report(today, **kw)
        finally:
            m.DECISION_LOG = original


# ---------------------------------------------------------------------------

def test_status_classification() -> None:
    print("\n[状态分类]")
    cases = [
        ("等待执行", True),
        ("等待中", True),
        ("等待讨论", True),
        ("执行中", True),
        ("已采纳，待落地", True),
        ("已推翻，见 D011", False),
        ("主动放弃（2026-08-01，本人决定两只都留）", False),
        ("已决策：保留 META（本人决定）。价格纪律：现价不加仓", False),
        # 既宣布结案又留了尾巴的，按未结案处理，否则这条尾巴永远没人管
        ("已决策：两只都保留。保留两只的理由待补写入 ETF 档案", True),
        ("某种没见过的写法", True),  # 未知状态宁可多报
    ]
    for status, expected in cases:
        d = m.Decision("D999", "X", "a", "t", None, "", "r", status)
        check(f"「{status[:22]}」→ {'未结案' if expected else '已结案'}", d.is_open == expected)


def test_deadline_buckets() -> None:
    print("\n[逾期与临期的分界]")
    rows = "\n".join([
        "| D001 | 2026-08-01 | QCOM | 平仓 | 规则 T2 已触发 | 2026-08-05 | 浮亏 101% | 等待执行 |",
        "| D002 | 2026-08-01 | 全组合 | 补数据 | 尽快 | 2026-08-26 | 口径 | 等待执行 |",
        "| D003 | 2026-08-01 | X | 做点啥 | — | 2026-09-01 | 理由 | 等待中 |",
        "| D004 | 2026-08-01 | Y | 做点啥 | — | 2026-12-31 | 理由 | 等待中 |",
        "| D005 | 2026-08-01 | Z | 已经不用管了 | — | 2026-08-05 | 理由 | 已推翻，见 D001 |",
        "| D006 | 2026-08-01 | W | 长期执行 | — | 长期 | 理由 | 执行中 |",
    ])
    rep = with_log(make_log(rows, ""), date(2026, 8, 26))
    codes_overdue = [x["code"] for x in rep.overdue]
    codes_soon = [x["code"] for x in rep.due_soon]

    check("逾期只含 D001", codes_overdue == ["D001"], f"实际 {codes_overdue}")
    check("逾期天数算对（08-05 → 08-26 是 21 天）", rep.overdue[0]["overdue_days"] == 21)
    check("期限就是今天 → 算临期不算逾期", "D002" in codes_soon and "D002" not in codes_overdue)
    check("7 天内的 D003 进临期", "D003" in codes_soon, f"实际 {codes_soon}")
    check("远期的 D004 不报", "D004" not in codes_soon + codes_overdue)
    check("已推翻的 D005 即使过期也不报", "D005" not in codes_overdue)
    check("失效期限写「长期」不报，但计入未结案", rep.open_count == 5, f"实际 {rep.open_count}")
    check("规则原文从规则卡带出（T2）", "T2" in rep.overdue[0]["rules"])


def test_dte_gate_boundaries() -> None:
    print("\n[21 DTE 闸门边界]")
    opt = "| QQQ | 收租型 | 620 | 2026-09-18 | -2 | 10.11 | 5.72 | +43.4% | 名义 124,000 |"

    # 闸门日 = 2026-09-18 − 21 天 = 2026-08-28
    rep = with_log(make_log("", opt), date(2026, 8, 20))
    check("距闸门 8 天（超出提前量 7）→ 不报", not rep.gate_upcoming and not rep.gate_breached)

    rep = with_log(make_log("", opt), date(2026, 8, 21))
    check("距闸门 7 天 → 进入提醒", len(rep.gate_upcoming) == 1)

    rep = with_log(make_log("", opt), date(2026, 8, 28))
    check("闸门当天 → 仍算临近未越线", len(rep.gate_upcoming) == 1 and not rep.gate_breached)
    check("闸门当天 days_to_gate 为 0", rep.gate_upcoming[0]["days_to_gate"] == 0)

    rep = with_log(make_log("", opt), date(2026, 8, 29))
    check("闸门后一天 → 判为已越线", len(rep.gate_breached) == 1 and not rep.gate_upcoming)
    check("已越线时 DTE 小于 21", rep.gate_breached[0]["dte"] < m.DTE_GATE)

    rep = with_log(make_log("", opt), date(2026, 9, 19))
    check("到期日已过 → 转入台账过期", len(rep.stale_options) == 1 and not rep.gate_breached)
    check("台账过期天数算对", rep.stale_options[0]["expired_days"] == 1)


def test_gate_grouping() -> None:
    print("\n[同一到期日合并]")
    opts = "\n".join([
        "| SPYM | 收租型 | 83 | 2026-09-18 | -5 | 0.94 | 0.582 | +38.4% | 名义 41,500 |",
        "| SPYM | 收租型 | 86 | 2026-09-18 | -4 | 1.34 | 1.041 | +22.5% | 名义 34,400 |",
        "| QQQ | 收租型 | 630 | 2026-10-16 | -1 | 11.29 | 11.05 | +2.1% | 名义 63,000 |",
    ])
    rep = with_log(make_log("", opts), date(2026, 8, 26))
    check("只报到期日临近的那一组", len(rep.gate_upcoming) == 1)
    g = rep.gate_upcoming[0]
    check("同一到期日的张数合并", g["contracts"] == 9, f"实际 {g['contracts']}")
    check("同一到期日的名义合并", g["notional"] == 75900, f"实际 {g['notional']}")
    check("腿的明细保留", len(g["legs"]) == 2)


def test_parse_failure_is_loud() -> None:
    """SPLG 的教训：静默失败看起来和一切正常完全一样。"""
    print("\n[解析失败必须大声]")
    rep = with_log("# 决策日志\n\n什么表格都没有。\n", date(2026, 8, 26))
    check("解析不到表格 → 记录错误", len(rep.errors) >= 2, f"实际 {rep.errors}")
    check("错误里点名决策表", any("§一" in e for e in rep.errors))
    check("错误里点名期权表", any("§B" in e for e in rep.errors))
    check("标题写「解析失败」而不是「全部合规」", "解析失败" in m.subject_of(rep))
    check("JSON 的 ok 为 false", m.to_dict(rep)["ok"] is False)

    original = m.DECISION_LOG
    m.DECISION_LOG = Path("/nonexistent/决策日志.md")
    try:
        rep = m.build_report(date(2026, 8, 26))
    finally:
        m.DECISION_LOG = original
    check("文件不存在 → 报错而非当作没有待办", bool(rep.errors))

    # 到期日写坏的行必须被点名，不能悄悄跳过
    bad = "| QQQ | 收租型 | 620 | 待定 | -2 | 10.11 | 5.72 | +43.4% | 名义 124,000 |"
    rep = with_log(make_log("", bad), date(2026, 8, 26))
    check("到期日无法解析 → 点名该行", any("无法解析" in e for e in rep.errors))


def test_clean_day() -> None:
    print("\n[全部合规时]")
    rows = "| D001 | 2026-08-01 | X | 做点啥 | — | 2026-12-31 | 理由 | 等待中 |"
    opt = "| QQQ | 收租型 | 620 | 2026-12-18 | -2 | 10.11 | 5.72 | +2% | 名义 124,000 |"
    rep = with_log(make_log(rows, opt), date(2026, 8, 26))
    check("无逾期无闸门", not rep.overdue and not rep.gate_upcoming and not rep.gate_breached)
    check("无解析错误", not rep.errors)
    plain = m.render_plain(rep)
    check("空区段显式写「今日无」", plain.count("今日无") >= 3,
          "必须能区分「没触发」和「没检查」")


def test_rules_card() -> None:
    print("\n[规则卡解析]")
    rules = m.load_rules(m.RULES_CARD)
    check("规则卡能解析出内容", len(rules) > 10, f"实际 {len(rules)} 条")
    check("A3 带小标题也能识别", "A3" in rules)
    check("A3 原文包含 21 DTE", "21 DTE" in rules.get("A3", ""))
    check("T2 有 48 小时时限", "48" in rules.get("T2", ""))
    check("P1 有软硬线", "20%" in rules.get("P1", "") and "30%" in rules.get("P1", ""))
    check("不把快照当期数据当成规则", "25.3%" not in rules.get("P1", ""),
          "「当前值」列必须排除，否则规则会随快照过期")


def test_recipients_isolation() -> None:
    """报告含持仓、期权义务与现金缺口，绝不能落到朋友那份名单里。"""
    print("\n[收件人隔离]")
    friends = m.REPO_ROOT / "friends" / "tools" / "qdii_email_recipients.txt"
    check("收件人文件与 friends 的不是同一个", m.RECIPIENTS_FILE != friends)
    original = m.RECIPIENTS_FILE
    m.RECIPIENTS_FILE = Path("/nonexistent/discipline_recipients.txt")
    import os
    saved = os.environ.pop("DISCIPLINE_RECIPIENTS", None)
    try:
        got = m.load_recipients(m.RECIPIENTS_FILE)
        check("没配收件人时返回空，不回退到朋友名单", got == [], f"实际 {got}")
    finally:
        m.RECIPIENTS_FILE = original
        if saved is not None:
            os.environ["DISCIPLINE_RECIPIENTS"] = saved


def test_real_files() -> None:
    print("\n[对真实文件跑一遍]")
    rep = m.build_report(date(2026, 8, 26))
    check("真实决策日志解析无错", not rep.errors, f"错误：{rep.errors}")
    check("解析出未结案决策", rep.open_count > 0)
    check("纯文本渲染不抛异常", isinstance(m.render_plain(rep), str))
    check("HTML 渲染不抛异常", "<div" in m.render_html(rep))
    check("JSON 可序列化", isinstance(m.to_dict(rep)["today"], str))


def main() -> int:
    print("check_discipline 自检")
    print("=" * 52)
    test_status_classification()
    test_deadline_buckets()
    test_dte_gate_boundaries()
    test_gate_grouping()
    test_parse_failure_is_loud()
    test_clean_day()
    test_rules_card()
    test_recipients_isolation()
    test_real_files()
    print("=" * 52)
    if FAILURES:
        print(f"{len(FAILURES)} 项失败：")
        for f in FAILURES:
            print(f"  · {f}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
