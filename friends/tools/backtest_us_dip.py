#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测 us-dip 阶梯买入策略的波动与收益（5/10/15/20 年）。

方法：
- 数据：QQQ 代表纳指100、SPY 代表标普500，取 Yahoo 复权收盘（含分红，近似总回报）。
- 阶梯（与 us_dip_watchlist.json 一致）：
    纳指100：跌 8%→买30%、跌15%→买40%、跌20%→买30%
    标普500：跌 6%→买30%、跌10%→买30%、跌15%→买20%、跌20%→买20%
- “回撤”= (现价 − 期内历史最高收盘) / 历史最高收盘。创新高则阶梯重新武装（下一轮回调可再买）。
- 两种口径对比（同为 100 单位资金）：
    A. 买入持有（Buy&Hold）：期初一次性全买，持有到期末。
    B. 阶梯买入（Ladder）：期初现金 100，按阶梯逐档买入；钱花完即满仓持有，未触发的钱留现金（0 利息，偏保守）。
- 指标：CAGR（年化收益）、年化波动率（日对数收益 σ×√252）、最大回撤、期末价值倍数、
        阶梯累计投入比例、触发档数。

⚠️ 方法学警告：本脚本的结论不可用于决策，四个已确认的缺陷会系统性歪曲结果。
   已由 backtest_dip_rolling.py（滚动+现金流感知）与 backtest_dip_sweep.py（参数曲面）替代。

   1) ATH 预热偏差：`ath = prices[0]` 把序列首日当历史最高。实测这一项就能让
      「阶梯 vs 全额立投」的中位超额差 2~3 个百分点（见 --ath-mode window 对照）。
      正确做法是用起点之前的真实最高收盘（point-in-time）。
   2) 现金按 0 利息：低估空等的机会成本。现金年化从 0% 提到 4%，
      阶梯的劣势会从 −4.96% 收窄到 −2.80%——即旧口径其实是**低估**了阶梯。
   3) re-arm 只认新高：长期水下时三档打完就断粮，而那正是最该继续买的时期。
      加「水下满 6 个月补一档」后，阶梯劣势从 −8.61% 改善到 −3.51%，
      这是原阶梯逻辑最大的单一缺陷。
   4) 单起点回测：从今天往回切 5/10/15/20 年只有一个起点，且必然包含美股大牛市。
      改成 187 个滚动起点后，结论完全变了（见下）。

   修正全部缺陷后的实测结论（SPY，2001-01~2026-08，187 个 10 年滚动窗口）：
     · 纯阶梯只在 3.7% 的起点跑赢「全额立投」，中位落后 3.91%
     · 加权买入成本并没有更低：比立刻全买还贵 1.02%（P10 情形贵 7.49%）
     · 43.3% 的起点开局就已跌破最深一档 → 阶梯当天全投，等于没择时
   → 对「新钱持续流入 + 本金永不卖出」的人，阶梯是负价值的。别用它决定要不要投，
     可以用它决定「已经打算投的钱，今天多投一点还是少投一点」。

仅供研究，非投资建议。
"""
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timedelta

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bt_cache")

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

LADDERS = {
    "纳指100": [(8, 30), (15, 40), (20, 30)],
    "标普500": [(6, 30), (10, 30), (15, 20), (20, 20)],
}
PROXY = {"纳指100": "QQQ", "标普500": "SPY"}
HORIZONS = [5, 10, 15, 20]


def _fetch_yfinance(sym):
    """VPS 上优先用 yfinance（更稳，不易 429）。"""
    import yfinance as yf
    df = yf.download(sym, period="max", interval="1d",
                     auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError("yfinance 空数据")
    col = df["Close"]
    out = []
    for idx, val in col.items():
        try:
            p = float(val)
        except Exception:
            p = float(val.iloc[0]) if hasattr(val, "iloc") else float("nan")
        if p == p:  # not NaN
            out.append((idx.date(), p))
    out.sort(key=lambda x: x[0])
    return out


def fetch(sym, rng="25y"):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"{sym}_{rng}.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 6 * 3600:
        with open(cache) as f:
            raw = json.load(f)
        return [(datetime.strptime(d, "%Y-%m-%d").date(), p) for d, p in raw]

    # 优先 yfinance（VPS 环境）
    try:
        out = _fetch_yfinance(sym)
        with open(cache, "w") as f:
            json.dump([[d.strftime("%Y-%m-%d"), p] for d, p in out], f)
        return out
    except Exception:
        pass

    last_err = None
    for attempt in range(6):
        host = "query1" if attempt % 2 == 0 else "query2"
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30)
            j = json.load(r)
            res = j["chart"]["result"][0]
            ts = res["timestamp"]
            adj = res["indicators"]["adjclose"][0]["adjclose"]
            out = []
            for t, p in zip(ts, adj):
                if p is None:
                    continue
                out.append((datetime.utcfromtimestamp(t).date(), float(p)))
            out.sort(key=lambda x: x[0])
            with open(cache, "w") as f:
                json.dump([[d.strftime("%Y-%m-%d"), p] for d, p in out], f)
            return out
        except Exception as e:
            last_err = e
            time.sleep(2.5 * (attempt + 1))
    raise RuntimeError(f"拉取 {sym} 失败：{last_err}")


def slice_years(series, years):
    end = series[-1][0]
    start = end - timedelta(days=int(round(years * 365.25)))
    return [(d, p) for (d, p) in series if d >= start]


def ann_vol(prices):
    rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def max_drawdown(equity):
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def cagr(v_end, v_start, years):
    if v_start <= 0:
        return 0.0
    return (v_end / v_start) ** (1.0 / years) - 1.0


def backtest_ladder(series, ladder, budget=100.0):
    """单笔预算 budget，按阶梯逐档买入；创新高重新武装。返回 equity 曲线与统计。"""
    prices = [p for _, p in series]
    cash = budget
    shares = 0.0
    ath = prices[0]
    armed = {th for th, _ in ladder}
    triggers = []  # (date, threshold, buy_pct, price)
    equity = []
    for (d, p) in series:
        if p > ath:
            ath = p
            armed = {th for th, _ in ladder}  # 创新高重新武装
        dd = (p - ath) / ath * 100.0  # <=0
        for th, pct in ladder:
            if th in armed and -dd >= th:
                amt = min(cash, budget * pct / 100.0)
                if amt > 1e-9:
                    shares += amt / p
                    cash -= amt
                    triggers.append((d, th, pct, p))
                armed.discard(th)
        equity.append(cash + shares * p)
    deployed = budget - cash
    return {
        "equity": equity,
        "deployed_pct": deployed / budget * 100.0,
        "cash_pct": cash / budget * 100.0,
        "n_triggers": len(triggers),
        "triggers": triggers,
        "prices": prices,
    }


def analyze():
    data = {g: fetch(sym) for g, sym in PROXY.items()}
    print("数据区间：")
    for g, s in data.items():
        print(f"  {g}({PROXY[g]}): {s[0][0]} → {s[-1][0]}  共 {len(s)} 交易日")
    print()

    for g in ["纳指100", "标普500"]:
        series_full = data[g]
        ladder = LADDERS[g]
        ladder_txt = "、".join(f"跌{th}%买{pct}%" for th, pct in ladder)
        print("=" * 92)
        print(f"【{g}】代理标的 {PROXY[g]}    阶梯：{ladder_txt}")
        print("-" * 92)
        hdr = (f"{'年限':>4} | {'买入持有':^30} | {'阶梯买入':^38}")
        print(hdr)
        print(f"{'':>4} | {'年化':>7}{'波动率':>9}{'最大回撤':>10} | "
              f"{'年化':>7}{'波动率':>9}{'最大回撤':>10}{'投入%':>7}{'触发':>5}")
        print("-" * 92)
        for years in HORIZONS:
            s = slice_years(series_full, years)
            if len(s) < 60:
                continue
            prices = [p for _, p in s]
            # 买入持有
            bh_equity = [p / prices[0] * 100.0 for p in prices]
            bh_cagr = cagr(prices[-1], prices[0], years)
            bh_vol = ann_vol(prices)
            bh_mdd = max_drawdown(prices)
            # 阶梯
            lad = backtest_ladder(s, ladder)
            eq = lad["equity"]
            lad_end = eq[-1]
            lad_cagr = cagr(lad_end, 100.0, years)
            # 波动率/回撤只在已投入(非纯现金)区间才有意义，用整段 equity 计算
            lad_vol = ann_vol(eq)
            lad_mdd = max_drawdown(eq)
            print(f"{years:>3}年 | {bh_cagr*100:>6.1f}%{bh_vol*100:>8.1f}%{bh_mdd*100:>9.1f}% | "
                  f"{lad_cagr*100:>6.1f}%{lad_vol*100:>8.1f}%{lad_mdd*100:>9.1f}%"
                  f"{lad['deployed_pct']:>6.0f}%{lad['n_triggers']:>5}")
        print()

    # 回调频率：过去 20 年，各回撤深度出现的独立“回调事件”次数与平均水下天数
    print("=" * 92)
    print("回撤频率与恢复（20 年窗口）：独立回调事件中触及各深度的次数 / 平均恢复到新高的自然日数")
    print("-" * 92)
    depths = [6, 8, 10, 15, 20, 30, 40, 50]
    for g in ["纳指100", "标普500"]:
        s = slice_years(data[g], 20)
        # 划分“回调事件”：从一个新高开始，到重新回到该新高为止
        ath = s[0][1]
        ath_date = s[0][0]
        trough = ath
        in_dip = False
        events = []  # (max_depth_pct, underwater_days)
        cur_max_depth = 0.0
        dip_start = ath_date
        for (d, p) in s:
            if p >= ath:
                if in_dip:
                    events.append((cur_max_depth, (d - dip_start).days))
                    in_dip = False
                ath = p
                ath_date = d
                cur_max_depth = 0.0
            else:
                if not in_dip:
                    in_dip = True
                    dip_start = ath_date
                    cur_max_depth = 0.0
                depth = (ath - p) / ath * 100.0
                cur_max_depth = max(cur_max_depth, depth)
        # 记录仍未恢复的当前回调
        ongoing = None
        if in_dip:
            ongoing = (cur_max_depth, (s[-1][0] - dip_start).days)
        print(f"\n【{g}】{PROXY[g]}")
        for th in depths:
            cnt = sum(1 for md, _ in events if md >= th)
            if ongoing and ongoing[0] >= th:
                cnt += 1
            uw = [uw for md, uw in events if md >= th]
            avg_uw = sum(uw) / len(uw) if uw else 0
            note = ""
            if ongoing and ongoing[0] >= th:
                note = f"（含当前未收复 1 次，已 {ongoing[1]} 天）"
            print(f"    ≥跌{th:>2}%: {cnt:>2} 次   平均恢复 {avg_uw:>5.0f} 天{note}")

    # 触发明细（20 年窗口）与每次触发至今的回报
    print("=" * 92)
    print("阶梯触发明细（20 年窗口，每次触发买入价 → 至今复权收益）")
    print("-" * 92)
    for g in ["纳指100", "标普500"]:
        s = slice_years(data[g], 20)
        last_p = s[-1][1]
        lad = backtest_ladder(s, LADDERS[g])
        print(f"\n【{g}】{PROXY[g]}  期末价 {last_p:.2f}  触发 {lad['n_triggers']} 次，累计投入 {lad['deployed_pct']:.0f}%")
        for (d, th, pct, p) in lad["triggers"]:
            fwd = (last_p / p - 1.0) * 100.0
            print(f"    {d}  跌{th:>2}%档 买{pct:>2}%  价{p:>8.2f}  至今 {fwd:+.1f}%")


if __name__ == "__main__":
    analyze()
