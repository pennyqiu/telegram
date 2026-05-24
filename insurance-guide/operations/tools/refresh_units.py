#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
刷新发布物料相关的所有索引页 —— 每次新增文章后跑一次。
扫描 operations/published/ 实际文件，重新生成：
1. published/wechat/index.html       公众号成稿索引
2. published/zhihu/index.html        知乎成稿索引
3. published/units/<slug>.html       每个发布单元聚合页
4. published/units/index.html        发布单元总览
5. 主 dashboard / 运营中心 dashboard 上的计数

新增发布单元只需扩展下面的 UNITS 列表。
"""
import os
import sys
import io
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 自动切到仓库根（这样无论从哪儿调用都能找到 insurance-guide/）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..'))
os.chdir(_REPO_ROOT)


# ============== 发布单元数据（每加一篇就加一项）==============
UNITS = [
    {
        'slug': 'cpa01-dividend-trap',
        'number': '01',
        'tag': 'CPA 旗舰研报',
        'title': '港险分红险到底是不是智商税',
        'subtitle': 'CPA 视角的精算假设全拆解',
        'source_html': 'cpa-01-dividend-trap.html',
        'words': '6000+',
        'wechat_html': '公众号_港险分红险智商税CPA拆解.html',
        'zhihu_md': '知乎_港险分红险智商税CPA拆解.md',
        'hero_a': '#1e3a8a', 'hero_b': '#3b82f6',
    },
    {
        'slug': 'cpa02-fulfillment-ratio',
        'number': '02',
        'tag': 'CPA 旗舰研报',
        'title': '5000 字读懂分红实现率',
        'subtitle': '8 家公司横评 · 历史数据 · CPA 视角拆解',
        'source_html': 'cpa-02-fulfillment-ratio.html',
        'words': '5000+',
        'wechat_html': '公众号_港险分红实现率CPA横评.html',
        'zhihu_md': '知乎_港险分红实现率CPA横评.md',
        'hero_a': '#1e3a8a', 'hero_b': '#3b82f6',
    },
    {
        'slug': 'cpa03-usd-vs-rmb',
        'number': '03',
        'tag': 'CPA 旗舰研报 · 🆕',
        'title': '美元保单 vs 人民币保单',
        'subtitle': '不同通胀假设下的购买力平价对比 · CPA 横评',
        'source_html': 'cpa-03-usd-vs-rmb.html',
        'words': '5000+',
        'wechat_html': '公众号_港险美元保单VS人民币保单CPA对比.html',
        'zhihu_md': '知乎_港险美元保单VS人民币保单CPA对比.md',
        'hero_a': '#1e3a8a', 'hero_b': '#3b82f6',
    },
    {
        'slug': 'v22-persona',
        'number': '★',
        'tag': '人设奠基长文',
        'title': '在迅雷做了 8 年总账，我为什么把简历交给了安盛',
        'subtitle': '人设奠基长文 · 公众号 + 知乎双版本',
        'source_html': 'v22-persona.html',
        'words': '8000+',
        'wechat_html': '公众号_在迅雷做了8年总账.html',
        'zhihu_md': '知乎_8年迅雷CPA转做香港保险.md',
        'hero_a': '#581c87', 'hero_b': '#a855f7',
    },
]


def fmt_size(b):
    if b < 1024: return f'{b} B'
    if b < 1024 * 1024: return f'{b/1024:.1f} KB'
    return f'{b/1024/1024:.2f} MB'


def file_icon(name):
    if name.endswith('.html'): return 'html', '📄'
    if name.endswith('.md'): return 'md', '📝'
    return 'default', '📎'


# 自动构造文件描述
WECHAT_DESC = {}
ZHIHU_DESC = {}
for u in UNITS:
    marker = ' · 🆕' if '🆕' in u.get('tag', '') else ''
    if 'cpa' in u['slug']:
        prefix = f'CPA-{u["number"]}{marker}'
    elif u['number'] == '★':
        prefix = '★ 人设奠基长文'
    else:
        prefix = ''
    desc = f'{prefix} · {u["title"]}' if prefix else u['title']
    if u.get('wechat_html'):
        WECHAT_DESC[u['wechat_html']] = desc
    if u.get('zhihu_md'):
        ZHIHU_DESC[u['zhihu_md']] = desc
# 补充一些非 unit 但已存在的
WECHAT_DESC['公众号_在迅雷做了8年总账.md'] = '人设奠基长文 · Markdown 源'


# ============== 1. wechat/zhihu 索引模板 ==============
INDEX_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>__TITLE__ · 运营中心</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1e293b;background:#f8fafc;line-height:1.6;}
  a{color:inherit;text-decoration:none;}
  .topbar{background:#fff;padding:14px 24px;border-bottom:1px solid #e2e8f0;position:sticky;top:0;z-index:10;}
  .topbar-inner{max-width:980px;margin:0 auto;display:flex;align-items:center;gap:12px;font-size:14px;}
  .topbar a{color:#475569;font-weight:500;}
  .topbar a:hover{color:__ACCENT__;}
  .topbar .here{color:__ACCENT__;font-weight:700;}
  .topbar .sep{color:#cbd5e1;}
  .hero{background:linear-gradient(135deg,__HERO_A__ 0%,__HERO_B__ 100%);color:#fff;padding:36px 24px 44px;}
  .hero-inner{max-width:980px;margin:0 auto;}
  .hero-tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:1.5px;background:rgba(255,255,255,0.18);padding:5px 12px;border-radius:12px;margin-bottom:14px;}
  .hero h1{font-size:28px;font-weight:800;margin-bottom:8px;}
  .hero p{font-size:14px;opacity:0.92;line-height:1.7;}
  .hero-meta{font-size:12px;font-family:Consolas,Monaco,monospace;opacity:0.85;margin-top:14px;background:rgba(0,0,0,0.18);padding:6px 12px;border-radius:6px;display:inline-block;}
  .container{max-width:980px;margin:-22px auto 0;padding:0 24px 60px;position:relative;z-index:2;}
  .desc-box{background:#fff;border-radius:12px;padding:18px 22px;margin-bottom:18px;border:1px solid #e2e8f0;border-left:3px solid __ACCENT__;}
  .desc-title{font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px;}
  .desc-text{font-size:13px;color:#475569;line-height:1.7;}
  .desc-text code{background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:12px;color:__ACCENT__;}
  .file-list{background:#fff;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden;}
  .file-row{display:flex;align-items:center;padding:16px 20px;border-bottom:1px solid #f1f5f9;}
  .file-row:last-child{border-bottom:none;}
  .file-row:hover{background:#f8fafc;}
  .file-icon{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;margin-right:14px;flex-shrink:0;}
  .file-icon.html{background:#dbeafe;color:#1e40af;}
  .file-icon.md{background:#d1fae5;color:#047857;}
  .file-icon.default{background:#e2e8f0;color:#475569;}
  .file-info{flex:1;min-width:0;}
  .file-name{font-size:15px;font-weight:600;color:#0f172a;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .file-name a{color:__ACCENT__;}
  .file-name a:hover{text-decoration:underline;}
  .file-meta{font-size:12px;color:#94a3b8;margin-top:3px;}
  .file-size{font-size:12px;color:#64748b;margin-left:14px;flex-shrink:0;font-variant-numeric:tabular-nums;}
  footer{text-align:center;padding:24px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;background:#fff;margin-top:40px;}
  footer a{color:__ACCENT__;}
</style>
</head>
<body>

<nav class="topbar"><div class="topbar-inner">
  <a href="../../../index.html">🏠 综合站首页</a>
  <span class="sep">›</span>
  <a href="../../index.html">运营中心</a>
  <span class="sep">›</span>
  <span style="color:#94a3b8;">published/</span>
  <span class="sep">›</span>
  <span class="here">__DIR__/</span>
  <span style="margin-left:auto;font-size:12px;color:#94a3b8;">v3.1</span>
</div></nav>

<header class="hero"><div class="hero-inner">
  <span class="hero-tag">__TAG__</span>
  <h1>__TITLE__</h1>
  <p>__SUBTITLE__</p>
  <div class="hero-meta">📁 operations/published/__DIR__/ · __COUNT__ 个文件</div>
</div></header>

<main class="container">
  <div class="desc-box">
    <div class="desc-title">💡 使用方法</div>
    <div class="desc-text">__DESC_TEXT__</div>
  </div>
  <div class="file-list">
__FILE_ROWS__
  </div>
</main>

<footer>
  <div>__TITLE__ · 运营中心 v3.1</div>
  <div style="margin-top:8px;">
    <a href="../../../index.html">综合站首页</a> · 
    <a href="../../index.html">运营中心</a> · 
    <a href="../units/index.html">📦 发布单元总览</a>
  </div>
</footer>

</body>
</html>
"""


def gen_channel_index(dir_path, dir_name, title, tag, subtitle, accent,
                     hero_a, hero_b, desc_text, desc_map):
    if not os.path.isdir(dir_path):
        return
    entries = sorted([
        f for f in os.listdir(dir_path)
        if os.path.isfile(os.path.join(dir_path, f)) and f != 'index.html'
    ])
    rows = []
    for name in entries:
        full = os.path.join(dir_path, name)
        cls, icon = file_icon(name)
        size = fmt_size(os.path.getsize(full))
        desc = desc_map.get(name, '')
        desc_html = f'<div class="file-meta">{desc}</div>' if desc else ''
        rows.append(f"""    <div class="file-row">
      <div class="file-icon {cls}">{icon}</div>
      <div class="file-info">
        <div class="file-name"><a href="{name}">{name}</a></div>{desc_html}
      </div>
      <div class="file-size">{size}</div>
    </div>""")
    file_rows = '\n'.join(rows)
    html = INDEX_TPL
    for k, v in {
        '__TITLE__': title, '__TAG__': tag, '__SUBTITLE__': subtitle,
        '__ACCENT__': accent, '__HERO_A__': hero_a, '__HERO_B__': hero_b,
        '__DIR__': dir_name, '__COUNT__': str(len(entries)),
        '__DESC_TEXT__': desc_text, '__FILE_ROWS__': file_rows,
    }.items():
        html = html.replace(k, v)
    out = os.path.join(dir_path, 'index.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[OK] {out}  ({len(entries)} files)')


# ============== 2. 发布单元页 ==============
UNIT_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>__TITLE__ · 发布单元</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1e293b;background:#f8fafc;line-height:1.65;}
  a{color:inherit;text-decoration:none;}
  .topbar{background:#fff;padding:14px 24px;border-bottom:1px solid #e2e8f0;position:sticky;top:0;z-index:10;}
  .topbar-inner{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:12px;font-size:14px;}
  .topbar a{color:#475569;font-weight:500;}
  .topbar a:hover{color:#f59e0b;}
  .topbar .here{color:#f59e0b;font-weight:700;}
  .topbar .sep{color:#cbd5e1;}
  .hero{background:linear-gradient(135deg,__HERO_A__ 0%,__HERO_B__ 100%);color:#fff;padding:50px 24px 60px;position:relative;overflow:hidden;}
  .hero::before{content:'';position:absolute;top:-30%;right:-5%;width:500px;height:500px;background:radial-gradient(circle,rgba(255,255,255,0.1) 0%,transparent 70%);border-radius:50%;}
  .hero-inner{max-width:1180px;margin:0 auto;position:relative;z-index:1;}
  .hero-row{display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap;}
  .hero-num{font-size:96px;font-weight:900;line-height:0.9;color:#fff;letter-spacing:-3px;flex-shrink:0;}
  .hero-main{flex:1;min-width:300px;}
  .hero-tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:1.5px;background:rgba(255,255,255,0.18);padding:5px 12px;border-radius:12px;margin-bottom:10px;}
  .hero h1{font-size:30px;font-weight:800;margin-bottom:10px;line-height:1.3;}
  .hero p{font-size:15px;opacity:0.92;line-height:1.7;}
  .hero-stats{display:flex;gap:24px;margin-top:18px;flex-wrap:wrap;align-items:center;}
  .hero-stat{display:flex;flex-direction:column;}
  .hero-stat-num{font-size:22px;font-weight:800;line-height:1;}
  .hero-stat-label{font-size:11px;opacity:0.85;margin-top:4px;letter-spacing:0.5px;}
  .source-link{display:inline-flex;align-items:center;gap:6px;padding:7px 13px;background:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.3);border-radius:6px;font-size:12px;font-weight:600;}
  .container{max-width:1180px;margin:-30px auto 0;padding:0 24px 80px;position:relative;z-index:2;}
  .section{margin-bottom:36px;}
  .section-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:16px;padding:0 4px;}
  .section-title{font-size:20px;font-weight:800;color:#0f172a;}
  .section-title span{color:#94a3b8;font-weight:500;font-size:13px;margin-left:8px;}
  .grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;}
  @media(max-width:760px){.grid-2{grid-template-columns:1fr;}}
  .text-card{background:#fff;border-radius:14px;padding:24px;border:1px solid #e2e8f0;border-left:4px solid var(--ch);}
  .text-card-head{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
  .text-card-icon{width:32px;height:32px;border-radius:8px;background:var(--ch-bg);display:flex;align-items:center;justify-content:center;font-size:16px;}
  .text-card-channel{font-size:12px;font-weight:700;color:var(--ch);letter-spacing:1px;}
  .text-card-title{font-size:17px;font-weight:700;color:#0f172a;margin-bottom:6px;}
  .text-card-file{font-size:13px;color:#475569;font-family:Consolas,Monaco,monospace;background:#f1f5f9;padding:6px 10px;border-radius:6px;display:inline-block;margin-top:6px;}
  .text-card-actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;}
  .btn{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:600;}
  .btn-primary{background:var(--ch);color:#fff;}
  .btn-ghost{background:#f1f5f9;color:#475569;}
  .text-card-tip{font-size:12px;color:#64748b;line-height:1.7;margin-top:14px;padding:10px 14px;background:#fafbfc;border-radius:6px;border-left:2px solid #cbd5e1;}
  .text-card-tip code{background:#f1f5f9;color:#1e40af;padding:2px 6px;border-radius:4px;font-family:Consolas,Monaco,monospace;font-size:12px;}
  .text-card.wechat{--ch:#10b981;--ch-bg:#d1fae5;}
  .text-card.zhihu{--ch:#1a56db;--ch-bg:#dbeafe;}
  .flow{background:#fff;border-radius:14px;padding:24px;border:1px solid #e2e8f0;}
  .flow ol{margin:8px 0 0 20px;}
  .flow li{font-size:14px;color:#334155;margin:10px 0;line-height:1.75;}
  .flow code{background:#f1f5f9;color:#1e40af;padding:2px 7px;border-radius:4px;font-family:Consolas,Monaco,monospace;font-size:12.5px;}
  footer{text-align:center;padding:24px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;background:#fff;margin-top:40px;}
  footer a{color:#f59e0b;}
</style>
</head>
<body>

<nav class="topbar"><div class="topbar-inner">
  <a href="../../../index.html">🏠 综合站首页</a>
  <span class="sep">›</span>
  <a href="../../index.html">运营中心</a>
  <span class="sep">›</span>
  <a href="index.html" style="color:#475569;">units/</a>
  <span class="sep">›</span>
  <span class="here">__SLUG__</span>
  <span style="margin-left:auto;font-size:12px;color:#94a3b8;">v3.1</span>
</div></nav>

<header class="hero"><div class="hero-inner">
  <div class="hero-row">
    <div class="hero-num">__NUMBER__</div>
    <div class="hero-main">
      <span class="hero-tag">📦 发布单元 · __TAG__</span>
      <h1>__TITLE__</h1>
      <p>__SUBTITLE__</p>
      <div class="hero-stats">
        <div class="hero-stat"><div class="hero-stat-num">__WORDS__</div><div class="hero-stat-label">原文字数</div></div>
        <div class="hero-stat"><div class="hero-stat-num">2</div><div class="hero-stat-label">渠道成稿</div></div>
        <a class="source-link" href="../../../articles/__SOURCE_HTML__" target="_blank">📄 查看原文 HTML</a>
      </div>
    </div>
  </div>
</div></header>

<main class="container">

  <section class="section">
    <div class="section-head">
      <h2 class="section-title">📝 文字成稿 <span>—— 浏览器复制 → 粘贴到对应平台</span></h2>
    </div>
    <div class="grid-2">
      <div class="text-card wechat">
        <div class="text-card-head">
          <div class="text-card-icon">📢</div>
          <div class="text-card-channel">WECHAT · 公众号</div>
        </div>
        <div class="text-card-title">公众号成稿（HTML 带样式版）</div>
        <p style="font-size:13.5px;color:#475569;">浏览器打开 HTML → 全选复制 → 粘贴到公众号编辑器，样式全保留。</p>
        <div class="text-card-file">__WECHAT_HTML__</div>
        <div class="text-card-actions">
          <a class="btn btn-primary" href="../wechat/__WECHAT_HTML__" target="_blank">📄 浏览器打开</a>
          <a class="btn btn-ghost" href="../wechat/__WECHAT_HTML__" download>💾 下载 HTML</a>
        </div>
        <div class="text-card-tip">💡 <strong>粘贴流程</strong>：浏览器打开 → <code>Ctrl+A</code> 全选 → <code>Ctrl+C</code> 复制 → 公众号后台 → 新建图文 → <code>Ctrl+V</code></div>
      </div>
      <div class="text-card zhihu">
        <div class="text-card-head">
          <div class="text-card-icon">💡</div>
          <div class="text-card-channel">ZHIHU · 知乎</div>
        </div>
        <div class="text-card-title">知乎成稿（Markdown 原生版）</div>
        <p style="font-size:13.5px;color:#475569;">知乎专栏编辑器原生支持 Markdown 粘贴。</p>
        <div class="text-card-file">__ZHIHU_MD__</div>
        <div class="text-card-actions">
          <a class="btn btn-primary" href="../zhihu/__ZHIHU_MD__" target="_blank">📝 查看 Markdown</a>
          <a class="btn btn-ghost" href="../zhihu/__ZHIHU_MD__" download>💾 下载 .md</a>
        </div>
        <div class="text-card-tip">💡 <strong>粘贴流程</strong>：用编辑器打开 .md → 全选复制 → 知乎"写文章" → 粘贴</div>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="section-head"><h2 class="section-title">🚀 发布流程</h2></div>
    <div class="flow">
      <ol>
        <li><strong>公众号</strong>：浏览器打开 HTML → <code>Ctrl+A</code> + <code>Ctrl+C</code> → 公众号后台新建图文 → <code>Ctrl+V</code> → 推送</li>
        <li><strong>知乎</strong>：查看 Markdown → 全选复制 → <a href="https://zhuanlan.zhihu.com" target="_blank">知乎专栏</a> 写新文章 → 粘贴 → 发布</li>
      </ol>
    </div>
  </section>

  <section class="section">
    <div class="section-head"><h2 class="section-title">🔗 相关</h2></div>
    <div class="flow" style="font-size:13.5px;line-height:2.1;">
      📄 <a href="../../../articles/__SOURCE_HTML__" target="_blank" style="color:#1e40af;font-weight:600;">原文 HTML（articles/__SOURCE_HTML__）</a><br>
      🛠️ <a href="../../tools/convert_single.py" style="color:#1e40af;font-weight:600;">convert_single.py</a> · 重新生成成稿用<br>
      📦 <a href="index.html" style="color:#1e40af;font-weight:600;">回到发布单元总览</a>
    </div>
  </section>

</main>

<footer>
  <div>__TITLE__ · 发布单元 v3.1</div>
  <div style="margin-top:8px;">
    <a href="../../../index.html">综合站首页</a> · 
    <a href="../../index.html">运营中心</a> · 
    <a href="index.html">所有发布单元</a>
  </div>
</footer>

</body>
</html>
"""


def gen_unit_page(unit):
    html = UNIT_TPL
    for k, v in {
        '__TITLE__': unit['title'], '__SUBTITLE__': unit['subtitle'],
        '__SLUG__': unit['slug'], '__NUMBER__': unit['number'],
        '__TAG__': unit['tag'], '__WORDS__': unit['words'],
        '__SOURCE_HTML__': unit['source_html'],
        '__WECHAT_HTML__': unit['wechat_html'],
        '__ZHIHU_MD__': unit['zhihu_md'],
        '__HERO_A__': unit['hero_a'], '__HERO_B__': unit['hero_b'],
    }.items():
        html = html.replace(k, v)
    out_dir = 'insurance-guide/operations/published/units'
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{unit["slug"]}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)


# ============== 3. units/index.html 总览 ==============
UNITS_INDEX_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>发布单元总览 · 运营中心</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1e293b;background:#f8fafc;line-height:1.65;}
  a{color:inherit;text-decoration:none;}
  .topbar{background:#fff;padding:14px 24px;border-bottom:1px solid #e2e8f0;position:sticky;top:0;z-index:10;}
  .topbar-inner{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:12px;font-size:14px;}
  .topbar a{color:#475569;font-weight:500;}
  .topbar a:hover{color:#f59e0b;}
  .topbar .here{color:#f59e0b;font-weight:700;}
  .topbar .sep{color:#cbd5e1;}
  .hero{background:linear-gradient(135deg,#92400e 0%,#f59e0b 100%);color:#fff;padding:50px 24px 60px;}
  .hero-inner{max-width:1180px;margin:0 auto;}
  .hero-tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:1.5px;background:rgba(255,255,255,0.18);padding:5px 12px;border-radius:12px;margin-bottom:14px;}
  .hero h1{font-size:32px;font-weight:800;margin-bottom:8px;}
  .hero p{font-size:15px;opacity:0.92;line-height:1.7;max-width:760px;}
  .container{max-width:1180px;margin:-30px auto 0;padding:0 24px 80px;position:relative;z-index:2;}
  .unit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:18px;}
  .unit-card{background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0;transition:all 0.2s;display:flex;flex-direction:column;}
  .unit-card:hover{transform:translateY(-3px);box-shadow:0 12px 28px rgba(15,23,42,0.1);border-color:#f59e0b;}
  .unit-card-banner{aspect-ratio:9/5;background:linear-gradient(135deg,var(--bg-a),var(--bg-b));display:flex;align-items:center;justify-content:center;color:#fff;position:relative;overflow:hidden;}
  .unit-card-banner::before{content:'';position:absolute;top:-30%;right:-10%;width:300px;height:300px;background:radial-gradient(circle,rgba(255,255,255,0.15) 0%,transparent 70%);border-radius:50%;}
  .unit-card-banner-num{font-size:96px;font-weight:900;color:rgba(255,255,255,0.95);letter-spacing:-3px;line-height:1;position:relative;z-index:1;}
  .unit-card-body{padding:18px 20px;flex:1;display:flex;flex-direction:column;}
  .unit-card-tag{display:inline-block;font-size:11px;font-weight:700;background:#fef3c7;color:#92400e;padding:3px 10px;border-radius:10px;margin-bottom:8px;align-self:flex-start;}
  .unit-card-title{font-size:16px;font-weight:700;color:#0f172a;margin-bottom:6px;line-height:1.4;}
  .unit-card-desc{font-size:13px;color:#64748b;line-height:1.6;flex:1;}
  .unit-card-stats{display:flex;gap:14px;margin-top:12px;padding-top:12px;border-top:1px solid #f1f5f9;font-size:12px;color:#94a3b8;}
  .unit-card-stats span strong{color:#0f172a;}
  footer{text-align:center;padding:24px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;background:#fff;margin-top:40px;}
  footer a{color:#f59e0b;}
</style>
</head>
<body>

<nav class="topbar"><div class="topbar-inner">
  <a href="../../../index.html">🏠 综合站首页</a>
  <span class="sep">›</span>
  <a href="../../index.html">运营中心</a>
  <span class="sep">›</span>
  <span style="color:#94a3b8;">published/</span>
  <span class="sep">›</span>
  <span class="here">units/</span>
  <span style="margin-left:auto;font-size:12px;color:#94a3b8;">v3.1</span>
</div></nav>

<header class="hero"><div class="hero-inner">
  <span class="hero-tag">📦 PUBLISH UNITS</span>
  <h1>发布单元总览 · 共 __TOTAL__ 个</h1>
  <p>每个「发布单元」= 一篇文章的全部物料：公众号成稿 + 知乎成稿 + 使用流程。一处汇总，一键发布。</p>
</div></header>

<main class="container">
  <div class="unit-grid">
__UNIT_CARDS__
  </div>
</main>

<footer>
  <div>发布单元总览 · 运营中心 v3.1</div>
  <div style="margin-top:8px;"><a href="../../../index.html">综合站首页</a> · <a href="../../index.html">运营中心</a></div>
</footer>

</body>
</html>
"""


def unit_card(unit):
    return f"""    <a class="unit-card" href="{unit['slug']}.html" style="--bg-a:{unit['hero_a']};--bg-b:{unit['hero_b']};">
      <div class="unit-card-banner"><div class="unit-card-banner-num">{unit['number']}</div></div>
      <div class="unit-card-body">
        <span class="unit-card-tag">{unit['tag']}</span>
        <div class="unit-card-title">{unit['title']}</div>
        <div class="unit-card-desc">{unit['subtitle']}</div>
        <div class="unit-card-stats">
          <span>📝 <strong>{unit['words']}</strong> 字</span>
          <span>📢 公众号 + 知乎</span>
        </div>
      </div>
    </a>"""


def gen_units_index():
    cards = '\n'.join(unit_card(u) for u in UNITS)
    html = UNITS_INDEX_TPL.replace('__UNIT_CARDS__', cards).replace('__TOTAL__', str(len(UNITS)))
    out = 'insurance-guide/operations/published/units/index.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[OK] {out}  ({len(UNITS)} units)')


# ============== 4. 更新主 dashboard 计数 ==============
def update_dashboard_counts():
    wechat_count = len([f for f in os.listdir('insurance-guide/operations/published/wechat')
                        if f.endswith(('.html', '.md')) and f != 'index.html'])
    zhihu_count = len([f for f in os.listdir('insurance-guide/operations/published/zhihu')
                       if f.endswith('.md') and f != 'index.html'])

    p = 'insurance-guide/index.html'
    with open(p, 'r', encoding='utf-8') as f: c = f.read()
    c = re.sub(r'<span class="card-badge green">\d+ 篇 · 可直接发</span>',
               f'<span class="card-badge green">{wechat_count} 篇 · 可直接发</span>', c)
    c = re.sub(r'<span class="card-badge">\d+ 篇 · 可直接发</span>',
               f'<span class="card-badge">{zhihu_count} 篇 · 可直接发</span>', c)
    with open(p, 'w', encoding='utf-8') as f: f.write(c)

    p = 'insurance-guide/operations/index.html'
    with open(p, 'r', encoding='utf-8') as f: c = f.read()
    c = re.sub(r'<span class="card-badge green">\d+ 篇可直发</span>',
               f'<span class="card-badge green">{wechat_count} 篇可直发</span>', c)
    c = re.sub(r'<span class="card-badge blue">\d+ 篇可直发</span>',
               f'<span class="card-badge blue">{zhihu_count} 篇可直发</span>', c)
    c = re.sub(r'已就绪 \d+ 个单元', f'已就绪 {len(UNITS)} 个单元', c)
    with open(p, 'w', encoding='utf-8') as f: f.write(c)

    print(f'[OK] 计数: 公众号 {wechat_count} 篇, 知乎 {zhihu_count} 篇, 单元 {len(UNITS)} 个')


def main():
    gen_channel_index(
        'insurance-guide/operations/published/wechat', 'wechat',
        '公众号成稿仓库', 'OPERATIONS · WECHAT',
        '可直接发布的公众号稿件 · HTML 带样式版 + Markdown 双格式。',
        '#10b981', '#047857', '#10b981',
        '<b>HTML 文件</b>：浏览器打开 → Ctrl+A 全选 → Ctrl+C 复制 → 粘贴到公众号编辑器。<br>'
        '<b>MD 文件</b>：源 Markdown，用 <code>operations/tools/convert_single.py</code> 可重新生成。',
        WECHAT_DESC,
    )
    gen_channel_index(
        'insurance-guide/operations/published/zhihu', 'zhihu',
        '知乎成稿仓库', 'OPERATIONS · ZHIHU',
        '可直接发布的知乎稿件 · Markdown 原生格式。',
        '#1a56db', '#1e3a8a', '#3b82f6',
        '<b>知乎编辑器</b>原生支持 Markdown 粘贴。',
        ZHIHU_DESC,
    )
    for u in UNITS:
        gen_unit_page(u)
    print(f'[OK] {len(UNITS)} 个发布单元页生成')
    gen_units_index()
    update_dashboard_counts()


if __name__ == '__main__':
    main()
