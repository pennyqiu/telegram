"""
期权卖方真实数据拉取器（公开数据源版 · 无需 IB 账户）

为什么有这个：IB 账户/行情权限还在申请时，无法用 tools/qcom_options.py 连 Gateway。
本脚本改用 **CBOE 官方延迟报价**（免费、无需登录），即可拿到真实数据：
  - 正股现价
  - 完整期权链
  - ★ 真实希腊字母 Delta / Gamma / Theta / Vega / IV（CBOE 直接给，无需自己反推）

能做什么：
  1. 按目标 DTE 自动挑最接近的真实到期。
  2. 按目标 |Delta| 挑出真实行权价。
  3. 两种结构模式：
       --mode naked  ：裸卖 Put（Margin-Secured Put）+ 深虚值尾部对冲腿（默认）
       --mode spread ：牛市看跌价差（Bull Put Spread，定义风险，每条腿自带保护）
  4. 输出真实头寸表：权利金现金流、名义敞口/最大风险、组合希腊字母。
  5. --stress：用真实 IV/价格做 Black-Scholes 重定价，算 -20%/+50%IV 等情景的组合盈亏。
  6. --notify：把报告推送到 Telegram（复用项目的 notifier / 同一个 Bot 配置）。

⚠️ 局限：CBOE 不提供"你账户的保证金"。
   - naked 模式：保证金为模型估算（PM 压力法），仅供规划，账户下来后用 whatIf 复核。
   - spread 模式：最大风险=(价差宽度-净权利金)，这是**确定的**，无需依赖券商。
   数据为 CBOE 延迟报价（约 15 分钟），盘后为上一交易日收盘附近快照。

用法（在 ib_quant 目录下）：
  python tools/options_data.py --stress
  python tools/options_data.py --mode spread --spread-width 20 --stress
  python tools/options_data.py --stress --notify
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"


# ── Black-Scholes（用于压力情景重定价） ──────────────────────────────

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(spot: float, strike: float, t: float, iv: float, r: float) -> float:
    """欧式看跌期权理论价。"""
    if t <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return max(strike - spot, 0.0)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    return strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class OptQuote:
    expiry: str          # YYYY-MM-DD
    dte: int
    strike: float
    bid: float
    ask: float
    iv: float            # 小数，如 0.70
    delta: float         # 原值（看跌为负）
    gamma: float
    theta: float
    vega: float
    oi: float

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 2)
        return round(max(self.bid, self.ask), 2)

    @property
    def absdelta(self) -> float:
        return abs(self.delta)


@dataclass
class Position:
    label: str
    leg: OptQuote
    qty: int
    side: int            # +1 卖出(short), -1 买入(long)


@dataclass
class Report:
    symbol: str
    asof: str
    spot: float
    nlv: float
    mode: str
    positions: list[Position] = field(default_factory=list)
    total_credit: float = 0.0
    total_notional: float = 0.0     # 短腿行权价口径
    max_risk: float = 0.0           # spread=确定最大风险; naked=估算保证金
    risk_is_exact: bool = False
    net_delta: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    stress_rows: list[dict] = field(default_factory=list)
    stress_total: float = 0.0
    stress_spot: float = 0.0
    stress_iv: float = 0.0
    max_notional_mult: float = 1.5


# ── CBOE 拉取 / 解析 ─────────────────────────────────────────────────

def fetch_cboe(symbol: str, retries: int = 4) -> dict:
    """拉取 CBOE 延迟报价 JSON；网络偶发 SSL 中断时重试，并回退到 requests。"""
    url = CBOE_URL.format(sym=symbol.upper())
    headers = {"User-Agent": "Mozilla/5.0"}
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
        try:
            import requests
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
        wait = 2 * (i + 1)
        print(f"  拉取失败({last_err.__class__.__name__})，{wait}s 后重试 {i+1}/{retries} ...")
        time.sleep(wait)
    raise RuntimeError(f"多次拉取 CBOE 失败：{last_err}")


def _parse_occ(sym: str, root: str) -> tuple[str, str, float]:
    body = sym[len(root):]
    yy, mm, dd = body[0:2], body[2:4], body[4:6]
    cp = body[6]
    strike = int(body[7:]) / 1000.0
    return f"20{yy}-{mm}-{dd}", cp, strike


def parse_puts(data: dict, symbol: str) -> tuple[float, str, list[OptQuote]]:
    d = data.get("data", {})
    spot = float(d.get("current_price") or 0)
    asof = d.get("last_trade_time") or ""
    puts: list[OptQuote] = []
    today = date.today()
    for o in d.get("options", []):
        exp, cp, strike = _parse_occ(o["option"], symbol.upper())
        if cp != "P":
            continue
        dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
        puts.append(OptQuote(
            expiry=exp, dte=dte, strike=strike,
            bid=float(o.get("bid", 0)), ask=float(o.get("ask", 0)),
            iv=float(o.get("iv", 0)), delta=float(o.get("delta", 0)),
            gamma=float(o.get("gamma", 0)), theta=float(o.get("theta", 0)),
            vega=float(o.get("vega", 0)), oi=float(o.get("open_interest", 0)),
        ))
    return spot, asof, puts


# ── 选腿 ──────────────────────────────────────────────────────────────

def pick_expiries(puts: list[OptQuote], target_dtes: list[int]) -> list[int]:
    all_dte = sorted({p.dte for p in puts if p.dte > 0})
    chosen: list[int] = []
    for td in target_dtes:
        best = min(all_dte, key=lambda x: abs(x - td))
        if best not in chosen:
            chosen.append(best)
    return chosen


def pick_by_delta(puts: list[OptQuote], dte: int, target_delta: float) -> Optional[OptQuote]:
    cands = [p for p in puts if p.dte == dte and p.absdelta > 0 and p.bid + p.ask > 0]
    if not cands:
        return None
    return min(cands, key=lambda p: abs(p.absdelta - target_delta))


def pick_by_strike(puts: list[OptQuote], dte: int, target_strike: float) -> Optional[OptQuote]:
    cands = [p for p in puts if p.dte == dte and p.bid + p.ask > 0]
    if not cands:
        return None
    return min(cands, key=lambda p: abs(p.strike - target_strike))


# ── 保证金估算（仅 naked 模式；账户下来后以 whatIf 为准） ──────────────

def est_pm_initial_margin(leg: OptQuote, spot: float, r: float,
                          spot_shock: float = -0.15, iv_shock: float = 0.25) -> float:
    """PM 风格估算：短 Put 在 -15% 价 / +25% IV 情景下的 MtM 损失（每张，USD）。"""
    t = max(leg.dte, 1) / 365.0
    now = bs_put(spot, leg.strike, t, leg.iv, r)
    shocked = bs_put(spot * (1 + spot_shock), leg.strike, t, leg.iv * (1 + iv_shock), r)
    return max(shocked - now, 0.0) * 100


# ── 结构构建 + 仓位 sizing ────────────────────────────────────────────

@dataclass
class Structure:
    """一个可重复的结构单元（naked=1短腿; spread=1短腿+1长腿）。"""
    legs: list[tuple[OptQuote, int, str]]   # (期权, side, 标签)
    credit_unit: float                      # 每单元净权利金($/张)
    margin_unit: float                      # 每单元保证金/最大风险($)
    notional_unit: float                    # 每单元短腿名义($)


def build_structures(args, spot, puts, chosen) -> tuple[list[Structure], Optional[OptQuote]]:
    structures: list[Structure] = []
    labels = ["A", "B", "C", "D"]
    hedge_leg = None

    for i, (dte, td) in enumerate(zip(chosen, args.short_deltas)):
        short = pick_by_delta(puts, dte, td)
        if not short:
            continue
        lab = labels[i]
        if args.mode == "spread":
            long = pick_by_strike(puts, dte, short.strike - args.spread_width)
            if not long or long.strike >= short.strike:
                continue
            credit = short.mid - long.mid
            width = short.strike - long.strike
            margin = max(width - credit, 0.0) * 100        # 确定的最大风险
            structures.append(Structure(
                legs=[(short, +1, lab), (long, -1, lab + "↓")],
                credit_unit=credit, margin_unit=margin,
                notional_unit=short.strike * 100,
            ))
        else:  # naked
            structures.append(Structure(
                legs=[(short, +1, lab)],
                credit_unit=short.mid,
                margin_unit=est_pm_initial_margin(short, spot, args.r),
                notional_unit=short.strike * 100,
            ))

    # naked 模式：最远到期加一条深虚值尾部对冲腿
    if args.mode == "naked" and chosen:
        far = max(chosen)
        hedge_leg = pick_by_delta(puts, far, args.hedge_delta)

    return structures, hedge_leg


def size_positions(args, structures, hedge_leg) -> tuple[list[Position], int]:
    if not structures:
        return [], 0
    nlv = float(args.nlv)
    target_im = nlv * args.target_im
    max_notional = nlv * args.max_notional

    avg_margin = sum(s.margin_unit for s in structures) / len(structures)
    avg_notional = sum(s.notional_unit for s in structures) / len(structures)
    n_by_im = int(target_im / avg_margin) if avg_margin > 0 else 9999
    n_by_notional = int(max_notional / avg_notional) if avg_notional > 0 else n_by_im
    total_units = max(2, min(n_by_im, n_by_notional))

    k = len(structures)
    per = [total_units // k] * k
    for i in range(total_units - sum(per)):
        per[i] += 1

    positions: list[Position] = []
    for s, q in zip(structures, per):
        for leg, side, lab in s.legs:
            positions.append(Position(label=lab, leg=leg, qty=q, side=side))

    if hedge_leg:
        hedge_qty = max(1, round(total_units / 2))
        positions.append(Position(label="H", leg=hedge_leg, qty=hedge_qty, side=-1))

    return positions, total_units


# ── 汇总与压力 ────────────────────────────────────────────────────────

def compute_report(args, spot, asof, puts, positions, structures, total_units) -> Report:
    rep = Report(symbol=args.symbol.upper(), asof=asof, spot=spot,
                 nlv=float(args.nlv), mode=args.mode,
                 max_notional_mult=args.max_notional, positions=positions)

    for p in positions:
        rep.total_credit += p.side * p.leg.mid * 100 * p.qty
        # 短腿(+1)持仓 delta = -期权delta；长腿(-1)= +期权delta -> 统一 -side*delta
        rep.net_delta += -p.side * p.leg.delta * 100 * p.qty
        rep.net_theta += -p.side * p.leg.theta * 100 * p.qty
        rep.net_vega += -p.side * p.leg.vega * 100 * p.qty
        if p.side > 0:
            rep.total_notional += p.leg.strike * 100 * p.qty

    if args.mode == "spread":
        # 逐结构 × 实际手数，得到确定的最大风险（=保证金）
        rep.max_risk = 0.0
        per_unit = total_units // len(structures)
        rem = total_units - per_unit * len(structures)
        for i, s in enumerate(structures):
            q = per_unit + (1 if i < rem else 0)
            rep.max_risk += s.margin_unit * q
        rep.risk_is_exact = True
    else:
        avg_margin = sum(s.margin_unit for s in structures) / len(structures)
        hedge_cost = 0.0
        for p in positions:
            if p.label == "H":
                hedge_cost = p.leg.mid * 100 * p.qty * 0.5
        rep.max_risk = avg_margin * total_units - hedge_cost
        rep.risk_is_exact = False

    if args.stress:
        rep.stress_spot, rep.stress_iv = args.stress_spot, args.stress_iv
        s2 = spot * (1 + args.stress_spot)
        for p in positions:
            t = max(p.leg.dte, 1) / 365.0
            now = bs_put(spot, p.leg.strike, t, p.leg.iv, args.r)
            shk = bs_put(s2, p.leg.strike, t, p.leg.iv * (1 + args.stress_iv), args.r)
            pnl = (now - shk) * 100 * p.qty * p.side
            rep.stress_rows.append({"p": p, "now": now, "shocked": shk, "pnl": pnl})
            rep.stress_total += pnl

    return rep


# ── 控制台格式 ────────────────────────────────────────────────────────

def format_console(rep: Report) -> str:
    L = "=" * 94
    out = ["\n" + L]
    mode_cn = "牛市看跌价差(定义风险)" if rep.mode == "spread" else "裸卖Put+尾部对冲"
    out.append(f" {rep.symbol} 卖方建仓 · 真实数据头寸表 [{mode_cn}]（CBOE {rep.asof}）")
    out.append(L)
    out.append(f" 账户净值 NLV : ${rep.nlv:,.0f}        {rep.symbol} 现价 : ${rep.spot:.2f}")
    out.append(L)
    out.append(f"{'腿':<5}{'方向':<7}{'到期':<13}{'DTE':<6}{'行权价':<9}{'|Δ|':<7}"
               f"{'IV%':<7}{'中间价':<8}{'手数':<6}{'现金流':<12}{'名义/风险':<13}{'OI':<7}")
    out.append("-" * 94)
    for p in rep.positions:
        side_cn = "卖Put" if p.side > 0 else "买Put"
        cash = p.side * p.leg.mid * 100 * p.qty
        cash_s = f"+${cash:,.0f}" if cash >= 0 else f"-${abs(cash):,.0f}"
        notional = p.leg.strike * 100 * p.qty
        out.append(f"{p.label:<5}{side_cn:<7}{p.leg.expiry:<13}{p.leg.dte:<6}"
                   f"{p.leg.strike:<9.1f}{p.leg.absdelta:<7.3f}{p.leg.iv*100:<7.1f}"
                   f"{p.leg.mid:<8.2f}{p.qty:<6}{cash_s:<12}${notional:<12,.0f}{p.leg.oi:<7.0f}")
    out.append("-" * 94)
    out.append(f" 单周期净权利金      : +${rep.total_credit:,.0f}  "
               f"({rep.total_credit/rep.nlv*100:.2f}% / 周期)")
    out.append(f" 短腿名义敞口        : ${rep.total_notional:,.0f}  "
               f"({rep.total_notional/rep.nlv:.2f}× NLV, 上限 {rep.max_notional_mult:.1f}×)")
    if rep.risk_is_exact:
        out.append(f" 最大风险(确定,保证金): ${rep.max_risk:,.0f}  "
                   f"({rep.max_risk/rep.nlv*100:.1f}% NLV)  ※价差定义风险,精确")
    else:
        out.append(f" 估算初始保证金 IM   : ${rep.max_risk:,.0f}  "
                   f"({rep.max_risk/rep.nlv*100:.1f}% 利用率)  ※模型估算,非真实")
    out.append(f" 组合净 Delta        : {rep.net_delta:+,.0f} 股当量")
    out.append(f" 组合净 Theta        : ${rep.net_theta:+,.0f} / 天")
    out.append(f" 组合净 Vega         : ${rep.net_vega:+,.0f} / 每 1 个波动点")
    out.append(L)

    if rep.stress_rows:
        s2 = rep.spot * (1 + rep.stress_spot)
        out.append(f"\n 压力测试：{rep.symbol} {rep.stress_spot*100:+.0f}% , "
                   f"IV {rep.stress_iv*100:+.0f}%   (${rep.spot:.2f}→${s2:.2f})")
        out.append("-" * 94)
        out.append(f"{'腿':<6}{'行权价':<9}{'冲击前理论价':<14}{'冲击后理论价':<14}{'盈亏':<14}")
        for row in rep.stress_rows:
            out.append(f"{row['p'].label:<6}{row['p'].leg.strike:<9.1f}"
                       f"{row['now']:<14.2f}{row['shocked']:<14.2f}${row['pnl']:+,.0f}")
        out.append("-" * 94)
        out.append(f" 组合净 MtM 盈亏     : ${rep.stress_total:+,.0f}  "
                   f"({rep.stress_total/rep.nlv*100:+.2f}% NLV)")
        out.append(L)

    out.append("\n 注：希腊字母/价格为 CBOE 真实延迟报价；naked 保证金为 BS 模型估算，"
               "spread 最大风险为精确值。\n     待 IB 账户开通后用 tools/qcom_options.py 的 "
               "whatIf 取真实保证金复核。\n")
    return "\n".join(out)


# ── Telegram 文案 ─────────────────────────────────────────────────────

def format_telegram(rep: Report) -> str:
    mode_cn = "牛市看跌价差" if rep.mode == "spread" else "裸卖Put+尾部对冲"
    lines = []
    lines.append(f"📈 <b>{rep.symbol} 卖方头寸建议</b> [{mode_cn}]")
    lines.append(f"现价 ${rep.spot:.2f} · NLV ${rep.nlv:,.0f} · CBOE {rep.asof}")
    lines.append("")
    rows = ["腿  方向   到期   行权 |Δ|  IV%  中价 手"]
    for p in rep.positions:
        sd = "卖" if p.side > 0 else "买"
        rows.append(f"{p.label:<3}{sd}P {p.leg.expiry[5:]} {p.leg.strike:>5.0f} "
                    f"{p.leg.absdelta:.2f} {p.leg.iv*100:>4.0f} {p.leg.mid:>5.2f} {p.qty}")
    lines.append("<pre>" + "\n".join(rows) + "</pre>")
    lines.append(f"💰 净权利金: <b>+${rep.total_credit:,.0f}</b> ({rep.total_credit/rep.nlv*100:.2f}%/周期)")
    lines.append(f"📊 名义敞口: ${rep.total_notional:,.0f} ({rep.total_notional/rep.nlv:.2f}×)")
    if rep.risk_is_exact:
        lines.append(f"🛡 最大风险(精确): ${rep.max_risk:,.0f} ({rep.max_risk/rep.nlv*100:.1f}%)")
    else:
        lines.append(f"🛡 估算保证金: ${rep.max_risk:,.0f} ({rep.max_risk/rep.nlv*100:.1f}%)")
    lines.append(f"Δ {rep.net_delta:+,.0f} | Θ ${rep.net_theta:+,.0f}/天 | V ${rep.net_vega:+,.0f}/点")
    if rep.stress_rows:
        lines.append(f"⚠️ 压力 {rep.stress_spot*100:+.0f}%/IV{rep.stress_iv*100:+.0f}%: "
                     f"<b>${rep.stress_total:+,.0f}</b> ({rep.stress_total/rep.nlv*100:+.1f}% NLV)")
    return "\n".join(lines)


# ── Telegram 推送（优先复用 notifier，回退直连 Bot API） ──────────────

def push_telegram(text: str) -> bool:
    # 路线1：复用项目 notifier（同时会触发邮箱等已注册通道）
    try:
        import asyncio
        import config  # noqa
        import notifier
        from hooks import emit, Event
        notifier.setup()
        asyncio.run(emit(Event.DAILY_REPORT, {"text": text}))
        print("已通过 notifier 推送到 Telegram（及其它已启用通道）。")
        return True
    except Exception as e:
        print(f"  notifier 通道不可用({e.__class__.__name__})，回退直连 Bot API ...")

    # 路线2：直连 Telegram Bot API（仅需 env 里的 token / chat_id）
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("  未配置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，跳过推送。")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = json.loads(resp.read().decode()).get("ok")
        print("已通过 Bot API 推送到 Telegram。" if ok else "Telegram 返回非 ok。")
        return bool(ok)
    except Exception as e:
        print(f"  Telegram 推送失败：{e}")
        return False


# ── 主流程 ────────────────────────────────────────────────────────────

def run(args):
    sym = args.symbol.upper()
    print(f"拉取 CBOE 延迟报价：{sym} ...")
    data = fetch_cboe(sym)
    spot, asof, puts = parse_puts(data, sym)
    if spot <= 0 or not puts:
        print("未取到有效数据（标的代码或数据源问题）。")
        return

    chosen = pick_expiries(puts, args.dtes)
    structures, hedge_leg = build_structures(args, spot, puts, chosen)
    if not structures:
        print("未能构建任何结构（检查 DTE / Delta / 价差宽度参数）。")
        return
    positions, total_units = size_positions(args, structures, hedge_leg)
    rep = compute_report(args, spot, asof, puts, positions, structures, total_units)

    print(format_console(rep))
    if args.notify:
        push_telegram(format_telegram(rep))


def parse_args():
    p = argparse.ArgumentParser(description="期权卖方真实数据拉取器（CBOE 公开源，无需 IB）")
    p.add_argument("--symbol", default="QCOM")
    p.add_argument("--nlv", type=float, default=200000)
    p.add_argument("--mode", choices=["naked", "spread"], default="naked")
    p.add_argument("--spread-width", type=float, default=20.0,
                   help="spread 模式下保护腿低于短腿的行权价点数")
    p.add_argument("--dtes", type=int, nargs="+", default=[35, 49])
    p.add_argument("--short-deltas", type=float, nargs="+", default=[0.18, 0.16])
    p.add_argument("--hedge-delta", type=float, default=0.06)
    p.add_argument("--target-im", type=float, default=0.25)
    p.add_argument("--max-notional", type=float, default=1.5)
    p.add_argument("--r", type=float, default=0.045)
    p.add_argument("--stress", action="store_true", help="开启压力测试")
    p.add_argument("--stress-spot", type=float, default=-0.20)
    p.add_argument("--stress-iv", type=float, default=0.50)
    p.add_argument("--notify", action="store_true", help="把报告推送到 Telegram")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if len(args.short_deltas) < len(args.dtes):
        args.short_deltas += [args.short_deltas[-1]] * (len(args.dtes) - len(args.short_deltas))
    run(args)
