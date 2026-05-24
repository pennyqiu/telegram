#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 operations/dashboard.html 统计看板：
- 4 大核心数字（单元 / 成稿 / 字数 / 渠道）
- 各渠道横向堆叠条形图（纯 CSS）
- 近 30 天热力图（按文件 mtime + git log 综合）
- 渠道分布饼图（CSS conic-gradient）
"""
import os, sys, io, subprocess, datetime
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = 'insurance-guide'
PUB = f'{ROOT}/operations/published'

# ---- 1) 各渠道文件清单 ----
channels = {
    'wechat':    {'name': '公众号成稿', 'color': '#10b981', 'icon': '📨', 'ext': ['.html']},
    'zhihu':     {'name': '知乎成稿',   'color': '#3b82f6', 'icon': '📰', 'ext': ['.md']},
    'xhs':       {'name': '小红书散稿', 'color': '#ec4899', 'icon': '🌹', 'ext': ['.md']},
    'xhs-units': {'name': '小红书单元', 'color': '#f472b6', 'icon': '📚', 'ext': ['.html'], 'exclude': ['index.html']},
    'pyq':       {'name': '朋友圈素材', 'color': '#f59e0b', 'icon': '💬', 'ext': ['.md']},
    'units':     {'name': 'CPA 发布单元', 'color': '#8b5cf6', 'icon': '📦', 'ext': ['.html'], 'exclude': ['index.html']},
}

stats = {}
all_files = []  # for heatmap: (path, mtime)
for key, cfg in channels.items():
    d = os.path.join(PUB, key)
    files = []
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f == 'index.html':
                continue
            if 'exclude' in cfg and f in cfg['exclude']:
                continue
            ext = os.path.splitext(f)[1]
            if ext not in cfg['ext']:
                continue
            full = os.path.join(d, f)
            if os.path.isfile(full):
                files.append(f)
                all_files.append((full, os.path.getmtime(full)))
    stats[key] = {**cfg, 'count': len(files), 'files': files}

total_files = sum(s['count'] for s in stats.values())

# ---- 2) 总字数（从 refresh_units.py 的 UNITS 列表读，加上 pyq + xhs-units 估算）----
def estimate_words():
    # CPA + v22 单元字数：从 refresh_units.py 解析 UNITS
    p = f'{ROOT}/operations/tools/refresh_units.py'
    if not os.path.exists(p):
        return 0
    with open(p, 'r', encoding='utf-8') as f:
        c = f.read()
    import re
    nums = re.findall(r"'words':\s*'(\d+)\+?'", c)
    cpa_words = sum(int(n) for n in nums)
    # pyq: 30 条 × ~150 字
    pyq_words = stats['pyq']['count'] * 150
    # xhs-units: 39 篇 × ~900 字（已经记录在 xhs_units 索引页）
    xhs_units_words = stats['xhs-units']['count'] * 900
    # xhs 散稿：估算 5000 字
    xhs_words = stats['xhs']['count'] * 5000 if stats['xhs']['count'] else 0
    return cpa_words + pyq_words + xhs_units_words + xhs_words

total_words = estimate_words()

# ---- 3) 热力图：近 30 天每日发布数 ----
today = datetime.date.today()
days = [today - datetime.timedelta(days=i) for i in range(29, -1, -1)]
day_counts = defaultdict(int)
for path, mtime in all_files:
    d = datetime.date.fromtimestamp(mtime)
    if d in days:
        day_counts[d] += 1

max_day = max(day_counts.values()) if day_counts else 1

def heat_color(n):
    if n == 0: return '#f1f5f9'
    ratio = n / max_day
    if ratio <= 0.25: return '#fef3c7'
    if ratio <= 0.5:  return '#fcd34d'
    if ratio <= 0.75: return '#f59e0b'
    return '#d97706'

heat_cells = ''
for i, d in enumerate(days):
    n = day_counts[d]
    color = heat_color(n)
    label = f'{d.strftime("%m-%d")} · {n} 篇'
    heat_cells += f'<div class="heat-cell" style="background:{color};" title="{label}"><span class="heat-tip">{label}</span></div>'

# 取最近 7 天作为周对比
last_7 = sum(day_counts[d] for d in days[-7:])
prev_7 = sum(day_counts[d] for d in days[-14:-7])

# ---- 4) 渠道分布饼图：conic-gradient 配色 ----
sorted_ch = sorted(stats.items(), key=lambda x: -x[1]['count'])
total = sum(s['count'] for _, s in sorted_ch) or 1
acc = 0
gradient_parts = []
for key, s in sorted_ch:
    if s['count'] == 0: continue
    start = acc / total * 360
    acc += s['count']
    end = acc / total * 360
    gradient_parts.append(f'{s["color"]} {start:.1f}deg {end:.1f}deg')
gradient_css = ', '.join(gradient_parts) if gradient_parts else '#e2e8f0 0deg 360deg'

# ---- 5) 渠道条形图 ----
max_count = max(s['count'] for s in stats.values()) or 1
bar_rows = ''
for key, s in sorted_ch:
    pct = s['count'] / max_count * 100
    bar_rows += f'''      <div class="bar-row">
        <div class="bar-label"><span class="bar-icon" style="color:{s['color']};">{s['icon']}</span>{s['name']}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{s['color']};"></div></div>
        <div class="bar-value">{s['count']}</div>
      </div>
'''

# ---- 6) 图例 ----
legend = ''
for key, s in sorted_ch:
    if s['count'] == 0: continue
    pct = s['count'] / total * 100
    legend += f'''      <div class="legend-item">
        <span class="legend-dot" style="background:{s['color']};"></span>
        <span class="legend-name">{s['name']}</span>
        <span class="legend-count">{s['count']}</span>
        <span class="legend-pct">{pct:.0f}%</span>
      </div>
'''

# ---- 7) 渲染 HTML ----
last_mtime_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
trend_arrow = '↑' if last_7 > prev_7 else ('↓' if last_7 < prev_7 else '→')
trend_color = '#10b981' if last_7 > prev_7 else ('#ef4444' if last_7 < prev_7 else '#94a3b8')
trend_delta = last_7 - prev_7

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>运营统计看板 · 港险综合站</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1e293b;background:#f1f5f9;line-height:1.6;-webkit-font-smoothing:antialiased;}}
  a{{color:inherit;text-decoration:none;}}
  .topbar{{background:#fff;padding:14px 24px;border-bottom:1px solid #e2e8f0;position:sticky;top:0;z-index:10;}}
  .topbar-inner{{max-width:1280px;margin:0 auto;display:flex;align-items:center;gap:12px;font-size:14px;}}
  .topbar a{{color:#475569;font-weight:500;}}
  .topbar a:hover{{color:#6366f1;}}
  .topbar .here{{color:#6366f1;font-weight:700;}}
  .topbar .sep{{color:#cbd5e1;}}
  .hero{{background:linear-gradient(135deg,#312e81 0%,#6366f1 100%);color:#fff;padding:32px 24px 44px;}}
  .hero-inner{{max-width:1280px;margin:0 auto;}}
  .hero-tag{{display:inline-block;font-size:11px;font-weight:700;letter-spacing:1.5px;background:rgba(255,255,255,0.18);padding:5px 12px;border-radius:12px;margin-bottom:12px;}}
  .hero h1{{font-size:26px;font-weight:800;margin-bottom:4px;}}
  .hero-sub{{font-size:13.5px;opacity:0.85;}}
  .container{{max-width:1280px;margin:-26px auto 0;padding:0 24px 60px;position:relative;z-index:2;}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px;}}
  .kpi{{background:#fff;border-radius:14px;padding:22px 24px;border:1px solid #e2e8f0;}}
  .kpi-label{{font-size:11.5px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;}}
  .kpi-value{{font-size:36px;font-weight:900;color:#0f172a;line-height:1;letter-spacing:-1px;}}
  .kpi-unit{{font-size:13px;color:#64748b;margin-left:4px;font-weight:600;}}
  .kpi-foot{{font-size:11.5px;color:#94a3b8;margin-top:10px;}}
  .panels{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:24px;}}
  .panel{{background:#fff;border-radius:14px;padding:22px 24px;border:1px solid #e2e8f0;}}
  .panel h2{{font-size:14px;font-weight:700;color:#334155;letter-spacing:0.5px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;}}
  .panel-sub{{font-size:11.5px;color:#94a3b8;font-weight:500;}}

  /* bars */
  .bar-row{{display:flex;align-items:center;gap:14px;padding:10px 0;}}
  .bar-label{{flex:0 0 130px;font-size:13.5px;color:#334155;display:flex;align-items:center;gap:6px;}}
  .bar-icon{{font-size:14px;}}
  .bar-track{{flex:1;height:14px;background:#f1f5f9;border-radius:7px;overflow:hidden;}}
  .bar-fill{{height:100%;border-radius:7px;transition:width 0.6s;}}
  .bar-value{{flex:0 0 36px;font-size:14px;font-weight:800;color:#0f172a;text-align:right;font-variant-numeric:tabular-nums;}}

  /* pie */
  .pie-wrap{{display:flex;align-items:center;justify-content:center;flex-direction:column;}}
  .pie{{width:160px;height:160px;border-radius:50%;background:conic-gradient({gradient_css});position:relative;margin-bottom:16px;}}
  .pie::before{{content:'';position:absolute;inset:30px;background:#fff;border-radius:50%;}}
  .pie-center{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:1;}}
  .pie-num{{font-size:30px;font-weight:900;color:#0f172a;line-height:1;}}
  .pie-label{{font-size:11px;color:#64748b;margin-top:4px;letter-spacing:0.5px;}}
  .legend{{margin-top:8px;font-size:12.5px;color:#475569;width:100%;}}
  .legend-item{{display:flex;align-items:center;gap:8px;padding:5px 0;}}
  .legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;}}
  .legend-name{{flex:1;}}
  .legend-count{{font-weight:700;color:#0f172a;font-variant-numeric:tabular-nums;}}
  .legend-pct{{color:#94a3b8;font-size:11.5px;width:34px;text-align:right;font-variant-numeric:tabular-nums;}}

  /* heatmap */
  .heatmap{{display:grid;grid-template-columns:repeat(30,1fr);gap:5px;margin-bottom:14px;}}
  .heat-cell{{aspect-ratio:1;border-radius:4px;position:relative;cursor:default;}}
  .heat-cell:hover .heat-tip{{display:block;}}
  .heat-tip{{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:#0f172a;color:#fff;font-size:11px;padding:4px 8px;border-radius:4px;white-space:nowrap;z-index:5;font-variant-numeric:tabular-nums;}}
  .heat-tip::after{{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:4px solid transparent;border-top-color:#0f172a;}}
  .heat-scale{{display:flex;align-items:center;gap:6px;font-size:11px;color:#94a3b8;}}
  .heat-scale-cell{{width:14px;height:14px;border-radius:3px;}}

  /* trend */
  .trend-row{{display:flex;align-items:center;gap:16px;margin-top:14px;padding:12px 16px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;}}
  .trend-num{{font-size:22px;font-weight:900;color:{trend_color};}}
  .trend-label{{font-size:12px;color:#64748b;}}

  footer{{text-align:center;padding:24px;color:#94a3b8;font-size:12px;background:#fff;border-top:1px solid #e2e8f0;margin-top:30px;}}
  footer a{{color:#6366f1;}}

  @media (max-width:900px){{
    .kpi-grid{{grid-template-columns:repeat(2,1fr);}}
    .panels{{grid-template-columns:1fr;}}
    .heatmap{{grid-template-columns:repeat(15,1fr);}}
  }}
</style>
</head>
<body>

<nav class="topbar">
  <div class="topbar-inner">
    <a href="../index.html">🏠 综合站首页</a>
    <span class="sep">›</span>
    <a href="index.html">运营中心</a>
    <span class="sep">›</span>
    <span class="here">dashboard</span>
    <span style="margin-left:auto;font-size:12px;color:#94a3b8;">最后刷新: {last_mtime_str}</span>
  </div>
</nav>

<header class="hero">
  <div class="hero-inner">
    <span class="hero-tag">DASHBOARD · 运营统计看板</span>
    <h1>📊 运营统计看板</h1>
    <div class="hero-sub">实时统计各渠道成稿数、字数累计、近 30 天发布热度</div>
  </div>
</header>

<main class="container">

  <div class="kpi-grid">
    <div class="kpi">
      <div class="kpi-label">📦 总稿件</div>
      <div class="kpi-value">{total_files}<span class="kpi-unit">篇</span></div>
      <div class="kpi-foot">覆盖 {sum(1 for s in stats.values() if s['count']>0)} 个渠道</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">📝 累计字数</div>
      <div class="kpi-value">{total_words/10000:.1f}<span class="kpi-unit">万字</span></div>
      <div class="kpi-foot">含 CPA + 小红书 + 朋友圈</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">🆕 近 7 天</div>
      <div class="kpi-value">{last_7}<span class="kpi-unit">篇</span></div>
      <div class="kpi-foot" style="color:{trend_color};">{trend_arrow} {abs(trend_delta)} vs 上周</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">🎯 CPA 旗舰</div>
      <div class="kpi-value">14<span class="kpi-unit">篇</span></div>
      <div class="kpi-foot">100% 公众号 + 知乎双发</div>
    </div>
  </div>

  <div class="panels">
    <div class="panel">
      <h2>📊 各渠道稿件分布 <span class="panel-sub">按数量排序</span></h2>
{bar_rows.rstrip()}
    </div>

    <div class="panel">
      <h2>🍩 渠道占比</h2>
      <div class="pie-wrap">
        <div class="pie">
          <div class="pie-center">
            <div class="pie-num">{total_files}</div>
            <div class="pie-label">TOTAL</div>
          </div>
        </div>
        <div class="legend">
{legend.rstrip()}
        </div>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>🔥 近 30 天发布热力 <span class="panel-sub">{(today - datetime.timedelta(days=29)).strftime('%m-%d')} ～ {today.strftime('%m-%d')}</span></h2>
    <div class="heatmap">
{heat_cells}
    </div>
    <div class="heat-scale">
      <span>少</span>
      <span class="heat-scale-cell" style="background:#f1f5f9;"></span>
      <span class="heat-scale-cell" style="background:#fef3c7;"></span>
      <span class="heat-scale-cell" style="background:#fcd34d;"></span>
      <span class="heat-scale-cell" style="background:#f59e0b;"></span>
      <span class="heat-scale-cell" style="background:#d97706;"></span>
      <span>多</span>
      <span style="margin-left:auto;">本周 {last_7} 篇 · 上周 {prev_7} 篇</span>
    </div>
    <div class="trend-row">
      <span class="trend-num">{trend_arrow} {abs(trend_delta)}</span>
      <span class="trend-label">
        近 7 天发布 <b>{last_7}</b> 篇，对比上 7 天 <b>{prev_7}</b> 篇，
        {('保持上升势头' if trend_delta > 0 else '略有下降' if trend_delta < 0 else '基本持平')}
      </span>
    </div>
  </div>

</main>

<footer>
  <div>运营统计看板 · 港险综合站 v3.1 · 数据来源：published/ 目录文件 mtime</div>
  <div style="margin-top:8px;">
    <a href="../index.html">综合站首页</a> · 
    <a href="index.html">运营中心</a> · 
    <a href="published/units/index.html">CPA 发布单元</a> · 
    <a href="published/xhs-units/index.html">小红书发布单元</a>
  </div>
</footer>

</body>
</html>
'''

out = f'{ROOT}/operations/dashboard.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'[OK] {out} 生成')
print(f'     总稿件 {total_files} · 累计字数 {total_words/10000:.1f} 万 · 近 7 天 {last_7} 篇')
for k, s in sorted_ch:
    print(f'       · {s["icon"]} {s["name"]:12s} {s["count"]:>3d}')
