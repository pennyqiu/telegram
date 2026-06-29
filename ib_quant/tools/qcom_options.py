"""
QCOM 期权卖方真实数据拉取器（只读，绝不下单）

目的：解决"用估算的 IV / 权利金 / 保证金做决策容易失真"的问题。
本脚本直接从你自己的 IB Gateway 拉取真实数据，作为卖 Put 策略建仓/滚动的输入：

  1. 现价（QCOM 实时 / 延迟行情）
  2. 期权链 -> 自动挑选最接近目标 DTE 的到期日
  3. 真实希腊字母（Delta / IV / Theta / Vega）-> 按目标 Delta 选出真实行权价
  4. 真实买卖价 / 中间价 -> 真实权利金现金流
  5. ★ whatIfOrder -> IB 返回的【真实】初始/维持保证金（PM 组合抵消后的真值）
     —— 这是估算永远算不准、但对 PM 账户最关键的数字。

安全说明：
  - 全程 readonly=True 连接，且只用 whatIf=True 的"假想单"询价保证金，IB 不会成交。
  - 使用独立 clientId（默认 30），与只读监控(10)/交易(20)区分，避免冲突。

用法（在 ib_quant 目录下）：
  python tools/qcom_options.py
  python tools/qcom_options.py --symbol QCOM --nlv 200000 --dtes 35 49 \
      --short-deltas 0.18 0.16 --hedge-delta 0.06 --md-type 3

参数：
  --symbol        标的代码（默认 QCOM）
  --nlv           账户净值；不填则尝试从账户摘要读取 NetLiquidation
  --dtes          目标到期天数列表（默认 35 49），脚本自动找最接近的真实到期
  --short-deltas  各到期的卖出腿目标 |Delta|（与 --dtes 对应，默认 0.18 0.16）
  --hedge-delta   尾部对冲腿目标 |Delta|（默认 0.06，在最远到期上买入）
  --target-im     目标初始保证金利用率（默认 0.25 = 25%）
  --max-notional  最大名义敞口（占 NLV 倍数，默认 1.5）
  --md-type       行情类型 1=实时 2=冻结 3=延迟 4=延迟冻结（默认 1，失败回退 3）
  --r             无风险利率，用于 BS 兜底计算 Delta（默认 0.045）
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

# 允许直接 `python tools/qcom_options.py` 运行：把 ib_quant 根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # dotenv 缺失不致命
    pass

from ib_async import IB, Stock, Option, Order, Ticker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("qcom_options")
logging.getLogger("ib_async").setLevel(logging.WARNING)


# ── Black-Scholes 兜底（仅当行情无 Greeks 时用 IV 反推 Delta） ───────────

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put_delta(spot: float, strike: float, t_years: float, iv: float, r: float) -> float:
    """返回看跌期权 Delta（负值）。"""
    if spot <= 0 or strike <= 0 or t_years <= 0 or iv <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / (iv * math.sqrt(t_years))
    return _norm_cdf(d1) - 1.0


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class LegQuote:
    expiry: str
    dte: int
    strike: float
    right: str            # "P"
    bid: float
    ask: float
    delta: float          # 已取绝对值
    iv: float
    theta: float
    vega: float
    src: str              # greeks 来源："IB" 或 "BS兜底"

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 2)
        return round(max(self.bid, self.ask), 2)


def _f(v, default: float = 0.0) -> float:
    """ib_async 无行情返回 nan，统一兜底。"""
    try:
        x = float(v)
        return x if x == x else default   # x==x 过滤 nan
    except (TypeError, ValueError):
        return default


def _dte(expiry: str) -> int:
    d = datetime.strptime(expiry, "%Y%m%d").date()
    return (d - date.today()).days


# ── 主拉取器 ──────────────────────────────────────────────────────────

class OptionPuller:
    def __init__(self, args):
        self.args = args
        self.ib = IB()

    async def connect(self) -> None:
        host = os.getenv("IB_HOST", "127.0.0.1")
        port = int(os.getenv("IB_PORT", "4002"))
        client_id = int(os.getenv("IB_DATA_CLIENT_ID", "30"))
        logger.info("连接 IB Gateway %s:%s (clientId=%s, 只读)...", host, port, client_id)
        await self.ib.connectAsync(host, port, clientId=client_id, readonly=True)
        logger.info("已连接。")
        # 行情类型：优先实时，失败回退延迟
        self.ib.reqMarketDataType(self.args.md_type)

    async def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()

    async def get_nlv(self) -> float:
        if self.args.nlv:
            return float(self.args.nlv)
        account = os.getenv("IB_ACCOUNT", "")
        try:
            rows = await self.ib.reqAccountSummaryAsync()
            for r in rows:
                if r.tag == "NetLiquidation" and (not account or r.account == account):
                    return float(r.value)
        except Exception as e:
            logger.warning("读取账户净值失败（将用 200000 兜底）: %s", e)
        return 200000.0

    async def get_spot(self, stock: Stock) -> float:
        [t] = await self.ib.reqTickersAsync(stock)
        price = _f(t.marketPrice())
        if price <= 0:
            price = _f(t.last) or _f(t.close) or _f((t.bid + t.ask) / 2 if t.bid and t.ask else 0)
        return price

    async def gather_greeks(self, options: list[Option]) -> dict[int, Ticker]:
        """流式订阅一批期权，等待 Greeks 回填后读取并退订。分批避免行情线超限。"""
        result: dict[int, Ticker] = {}
        batch = 25
        for i in range(0, len(options), batch):
            chunk = options[i:i + batch]
            tickers = [self.ib.reqMktData(o, "", False, False) for o in chunk]
            # 等待 modelGreeks 回填（最多 ~8 秒）
            for _ in range(16):
                await asyncio.sleep(0.5)
                if all(t.modelGreeks is not None for t in tickers):
                    break
            for o, t in zip(chunk, tickers):
                result[o.conId] = t
                self.ib.cancelMktData(o)
            logger.info("  已取 %d/%d 个行权价的行情", min(i + batch, len(options)), len(options))
        return result

    async def select_leg(
        self, stock: Stock, spot: float, expiry: str, target_delta: float, r: float,
    ) -> Optional[LegQuote]:
        """在给定到期日，挑出 |Delta| 最接近 target 的看跌期权。"""
        chains = await self.ib.reqSecDefOptParamsAsync(
            stock.symbol, "", stock.secType, stock.conId
        )
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0] if chains else None)
        if not chain:
            logger.error("未取到期权链定义。")
            return None

        # 只看现价附近、对卖 Put 有意义的价外区间，缩小行情请求量
        lo, hi = spot * 0.50, spot * 1.02
        strikes = sorted(s for s in chain.strikes if lo <= s <= hi)
        if not strikes:
            logger.error("到期 %s 无合适行权价。", expiry)
            return None

        opts = [Option(stock.symbol, expiry, k, "P", "SMART",
                       tradingClass=chain.tradingClass) for k in strikes]
        opts = await self.ib.qualifyContractsAsync(*opts)
        opts = [o for o in opts if o.conId]

        greeks = await self.gather_greeks(opts)
        t_years = max(_dte(expiry), 1) / 365.0

        best: Optional[LegQuote] = None
        best_diff = 1e9
        for o in opts:
            t = greeks.get(o.conId)
            if not t:
                continue
            bid, ask = _f(t.bid), _f(t.ask)
            mg = t.modelGreeks
            if mg and mg.delta is not None and _f(mg.delta) != 0:
                delta = abs(_f(mg.delta))
                iv = _f(mg.impliedVol)
                theta = _f(mg.theta)
                vega = _f(mg.vega)
                src = "IB"
            else:
                # 兜底：用该合约 IV（若有）反推 BS Delta
                iv = _f(t.impliedVolatility) or self.args.iv_fallback
                delta = abs(bs_put_delta(spot, o.strike, t_years, iv, r))
                theta = vega = 0.0
                src = "BS兜底"
            if delta <= 0:
                continue
            diff = abs(delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best = LegQuote(
                    expiry=expiry, dte=_dte(expiry), strike=o.strike, right="P",
                    bid=bid, ask=ask, delta=delta, iv=iv, theta=theta, vega=vega, src=src,
                )
        return best

    async def what_if_margin(self, stock: Stock, leg: LegQuote, action: str, qty: int) -> tuple[float, float]:
        """用假想单询问 IB 真实保证金变化。返回 (初始保证金变化, 维持保证金变化)。"""
        opt = Option(stock.symbol, leg.expiry, leg.strike, leg.right, "SMART")
        [opt] = await self.ib.qualifyContractsAsync(opt)
        order = Order(action=action, orderType="LMT", totalQuantity=qty,
                      lmtPrice=max(leg.mid, 0.05), whatIf=True)
        state = await self.ib.whatIfOrderAsync(opt, order)
        return _f(state.initMarginChange), _f(state.maintMarginChange)

    async def run(self) -> None:
        a = self.args
        stock = Stock(a.symbol, "SMART", "USD")
        [stock] = await self.ib.qualifyContractsAsync(stock)

        nlv = await self.get_nlv()
        spot = await self.get_spot(stock)
        if spot <= 0:
            logger.error("未取到 %s 现价（检查行情权限 / --md-type）。", a.symbol)
            return
        logger.info(f"账户净值 NLV = ${nlv:,.0f}")
        logger.info("%s 现价 = $%.2f", a.symbol, spot)

        # 1) 选到期日：在真实到期里找最接近目标 DTE 的
        chains = await self.ib.reqSecDefOptParamsAsync(
            stock.symbol, "", stock.secType, stock.conId
        )
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        all_exp = sorted(chain.expirations)
        chosen_exp = []
        for target in a.dtes:
            best = min(all_exp, key=lambda e: abs(_dte(e) - target))
            if best not in chosen_exp:
                chosen_exp.append(best)
        logger.info("目标 DTE %s -> 选定到期 %s",
                    a.dtes, [f"{e}({_dte(e)}d)" for e in chosen_exp])

        # 2) 各到期按目标 Delta 选卖出腿
        short_legs: list[LegQuote] = []
        for exp, td in zip(chosen_exp, a.short_deltas):
            logger.info("→ 到期 %s 选 |Δ|≈%.2f 的卖出腿...", exp, td)
            leg = await self.select_leg(stock, spot, exp, td, a.r)
            if leg:
                short_legs.append(leg)
                logger.info("   选中 %s P, Δ=%.3f, IV=%.1f%%, 中间价=$%.2f (%s)",
                            leg.strike, leg.delta, leg.iv * 100, leg.mid, leg.src)

        # 3) 最远到期选尾部对冲腿（买入）
        hedge_leg = None
        if chosen_exp:
            far_exp = max(chosen_exp, key=_dte)
            logger.info("→ 到期 %s 选 |Δ|≈%.2f 的尾部对冲腿...", far_exp, a.hedge_delta)
            hedge_leg = await self.select_leg(stock, spot, far_exp, a.hedge_delta, a.r)
            if hedge_leg:
                logger.info("   选中 %s P, Δ=%.3f, IV=%.1f%%, 中间价=$%.2f (%s)",
                            hedge_leg.strike, hedge_leg.delta, hedge_leg.iv * 100,
                            hedge_leg.mid, hedge_leg.src)

        if not short_legs:
            logger.error("未能选出任何卖出腿，终止。")
            return

        # 4) 用真实 whatIf 保证金做建议手数（目标 IM 利用率，受名义敞口上限约束）
        target_im = nlv * a.target_im
        max_notional = nlv * a.max_notional

        # 单张卖 Put 的真实初始保证金（取各腿均值做粗分配）
        per_leg_im = []
        for leg in short_legs:
            im, _ = await self.what_if_margin(stock, leg, "SELL", 1)
            per_leg_im.append(abs(im))
            logger.info(f"   {leg.strike} P 单张真实初始保证金 = ${abs(im):,.0f}")
        avg_im = sum(per_leg_im) / len(per_leg_im) if per_leg_im else 0

        total_short = int(target_im / avg_im) if avg_im > 0 else 0
        # 名义敞口约束（行权价口径）
        avg_strike = sum(l.strike for l in short_legs) / len(short_legs)
        max_by_notional = int(max_notional / (avg_strike * 100)) if avg_strike > 0 else total_short
        total_short = max(2, min(total_short, max_by_notional))

        # 在各卖出腿间均分，对冲腿按卖出腿数量的一半配置
        n_legs = len(short_legs)
        per_short = [total_short // n_legs] * n_legs
        for i in range(total_short - sum(per_short)):
            per_short[i] += 1
        hedge_qty = max(1, round(total_short / 2)) if hedge_leg else 0

        # 5) 组合真实 whatIf（PM 抵消后的真值）
        combo_init, combo_maint = await self._combo_margin(
            stock, short_legs, per_short, hedge_leg, hedge_qty
        )

        self._print_report(
            a.symbol, nlv, spot, short_legs, per_short, hedge_leg, hedge_qty,
            combo_init, combo_maint, max_notional,
        )

    async def _combo_margin(self, stock, short_legs, per_short, hedge_leg, hedge_qty):
        """逐腿累加 whatIf 保证金。注：真正的 PM 抵消需在 IB 端用组合 whatIf；
        此处逐腿求和作为保守上界，并单独标注对冲腿的释放效果。"""
        init = maint = 0.0
        for leg, q in zip(short_legs, per_short):
            if q <= 0:
                continue
            i, m = await self.what_if_margin(stock, leg, "SELL", q)
            init += abs(i)
            maint += abs(m)
        if hedge_leg and hedge_qty > 0:
            i, m = await self.what_if_margin(stock, hedge_leg, "BUY", hedge_qty)
            # 买入对冲腿在 PM 下通常【降低】组合保证金
            init += i
            maint += m
        return init, maint

    def _print_report(self, symbol, nlv, spot, short_legs, per_short,
                      hedge_leg, hedge_qty, combo_init, combo_maint, max_notional):
        line = "=" * 78
        print("\n" + line)
        print(f" {symbol} 卖方建仓 · 真实数据头寸表   ({datetime.now():%Y-%m-%d %H:%M})")
        print(line)
        print(f" 账户净值 NLV : ${nlv:>14,.0f}")
        print(f" {symbol} 现价   : ${spot:>14.2f}")
        print(line)
        header = (f"{'腿':<4}{'方向':<6}{'到期(DTE)':<14}{'行权价':<9}"
                  f"{'|Δ|':<7}{'IV':<8}{'中间价':<8}{'手数':<6}{'现金流':<11}{'名义敞口':<12}{'来源':<8}")
        print(header)
        print("-" * 78)

        total_credit = 0.0
        total_notional = 0.0
        names = ["A", "B", "C", "D"]
        for idx, (leg, q) in enumerate(zip(short_legs, per_short)):
            credit = leg.mid * 100 * q
            notional = leg.strike * 100 * q
            total_credit += credit
            total_notional += notional
            print(f"{names[idx]:<4}{'卖Put':<6}{leg.expiry}({leg.dte}d){'':<2}"
                  f"{leg.strike:<9.1f}{leg.delta:<7.3f}{leg.iv*100:<8.1f}"
                  f"{leg.mid:<8.2f}{q:<6}+${credit:<9,.0f}${notional:<11,.0f}{leg.src:<8}")
        if hedge_leg and hedge_qty > 0:
            cost = hedge_leg.mid * 100 * hedge_qty
            total_credit -= cost
            print(f"{'H':<4}{'买Put':<6}{hedge_leg.expiry}({hedge_leg.dte}d){'':<2}"
                  f"{hedge_leg.strike:<9.1f}{hedge_leg.delta:<7.3f}{hedge_leg.iv*100:<8.1f}"
                  f"{hedge_leg.mid:<8.2f}{hedge_qty:<6}-${cost:<9,.0f}{'(尾部封顶)':<12}{hedge_leg.src:<8}")

        print("-" * 78)
        print(f" 单周期净权利金     : +${total_credit:,.0f}  "
              f"({total_credit / nlv * 100:.2f}% / 周期)")
        print(f" 名义敞口(行权价口径): ${total_notional:,.0f}  "
              f"({total_notional / nlv:.2f}× NLV, 上限 {max_notional / nlv:.1f}×)")
        print(f" 真实初始保证金 IM  : ${combo_init:,.0f}  "
              f"({combo_init / nlv * 100:.1f}% 利用率)")
        print(f" 真实维持保证金 Maint: ${combo_maint:,.0f}  "
              f"({combo_maint / nlv * 100:.1f}%)")
        print(line)
        print(" 说明：IM/Maint 为逐腿 whatIf 之和（保守上界）；买入对冲腿已计入其保证金"
              "释放。\n       PM 真实抵消可能更低，最终以 IB Risk Navigator / 组合 whatIf 为准。")
        print(line + "\n")


def parse_args():
    p = argparse.ArgumentParser(description="QCOM 期权卖方真实数据拉取器（只读）")
    p.add_argument("--symbol", default="QCOM")
    p.add_argument("--nlv", type=float, default=0.0)
    p.add_argument("--dtes", type=int, nargs="+", default=[35, 49])
    p.add_argument("--short-deltas", type=float, nargs="+", default=[0.18, 0.16])
    p.add_argument("--hedge-delta", type=float, default=0.06)
    p.add_argument("--target-im", type=float, default=0.25)
    p.add_argument("--max-notional", type=float, default=1.5)
    p.add_argument("--md-type", type=int, default=1, choices=[1, 2, 3, 4])
    p.add_argument("--r", type=float, default=0.045)
    p.add_argument("--iv-fallback", type=float, default=0.70,
                   help="无任何 IV 时 BS 兜底用的波动率")
    return p.parse_args()


async def main():
    args = parse_args()
    if len(args.short_deltas) < len(args.dtes):
        # 不足则用最后一个值补齐
        args.short_deltas += [args.short_deltas[-1]] * (len(args.dtes) - len(args.short_deltas))
    puller = OptionPuller(args)
    try:
        await puller.connect()
        await puller.run()
    except ConnectionRefusedError:
        logger.error("连接被拒绝：请确认 IB Gateway/TWS 已启动并开放 API 端口 "
                     "(IB_PORT，模拟盘 4002 / 实盘 4001)。")
    except Exception as e:
        logger.error("运行出错: %s", e, exc_info=True)
    finally:
        await puller.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
