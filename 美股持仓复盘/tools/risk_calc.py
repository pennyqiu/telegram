#!/usr/bin/env python3
"""期权风险计算器：从标记价反解隐含波动率，算 Delta 调整敞口、压力测试与保证金追缴临界点。

为什么需要它：名义金额会严重误判风险。一张深虚值 Put 和一张实值 Put 名义金额可能相同，
实际风险差好几倍。Delta 调整后的敞口才是「等价于持有多少正股」的真实数字。

压力测试必须同时放大波动率。崩盘时 Put 亏钱有两个来源：标的下跌（Delta）和恐慌
（Vega）。只算 Delta 会低估一半以上的亏损，这是卖方最常见的致命误判。

用法：改下方 POSITIONS 与 PORTFOLIO 后 python3 risk_calc.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

RISK_FREE = 0.043

# 可承受的最大组合回撤。这是全部期权额度的源头，改这一个数字会改变下面所有阈值。
# 2026-08-01 由本人确认为 40%。
TOLERANCE = 0.40


@dataclass
class Put:
    """一张卖出的看跌期权。qty 为正数，代表卖出张数。"""

    symbol: str
    kind: str          # 收租型 / 接货型 / 卫星投机
    strike: float
    spot: float
    days: int
    qty: int
    mark: float        # 当前每股标记价
    open_premium: float
    is_index: bool

    iv: float = field(default=0.0, init=False)

    @property
    def notional(self) -> float:
        return self.strike * 100 * self.qty


@dataclass
class Portfolio:
    equity: float          # 股票市值
    cash: float
    net_liq: float
    beta: float            # 股票组合相对标普500 的贝塔


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_put(spot: float, strike: float, t: float, vol: float, r: float = RISK_FREE) -> float:
    if t <= 0 or vol <= 0:
        return max(strike - spot, 0.0)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return strike * math.exp(-r * t) * norm_cdf(-d2) - spot * norm_cdf(-d1)


def bs_put_delta(spot: float, strike: float, t: float, vol: float, r: float = RISK_FREE) -> float:
    if t <= 0 or vol <= 0:
        return -1.0 if spot < strike else 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    return norm_cdf(d1) - 1.0


def implied_vol(price: float, spot: float, strike: float, t: float) -> float:
    """二分法反解隐含波动率。"""
    lo, hi = 0.01, 4.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if bs_put(spot, strike, t, mid) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def find_strike_for_delta(spot: float, t: float, vol: float, target_abs_delta: float) -> float:
    """二分找出 |Delta| = target 的行权价（虚值看跌，故在现价下方）。"""
    lo, hi = spot * 0.4, spot
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if abs(bs_put_delta(spot, mid, t, vol)) > target_abs_delta:
            hi = mid  # |delta| 太大，行权价离现价太近，往下调
        else:
            lo = mid
    return 0.5 * (lo + hi)


def regt_margin(spot: float, strike: float, mark: float, qty: int) -> float:
    """Reg-T 裸卖 Put 保证金：期权市值 + max(标的20% − 虚值额, 行权价10%)。"""
    otm = max(spot - strike, 0.0)
    req = max(0.20 * spot - otm, 0.10 * strike)
    return (mark + req) * 100 * qty


# 波动率在崩盘中的放大路径。指数 IV 的扩张远比个股剧烈，因为恐慌买盘集中在指数保护上。
def stressed_vol(base_iv: float, drop: float, is_index: bool) -> float:
    if is_index:
        return max(base_iv, 0.15 + 1.20 * drop)
    return max(base_iv, base_iv + 0.90 * drop)


# ---------------------------------------------------------------- 数据（2026-08-01 快照）

PORTFOLIO = Portfolio(equity=433_602, cash=37.06, net_liq=427_418, beta=1.18)

POSITIONS = [
    Put("SPYM", "收租型", 83, 87.65, 48, 5, 0.582, 0.94, True),
    Put("SPYM", "收租型", 84, 87.65, 48, 5, 0.682, 1.09, True),
    Put("SPYM", "收租型", 86, 87.65, 48, 4, 1.041, 1.34, True),
    Put("QQQ", "收租型", 620, 680.0, 48, 2, 5.72, 10.11, True),
    Put("QQQ", "收租型", 630, 680.0, 76, 1, 11.05, 11.29, True),
    Put("QCOM", "接货型", 155, 147.5, 48, 1, 15.99, 7.94, False),
    Put("DRAM", "卫星投机", 55, 49.80, 20, 1, 7.641, 4.24, False),
]


def main() -> None:
    for p in POSITIONS:
        p.iv = implied_vol(p.mark, p.spot, p.strike, p.days / 365.0)

    print("=" * 78)
    print("一、逐张明细：名义金额 vs Delta 调整后的真实敞口")
    print("=" * 78)
    print(f"{'标的':<7}{'行权价':>7}{'类型':>7}{'张':>4}{'隐含波动':>9}{'Delta':>8}"
          f"{'名义金额':>11}{'Delta敞口':>11}")
    print("-" * 78)

    total_notional = total_delta_exp = 0.0
    idx_notional = idx_delta_exp = 0.0
    for p in POSITIONS:
        d = bs_put_delta(p.spot, p.strike, p.days / 365.0, p.iv)
        delta_exp = abs(d) * p.spot * 100 * p.qty
        total_notional += p.notional
        total_delta_exp += delta_exp
        if p.is_index:
            idx_notional += p.notional
            idx_delta_exp += delta_exp
        print(f"{p.symbol:<7}{p.strike:>7.0f}{p.kind:>7}{p.qty:>4}"
              f"{p.iv * 100:>8.1f}%{d:>8.2f}{p.notional:>11,.0f}{delta_exp:>11,.0f}")

    print("-" * 78)
    nl = PORTFOLIO.net_liq
    print(f"{'合计':<7}{'':<18}{total_notional:>36,.0f}{total_delta_exp:>11,.0f}")
    print(f"{'占净值':<7}{'':<18}{total_notional / nl * 100:>35.1f}%{total_delta_exp / nl * 100:>10.1f}%")
    print(f"\n其中指数类：名义 {idx_notional:,.0f}（{idx_notional / nl * 100:.1f}%）"
          f"　Delta 敞口 {idx_delta_exp:,.0f}（{idx_delta_exp / nl * 100:.1f}%）")
    print(f"\n股票 {PORTFOLIO.equity:,.0f} + 期权 Delta {total_delta_exp:,.0f}"
          f" = 总多头敞口 {PORTFOLIO.equity + total_delta_exp:,.0f}"
          f"（净值的 {(PORTFOLIO.equity + total_delta_exp) / nl * 100:.0f}%）")

    print()
    print("=" * 78)
    print("二、压力测试：标普500 下跌时的净值与保证金（含波动率放大）")
    print("=" * 78)
    print(f"{'跌幅':>5}{'股票亏损':>11}{'期权亏损':>11}{'净值':>11}{'回撤':>8}"
          f"{'保证金需求':>12}{'占净值':>8}{'状态':>10}")
    print("-" * 78)

    base_margin = sum(regt_margin(p.spot, p.strike, p.mark, p.qty) for p in POSITIONS)
    print(f"{'0%':>5}{0:>11,.0f}{0:>11,.0f}{nl:>11,.0f}{0.0:>7.1f}%"
          f"{base_margin:>12,.0f}{base_margin / nl * 100:>7.1f}%{'—':>10}")

    for drop in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
        equity_loss = PORTFOLIO.equity * drop * PORTFOLIO.beta
        opt_loss = 0.0
        margin = 0.0
        for p in POSITIONS:
            # 个股按贝塔放大跌幅，指数按原跌幅
            move = drop * (1.0 if p.is_index else 1.25)
            new_spot = p.spot * (1.0 - move)
            new_t = max(p.days / 365.0, 1 / 365.0)
            new_vol = stressed_vol(p.iv, drop, p.is_index)
            new_price = bs_put(new_spot, p.strike, new_t, new_vol)
            opt_loss += (new_price - p.mark) * 100 * p.qty
            margin += regt_margin(new_spot, p.strike, new_price, p.qty)

        new_nl = nl - equity_loss - opt_loss
        drawdown = (nl - new_nl) / nl * 100
        ratio = margin / new_nl * 100 if new_nl > 0 else 999
        # IB 对集中科技持仓的实际要求通常高于 Reg-T；超过净值 100% 即为强制平仓区
        if ratio >= 100:
            status = "强平"
        elif ratio >= 50:
            status = "追缴"
        elif ratio >= 30:
            status = "警戒"
        else:
            status = "尚可"
        print(f"{drop * 100:>4.0f}%{equity_loss:>11,.0f}{opt_loss:>11,.0f}{new_nl:>11,.0f}"
              f"{drawdown:>7.1f}%{margin:>12,.0f}{ratio:>7.1f}%{status:>10}")

    print()
    print("=" * 78)
    print(f"三、回撤预算分解（可承受上限 {TOLERANCE * 100:.0f}%）")
    print("=" * 78)
    print("关键在于「参照情景」——同样的预算，在不同的假想熊市里给出的额度天差地别。")
    print("股票部分的亏损无法用期权额度调节，只能靠降贝塔或加现金。")
    print("先扣掉股票消耗，剩下的才是期权能用的空间。\n")
    print(f"{'参照情景':>10}{'现金垫':>8}{'股票消耗':>10}{'剩余预算':>10}"
          f"{'期权名义上限':>14}{'占净值':>9}")
    print("-" * 78)

    for drop in (0.20, 0.25, 0.30, 0.40):
        # 该情景下，每 1 元名义敞口的亏损（用与实际持仓相仿的 -6% 虚值指数 Put 作探针）
        probe_iv = 0.17
        lpn = (bs_put(94.0 * (1 - drop), 94.0, 45 / 365.0, stressed_vol(probe_iv, drop, True))
               - bs_put(94.0, 94.0, 45 / 365.0, probe_iv)) / 100.0
        for cash_pct in (0.0, 0.10, 0.20):
            stock_dd = (1 - cash_pct) * drop * PORTFOLIO.beta
            room = TOLERANCE - stock_dd
            if room <= 0:
                print(f"{drop * 100:>9.0f}%{cash_pct * 100:>7.0f}%{stock_dd * 100:>9.1f}%"
                      f"{room * 100:>9.1f}%{'预算已耗尽':>14}{'0%':>9}")
            else:
                cap = room * nl / lpn
                print(f"{drop * 100:>9.0f}%{cash_pct * 100:>7.0f}%{stock_dd * 100:>9.1f}%"
                      f"{room * 100:>9.1f}%{cap:>14,.0f}{cap / nl * 100:>8.0f}%")
        print()

    breakeven = TOLERANCE / PORTFOLIO.beta
    print(f"⚠ 临界点：贝塔 {PORTFOLIO.beta}、零现金、零期权时，市场跌 "
          f"{breakeven * 100:.1f}% 就用尽 {TOLERANCE * 100:.0f}% 的预算。")
    print("  也就是说在更深的熊市里，光持有这个股票组合就已经超出容忍度，期权额度必须为零。")
    print("  历史参照：2022 标普 -25%，2020 年 3 月 -34%，2007-09 -57%，2000-02 -49%。")
    print("  且崩盘中贝塔会上升：2022 年标普 -25% 时纳指 -33%（1.32 倍），")
    print("  2000-02 标普 -49% 而纳指 -78%（1.6 倍）。1.18 是温和假设。")

    print()
    print("=" * 78)
    print("四、行动方案前后对照")
    print("=" * 78)
    print("方案：① 按 T2/T3 平掉 QCOM 155P 与 DRAM 55P（早已触发处理线）")
    print("      ② 平掉 SPYM 86P（Delta 0.32 最高）与 QQQ 620P（浮盈近止盈线且压在 9-18）")
    print("      ③ 卖出低信念仓位换现金（IQQ 与 QQQM 均保留，2026-08-01 本人决定）")
    print("      ④ 所得资金买入 SGOV\n")

    keep = [p for p in POSITIONS
            if not (p.symbol == "SPYM" and p.strike == 86)
            and not (p.symbol == "QQQ" and p.strike == 620)
            and p.symbol not in ("QCOM", "DRAM")]

    close_now = sum(p.mark * 100 * p.qty for p in POSITIONS if p not in keep)

    # 按信念由低到高排序的可变现来源。改这张表即可试算不同组合。
    SALES = [
        ("IBKR 碎股", 1_398, "碎股，非主动建仓"),
        ("DRAM 正股", 4_975, "playbook 第七节要求不长期持有"),
        ("TCEHY 腾讯ADR", 12_595, "粉单流动性差，且尚无标的档案（违反 F1）"),
        ("META", 27_690, "浮亏 -12.4%，可税务亏损收割；D010 待判断"),
    ]
    print("  变现来源（按信念由低到高，不触碰 MSFT/TSM/NVDA/GOOG/QQQM/IQQ/SPYM）：")
    running = PORTFOLIO.cash - close_now
    for name, amt, why in SALES:
        running += amt
        print(f"    + {name:<16}{amt:>8,.0f}　累计现金 {running:>8,.0f}"
              f"（{running / nl * 100:>4.1f}%）　{why}")
    print()

    proceeds = sum(a for _, a, _ in SALES)
    new_cash = proceeds - close_now + PORTFOLIO.cash
    new_equity = PORTFOLIO.equity - proceeds

    kept_notional = sum(p.notional for p in keep)
    kept_delta = sum(abs(bs_put_delta(p.spot, p.strike, p.days / 365.0, p.iv))
                     * p.spot * 100 * p.qty for p in keep)
    print(f"平掉 4 张期权花费 {close_now:,.0f}；变现合计 {proceeds:,.0f}")
    print(f"→ 股票 {new_equity:,.0f}　现金/SGOV {new_cash:,.0f}"
          f"（净值的 {new_cash / nl * 100:.1f}%）")
    print(f"→ 保留 {', '.join(f'{p.symbol} {p.strike:.0f}P×{p.qty}' for p in keep)}")
    print(f"→ 期权名义 {kept_notional:,.0f}（{kept_notional / nl * 100:.0f}%）"
          f"　Delta 敞口 {kept_delta:,.0f}（{kept_delta / nl * 100:.1f}%）")
    print(f"→ 总多头敞口 {new_equity + kept_delta:,.0f}"
          f"（{(new_equity + kept_delta) / nl * 100:.0f}%，原 119%）\n")

    print(f"{'跌幅':>6}{'原回撤':>9}{'新回撤':>9}{'预算内':>8}"
          f"{'原保证金':>10}{'新保证金':>10}{'现金能否平仓':>14}")
    print("-" * 78)
    for drop in (0.20, 0.25, 0.30, 0.40):
        old_loss = PORTFOLIO.equity * drop * PORTFOLIO.beta
        old_o = old_m = 0.0
        for p in POSITIONS:
            ns = p.spot * (1.0 - drop * (1.0 if p.is_index else 1.25))
            npx = bs_put(ns, p.strike, max(p.days / 365.0, 1 / 365.0),
                         stressed_vol(p.iv, drop, p.is_index))
            old_o += (npx - p.mark) * 100 * p.qty
            old_m += regt_margin(ns, p.strike, npx, p.qty)
        old_nl = nl - old_loss - old_o

        eq_loss = new_equity * drop * PORTFOLIO.beta
        o_loss = margin = close_cost = 0.0
        for p in keep:
            ns = p.spot * (1.0 - drop)
            npx = bs_put(ns, p.strike, max(p.days / 365.0, 1 / 365.0),
                         stressed_vol(p.iv, drop, p.is_index))
            o_loss += (npx - p.mark) * 100 * p.qty
            margin += regt_margin(ns, p.strike, npx, p.qty)
            close_cost += npx * 100 * p.qty
        new_nl = nl - eq_loss - o_loss
        new_dd = (nl - new_nl) / nl
        ok = "是" if new_cash >= close_cost else f"否（缺 {close_cost - new_cash:,.0f}）"
        within = "✓" if new_dd <= TOLERANCE else "✗"
        print(f"{drop * 100:>5.0f}%{(nl - old_nl) / nl * 100:>8.1f}%{new_dd * 100:>8.1f}%"
              f"{within:>7}{old_m / old_nl * 100:>9.1f}%{margin / new_nl * 100:>9.1f}%{ok:>16}")

    print()
    print("=" * 78)
    print("五、现金到底死不死：SGOV + 现金担保卖 put 引擎的收益")
    print("=" * 78)
    print("「留现金」不等于「钱躺着不动」。现金放 SGOV 拿无风险利率，同时作为卖 put 的抵押品，")
    print("再收一层权利金。两层叠加，才是留现金的真实机会成本。\n")
    print(f"假设：45 DTE 入场，0.20 Delta（约 80% 概率白收），21 DTE 或 50% 利润时平仓/滚动。")
    print(f"{'标的IV':>8}{'行权价/现价':>12}{'单周期权利金':>14}{'占抵押%':>10}"
          f"{'年化(仅put)':>13}{'+SGOV后':>10}")
    print("-" * 78)
    sgov = RISK_FREE
    t45 = 45 / 365.0
    for iv in (0.14, 0.18, 0.25, 0.35):
        strike = find_strike_for_delta(100.0, t45, iv, 0.20)
        prem = bs_put(100.0, strike, t45, iv)
        per_cycle = prem / strike
        # 一年约 10 个有效周期（持有约 24 天，含提前止盈滚动），平均实现约 60% 权利金
        annual = per_cycle * 10 * 0.60
        print(f"{iv * 100:>7.0f}%{strike:>11.1f}{prem:>14.2f}{per_cycle * 100:>9.2f}%"
              f"{annual * 100:>12.1f}%{(annual + sgov) * 100:>9.1f}%")
    print(f"\nSGOV 无风险利率按 {sgov * 100:.1f}%。年化为估算，随 IV 与实际执行差异很大，")
    print("低波动期可能只有 SGOV+2~3%，高波动期显著更高。要点：留现金的机会成本远小于「零收益」。")

    print()
    print("=" * 78)
    print("六、回撤响应阶梯（预先写死，不预测市场）")
    print("=" * 78)
    print("不猜底部，只对价格水平做机械反应。每跌一档，用现金担保 put 在「合理买入区间」建仓。")
    print("被行权 = 用你认可的价格买到货（是特性不是故障）；没被行权 = 白收权利金。\n")

    consolidated = 1_100_000  # 合并口径，其余账户数据补齐后更新
    deploy_budget = 0.25      # 投入弹药占合并净值比例（可调）
    solvency_reserve = 0.05   # 单独保护、不参与部署的偿付缓冲
    print(f"合并净值假设 {consolidated:,.0f}（待补齐）；部署弹药 {deploy_budget * 100:.0f}%"
          f" = {consolidated * deploy_budget:,.0f}；另留偿付缓冲 {solvency_reserve * 100:.0f}%（不动）\n")

    # 越跌越买：每档部署占「总弹药」的比例，故意在深处加大，但保留尾部
    ladder = [
        ("现价~-10%", 0.10, "各标的档案买区上沿，0.15Δ 现金担保 put，宁可不成交"),
        ("-10%~-20%", 0.20, "买区中枢，0.20~0.25Δ，开始接受被行权"),
        ("-20%~-30%", 0.30, "买区下沿，0.30Δ 或直接市价分批买入"),
        ("-30%~-40%", 0.25, "深度价值区，主动买入正股为主"),
        ("-40% 以下", 0.15, "尾部弹药，只在恐慌极值动用，永远保留"),
    ]
    print(f"{'市场档位':>12}{'部署占弹药%':>13}{'投入金额':>12}{'累计投入':>12}{'执行方式':>4}")
    print("-" * 78)
    cum = 0.0
    total = consolidated * deploy_budget
    for level, frac, how in ladder:
        amt = total * frac
        cum += amt
        print(f"{level:>12}{frac * 100:>11.0f}%{amt:>12,.0f}{cum:>12,.0f}   {how}")
    print(f"\n关键约束：偿付缓冲 {consolidated * solvency_reserve:,.0f} 独立于本阶梯，永不挪用——")
    print("否则一次下跌会同时（a）触发接货消耗弹药、（b）要求现金平掉存量 put，一块钱不能两用。")


if __name__ == "__main__":
    main()
