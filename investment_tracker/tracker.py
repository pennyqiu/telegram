#!/usr/bin/env python3
"""
Investment Monitoring Automation
每日/每周/每月自动生成投资简报 HTML

本地运行：
  python tracker.py daily

服务器运行（输出到 Nginx web 目录）：
  python tracker.py daily --output /var/www/briefing
  或设置环境变量：BRIEFING_OUTPUT=/var/www/briefing python tracker.py daily
"""

import sys
import json
import os
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    print("请先安装依赖：pip install yfinance requests feedparser")
    sys.exit(1)

try:
    import requests
    import feedparser
except ImportError:
    print("请先安装依赖：pip install requests feedparser")
    sys.exit(1)

# ============================================================
# 配置区：修改这里来匹配你的实际持仓
# ============================================================
PORTFOLIO = {
    "VOO":   {"name": "Vanguard S&P 500",      "target_pct": 30.0, "shares": 0},
    "SCHD":  {"name": "Schwab Dividend ETF",    "target_pct": 30.0, "shares": 0},
    "QQQ":   {"name": "Invesco QQQ",            "target_pct":  8.0, "shares": 0},
    "MSFT":  {"name": "Microsoft",              "target_pct":  5.0, "shares": 0},
    "AAPL":  {"name": "Apple",                  "target_pct":  4.0, "shares": 0},
    "GOOGL": {"name": "Alphabet",               "target_pct":  4.0, "shares": 0},
    "NVDA":  {"name": "NVIDIA",                 "target_pct":  4.0, "shares": 0},
    "AMZN":  {"name": "Amazon",                 "target_pct":  5.0, "shares": 0},
    # 黄金+债券合并处理，用 GLD/BND 代替
    "GLD":   {"name": "SPDR Gold Shares",       "target_pct":  5.0, "shares": 0},
    "BND":   {"name": "Vanguard Total Bond",    "target_pct":  5.0, "shares": 0},
}

# 持仓总市值（人民币，用于显示）—— 如果 shares=0，用这个估算
TOTAL_VALUE_CNY = 5_000_000_00  # 5000万人民币示例
USD_CNY_RATE = 7.3              # 美元兑人民币汇率，定期手动更新

# 再平衡阈值
REBALANCE_THRESHOLD = 5.0  # 偏差超过5%触发提醒

# 输出目录
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 服务器模式：通过环境变量或命令行 --output 指定固定输出目录
# 服务器上设置：export BRIEFING_OUTPUT=/var/www/briefing
SERVER_OUTPUT = os.environ.get("BRIEFING_OUTPUT", "")

# ============================================================
# 数据获取
# ============================================================

def fetch_prices(tickers: list) -> dict:
    """批量获取股票当前价格和日涨跌幅"""
    result = {}
    try:
        data = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
        closes = data["Close"]
        for t in tickers:
            try:
                prices = closes[t].dropna()
                if len(prices) >= 2:
                    today = float(prices.iloc[-1])
                    prev  = float(prices.iloc[-2])
                    chg   = (today - prev) / prev * 100
                    result[t] = {"price": today, "change_pct": chg}
                elif len(prices) == 1:
                    result[t] = {"price": float(prices.iloc[-1]), "change_pct": 0.0}
            except Exception:
                result[t] = {"price": 0.0, "change_pct": 0.0}
    except Exception as e:
        print(f"[警告] 批量获取价格失败：{e}")
    return result


def fetch_earnings_calendar(tickers: list, days_ahead: int = 30) -> list:
    """获取未来 N 天内有财报的持仓（ETF 没有财报日历，自动跳过）"""
    # ETF 和黄金不会有财报，直接跳过避免 404 警告
    ETF_SKIP = {"VOO", "VTI", "QQQ", "SCHD", "VYM", "DGRO", "GLD", "BND", "IEF", "TLT", "VXUS"}
    events = []
    today = datetime.today().date()
    cutoff = today + timedelta(days=days_ahead)
    for t in tickers:
        if t in ETF_SKIP:
            continue
        try:
            info = yf.Ticker(t).calendar
            if info is None:
                continue
            # yfinance calendar 返回 DataFrame
            if hasattr(info, "columns") and "Earnings Date" in info.columns:
                ed = info["Earnings Date"].iloc[0]
                if hasattr(ed, "date"):
                    ed = ed.date()
                if today <= ed <= cutoff:
                    events.append({"ticker": t, "date": str(ed)})
            elif isinstance(info, dict) and "Earnings Date" in info:
                ed = info["Earnings Date"]
                if isinstance(ed, list):
                    ed = ed[0]
                if hasattr(ed, "date"):
                    ed = ed.date()
                if today <= ed <= cutoff:
                    events.append({"ticker": t, "date": str(ed)})
        except Exception:
            pass
    events.sort(key=lambda x: x["date"])
    return events


def fetch_news(tickers: list, max_per_ticker: int = 3) -> list:
    """通过 Google News RSS 获取每只股票的最新新闻"""
    all_news = []
    for t in tickers:
        url = f"https://news.google.com/rss/search?q={t}+stock&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_ticker]:
                pub = entry.get("published", "")
                all_news.append({
                    "ticker": t,
                    "title": entry.get("title", ""),
                    "link":  entry.get("link",  "#"),
                    "pub":   pub[:16] if pub else "",
                })
        except Exception:
            pass
    return all_news


def fetch_dividend_info(tickers: list) -> dict:
    """获取各 ETF/个股的股息率"""
    result = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            yield_val = info.get("dividendYield") or 0
            result[t] = round(yield_val * 100, 2)
        except Exception:
            result[t] = 0.0
    return result

# ============================================================
# 计算再平衡
# ============================================================

def calc_rebalance(prices: dict) -> list:
    """
    根据当前股数和市价计算各持仓权重，与目标权重对比，
    返回需要再平衡的列表（偏差 > REBALANCE_THRESHOLD）。
    如果 shares=0，跳过计算（需用户填写）。
    """
    total_value = sum(
        PORTFOLIO[t]["shares"] * prices.get(t, {}).get("price", 0)
        for t in PORTFOLIO
    )
    if total_value == 0:
        return []  # 未填写持仓数量

    alerts = []
    for t, cfg in PORTFOLIO.items():
        price  = prices.get(t, {}).get("price", 0)
        value  = cfg["shares"] * price
        actual = value / total_value * 100 if total_value else 0
        diff   = actual - cfg["target_pct"]
        if abs(diff) >= REBALANCE_THRESHOLD:
            action = "卖出" if diff > 0 else "买入"
            alerts.append({
                "ticker":  t,
                "name":    cfg["name"],
                "target":  cfg["target_pct"],
                "actual":  round(actual, 1),
                "diff":    round(diff, 1),
                "action":  action,
            })
    return sorted(alerts, key=lambda x: abs(x["diff"]), reverse=True)

# ============================================================
# HTML 生成
# ============================================================

CSS = """
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#f8fafc;color:#1e293b;margin:0;padding:24px}
  .container{max-width:960px;margin:0 auto}
  h1{font-size:22px;margin-bottom:4px;color:#0f172a}
  .subtitle{color:#64748b;font-size:13px;margin-bottom:24px}
  .card{background:#fff;border-radius:12px;border:1px solid #e2e8f0;
        padding:20px;margin-bottom:20px}
  .card-title{font-size:15px;font-weight:700;margin-bottom:14px;color:#1e293b;
              display:flex;align-items:center;gap:8px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{background:#f1f5f9;padding:8px 12px;text-align:left;
     border-bottom:2px solid #e2e8f0;font-weight:600;color:#475569}
  td{padding:8px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}
  .up{color:#16a34a;font-weight:600}
  .dn{color:#dc2626;font-weight:600}
  .badge{display:inline-block;padding:2px 8px;border-radius:20px;
         font-size:11px;font-weight:600}
  .badge-buy{background:#dcfce7;color:#15803d}
  .badge-sell{background:#fee2e2;color:#b91c1c}
  .badge-ok{background:#f1f5f9;color:#475569}
  .news-item{padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:13px}
  .news-item:last-child{border-bottom:none}
  .ticker-badge{display:inline-block;background:#eff6ff;color:#1d4ed8;
                border-radius:4px;padding:1px 6px;font-size:11px;
                font-weight:700;margin-right:6px}
  .earn-row{padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:13px}
  .summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
  .summary-item{background:#f8fafc;border-radius:8px;padding:12px;text-align:center}
  .summary-val{font-size:20px;font-weight:700;margin-bottom:2px}
  .summary-label{font-size:11px;color:#64748b}
  @media(max-width:600px){.summary-grid{grid-template-columns:1fr 1fr}}
</style>
"""

def _chg_class(v: float) -> str:
    return "up" if v >= 0 else "dn"

def _chg_str(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def build_html(mode: str, prices: dict, earnings: list,
               news: list, rebalance: list, dividends: dict) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    next_map = {"daily": "明日同一时间", "weekly": "下周一", "monthly": "下月1日", "rebalance": "手动触发"}
    next_update = next_map.get(mode, "—")
    mode_label = {"daily": "每日简报", "weekly": "每周简报",
                  "monthly": "每月简报", "rebalance": "再平衡检查"}.get(mode, "投资简报")

    # 组合概览
    gains = [p["change_pct"] for p in prices.values() if p["price"] > 0]
    avg_chg = sum(gains) / len(gains) if gains else 0
    up_count = sum(1 for v in gains if v >= 0)
    dn_count = len(gains) - up_count
    earn_count = len(earnings)

    summary_html = f"""
    <div class="summary-grid">
      <div class="summary-item">
        <div class="summary-val {_chg_class(avg_chg)}">{_chg_str(avg_chg)}</div>
        <div class="summary-label">持仓平均涨跌</div>
      </div>
      <div class="summary-item">
        <div class="summary-val" style="color:#16a34a">{up_count} ↑</div>
        <div class="summary-label">今日上涨数量</div>
      </div>
      <div class="summary-item">
        <div class="summary-val" style="color:#dc2626">{dn_count} ↓ &nbsp;
          {"⚠️" if earn_count else ""}</div>
        <div class="summary-label">今日下跌 &nbsp;|&nbsp; {earn_count}只即将财报</div>
      </div>
    </div>"""

    # 持仓价格表
    price_rows = ""
    for t, cfg in PORTFOLIO.items():
        p = prices.get(t, {})
        price = p.get("price", 0)
        chg   = p.get("change_pct", 0)
        div   = dividends.get(t, 0)
        price_rows += f"""
        <tr>
          <td><strong>{t}</strong></td>
          <td style="color:#475569;font-size:12px">{cfg['name']}</td>
          <td>${price:.2f}</td>
          <td class="{_chg_class(chg)}">{_chg_str(chg)}</td>
          <td>{cfg['target_pct']:.0f}%</td>
          <td>{div:.1f}%</td>
        </tr>"""

    price_html = f"""
    <table>
      <thead><tr><th>代码</th><th>名称</th><th>现价</th><th>今日涨跌</th>
        <th>目标权重</th><th>股息率</th></tr></thead>
      <tbody>{price_rows}</tbody>
    </table>"""

    # 财报日历
    if earnings:
        earn_rows = "".join(
            f'<div class="earn-row">📅 <strong>{e["date"]}</strong> &nbsp; '
            f'<span class="ticker-badge">{e["ticker"]}</span></div>'
            for e in earnings
        )
        earn_html = f'<div>{earn_rows}</div>'
    else:
        earn_html = '<p style="color:#94a3b8;font-size:13px">未来30天内无持仓公司财报</p>'

    # 新闻
    news_items = "".join(
        f'<div class="news-item">'
        f'<span class="ticker-badge">{n["ticker"]}</span>'
        f'<a href="{n["link"]}" target="_blank" style="color:#1d4ed8;text-decoration:none">{n["title"]}</a>'
        f'<span style="color:#94a3b8;font-size:11px;margin-left:8px">{n["pub"]}</span>'
        f'</div>'
        for n in news[:20]
    ) if news else '<p style="color:#94a3b8;font-size:13px">暂无最新新闻</p>'

    # 再平衡
    if rebalance:
        reb_rows = "".join(f"""
        <tr>
          <td><strong>{r['ticker']}</strong></td>
          <td style="color:#475569;font-size:12px">{r['name']}</td>
          <td>{r['target']:.0f}%</td>
          <td>{r['actual']:.1f}%</td>
          <td class="{_chg_class(-r['diff'])}">{_chg_str(r['diff'])}</td>
          <td><span class="badge {'badge-sell' if r['action']=='卖出' else 'badge-buy'}">{r['action']}</span></td>
        </tr>""" for r in rebalance)
        reb_html = f"""
        <table>
          <thead><tr><th>代码</th><th>名称</th><th>目标</th><th>实际</th>
            <th>偏差</th><th>操作</th></tr></thead>
          <tbody>{reb_rows}</tbody>
        </table>
        <p style="font-size:12px;color:#64748b;margin-top:8px">
          ⚠️ 偏差超过 {REBALANCE_THRESHOLD:.0f}% 建议再平衡（优先用新资金买入补足，减少税收摩擦）
        </p>"""
    elif all(PORTFOLIO[t]["shares"] == 0 for t in PORTFOLIO):
        reb_html = """<p style="color:#f59e0b;font-size:13px">
          ⚠️ 请在 tracker.py 的 PORTFOLIO 配置中填写各持仓的 shares（股数），才能计算再平衡。
        </p>"""
    else:
        reb_html = f'<p style="color:#16a34a;font-size:13px">✅ 所有持仓偏差均在 {REBALANCE_THRESHOLD:.0f}% 以内，暂不需要再平衡。</p>'

    # 投资日志模板（仅月报显示）
    journal_html = ""
    if mode in ("monthly", "rebalance"):
        journal_html = f"""
    <div class="card">
      <div class="card-title">📝 本月投资日志模板</div>
      <div style="background:#f8fafc;border-radius:8px;padding:14px;font-size:13px;
                  font-family:monospace;line-height:2;white-space:pre-wrap">
本月总结 ({datetime.now().strftime("%Y年%m月")})

【买入记录】
  - 代码：___  数量：___ 股  均价：$___
  - 买入理由：
  - 买入后 thesis 是否有变化：

【卖出记录】
  - 代码：___  数量：___ 股  均价：$___
  - 卖出理由（thesis 被证伪 / 再平衡 / 其他）：

【市场观察】
  - 本月最重要的宏观事件：
  - 对持仓影响：

【情绪检查】
  - 本月最大的恐惧/贪婪时刻：
  - 我有没有做出情绪化决策？
  - 如果有，是什么让我动手了？

【下月计划】
  - 计划买入：
  - 需要密切关注的财报：
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{mode_label} — {ts}</title>
{CSS}
</head>
<body>
<div class="container">
  <h1>📊 投资{mode_label}</h1>
  <div class="subtitle">生成时间：{ts} &nbsp;|&nbsp; 汇率：¥{USD_CNY_RATE}/$</div>

  <div class="card">
    <div class="card-title">⚡ 今日概览</div>
    {summary_html}
  </div>

  <div class="card">
    <div class="card-title">💼 持仓快照</div>
    {price_html}
  </div>

  <div class="card">
    <div class="card-title">📅 即将财报（未来30天）</div>
    {earn_html}
  </div>

  <div class="card">
    <div class="card-title">📰 持仓最新新闻</div>
    {news_items}
  </div>

  <div class="card">
    <div class="card-title">⚖️ 再平衡检查（偏差 &gt;{REBALANCE_THRESHOLD:.0f}% 提醒）</div>
    {reb_html}
  </div>

  {journal_html}

  <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:12px">
    由 investment_tracker.py 自动生成 · 数据来源：Yahoo Finance / Google News RSS<br>
    下次更新：{next_update}
  </div>
</div>
</body>
</html>"""


# ============================================================
# 主程序
# ============================================================

def main():
    # 解析参数：python tracker.py [mode] [--output /path/to/dir]
    args = sys.argv[1:]
    mode = "daily"
    output_dir = None

    i = 0
    while i < len(args):
        if args[i] == "--output" and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            mode = args[i]
            i += 1
        else:
            i += 1

    valid = {"daily", "weekly", "monthly", "rebalance"}
    if mode not in valid:
        print(f"用法：python tracker.py [{'|'.join(valid)}] [--output /path/to/dir]")
        sys.exit(1)

    # 确定输出目录（优先级：命令行 > 环境变量 > 脚本同目录）
    out_dir = output_dir or SERVER_OUTPUT or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    tickers = list(PORTFOLIO.keys())
    print(f"[{mode.upper()}] 正在获取数据...")

    print("  → 获取股价...")
    prices = fetch_prices(tickers)

    print("  → 获取财报日历...")
    earnings = fetch_earnings_calendar(tickers, days_ahead=30)

    print("  → 获取新闻...")
    news = fetch_news(tickers, max_per_ticker=3 if mode == "daily" else 5)

    print("  → 计算股息率...")
    dividends = fetch_dividend_info(tickers)

    print("  → 计算再平衡...")
    rebalance = calc_rebalance(prices)

    html = build_html(mode, prices, earnings, news, rebalance, dividends)

    is_server = bool(output_dir or SERVER_OUTPUT)
    if is_server:
        # 服务器模式：输出 daily.html / weekly.html / monthly.html
        fname    = os.path.join(out_dir, f"{mode}.html")
        snapshot = os.path.join(out_dir, f"briefing_{mode}_{datetime.now().strftime('%Y%m%d')}.html")
        # index.html 始终指向最新一次运行的简报（方便 /briefing/ 直接打开）
        index    = os.path.join(out_dir, "index.html")

        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        with open(snapshot, "w", encoding="utf-8") as f:
            f.write(html)
        with open(index, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"\n✅ 简报已生成：{fname}")
        print(f"   历史快照：{snapshot}")
        print(f"   首页索引：{index}")
    else:
        # 本地模式：带时间戳文件名，方便对比历史
        fname = os.path.join(out_dir, f"briefing_{mode}_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n✅ 简报已生成：{fname}")
        print("   用浏览器打开即可查看。")

    # 自动在 macOS 上用默认浏览器打开
    if sys.platform == "darwin" and not is_server:
        os.system(f'open "{fname}"')


if __name__ == "__main__":
    main()
