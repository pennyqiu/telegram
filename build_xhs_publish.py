# -*- coding: utf-8 -*-
"""
小红书发布操作台生成器
========================
解决问题：从 HTML 文章页直接复制到小红书时，段落空行被吃掉，所有内容粘成一坨。

输出：
1. insurance-guide/articles/xhs-publish/xhs01.txt ~ xhs39.txt
   每篇 1 个纯文本，已按小红书最佳格式排版（标题 + 正文 + CTA + 话题标签），
   全选复制粘贴到小红书即可，换行 / 段落间距完美保留。

2. insurance-guide/articles/xhs-publish/index.html
   发布操作台 hub 页：每篇 1 个卡片，含【📋 一键复制】+【📥 下载 .txt】+【👁️ 预览】按钮。
   把这一页固定收藏在浏览器，每次发文打开 → 选篇 → 一键复制 → 切到小红书粘贴。

数据来源：
- #1：解析 insurance-guide/articles/v22-xhs01.html
- #2 - #39：从 build_xhs_articles.ARTICLES 导入
"""
import os
import re
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, '.')
from build_xhs_articles import ARTICLES

ROOT = Path('insurance-guide/articles')
OUT_DIR = ROOT / 'xhs-publish'
OUT_DIR.mkdir(exist_ok=True)

SHORT_BODIES_FILE = Path('xhs_short_bodies.md')

# ==========================================================
# 精简版正文加载（覆盖原 ARTICLES.body）
# ==========================================================
def load_short_bodies():
    """
    解析 xhs_short_bodies.md，按 ## #NN 标题切分。
    返回 {num:int -> body:str}
    """
    if not SHORT_BODIES_FILE.exists():
        return {}
    text = SHORT_BODIES_FILE.read_text(encoding='utf-8')
    # 按 ## #NN 切分
    parts = re.split(r'^##\s+#(\d{2})\s*$', text, flags=re.MULTILINE)
    # parts[0] = 文件头部说明（丢弃）
    # 之后是 [num, body, num, body, ...]
    result = {}
    for i in range(1, len(parts), 2):
        num = int(parts[i])
        body = parts[i+1].strip() if i+1 < len(parts) else ''
        if body:
            result[num] = body
    return result

# ==========================================================
# 月度分组（与 hub 页一致）
# ==========================================================
MONTHS = [
    {'label': 'M1 · 人设破圈月', 'desc': '建立『CPA 转身做港险』人设',  'range': (1, 6)},
    {'label': 'M2 · 科技中产月', 'desc': '互联网中层痛点 + 解法',         'range': (7, 12)},
    {'label': 'M3 · 教育金月',   'desc': '跨境家庭教育金规划',          'range': (13, 19)},
    {'label': 'M4 · 税务月',     'desc': 'CRS / 税务身份 / 跨境合规',     'range': (20, 25)},
    {'label': 'M5 · 产品月',     'desc': '储蓄 / 危疾 / 美元资产深拆',    'range': (26, 31)},
    {'label': 'M6 · 案例月',     'desc': '客户故事 + 综合诊断',          'range': (32, 39)},
]

# ==========================================================
# 解析 #1（v22-xhs01.html 是 markdown 转 HTML，内容在 <pre><code> 块里）
# ==========================================================
def _section(c, start_label, end_label=None):
    s = re.search(r'<h2[^>]*>' + re.escape(start_label) + r'.*?</h2>', c)
    if not s:
        return ''
    start = s.end()
    if end_label:
        e = re.search(r'<h2[^>]*>' + re.escape(end_label) + r'.*?</h2>', c[start:])
        end = start + e.start() if e else len(c)
    else:
        end = len(c)
    return c[start:end]


def _first_pre_code(section_html):
    """提取 section 里的第一个 <pre><code>...</code></pre> 块的文本"""
    m = re.search(r'<pre><code>(.+?)</code></pre>', section_html, re.DOTALL)
    if not m:
        return ''
    text = m.group(1)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return text.strip()


def parse_xhs01():
    fp = ROOT / 'v22-xhs01.html'
    c = fp.read_text(encoding='utf-8')

    body = _first_pre_code(_section(c, '四、正文', '五、'))
    # #1 的正文里已经含 CTA（评论区扣【30问】），第五节是『评论区私信秒回模板』
    # —— 那是回复客户用的，不发到帖子里。所以这里不附加 CTA。
    cta  = ''
    tag_block = _first_pre_code(_section(c, '七、', '八、'))
    tags = re.findall(r'#([^\s#]+)', tag_block)
    if not tags:
        tags = ['香港保险', '港险', '保险经纪', '安盛保险', '家庭理财',
                '资产配置', '美元资产', '财富管理', '理财规划', 'CPA',
                '深圳生活', '大湾区', '避坑指南']

    return {
        'num': 1,
        'week': 1,
        'day': '周三',
        'type': '⚪',
        'title': '内地人去香港买保险，到底合不合法？CPA 给你说清楚',
        'body': body or '（解析失败：请检查 v22-xhs01.html 的 <pre><code> 节）',
        'cta': cta,
        'tags': tags[:13],
    }

# ==========================================================
# 构建小红书发布版纯文本
# ==========================================================
def normalize(text):
    """把 \r\n / 多余空行规整化"""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def build_publish_text(a):
    """
    小红书最佳格式：
    标题 + 空行 + 正文 + 空行 + CTA + 空行 + #话题标签
    """
    parts = []
    parts.append(a['title'].strip())
    parts.append('')
    parts.append(normalize(a['body']))
    if a.get('cta'):
        parts.append('')
        parts.append(normalize(a['cta']))
    if a.get('tags'):
        parts.append('')
        # 小红书有效标签上限 10 个，多了不识别 → 截到前 10
        parts.append(' '.join(f'#{t}' for t in a['tags'][:10]))
    return '\n'.join(parts) + '\n'

# ==========================================================
# Hub 页 HTML
# ==========================================================
HUB_TPL = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>小红书发布操作台 · 39 篇一键复制 · 香港保险从业全景指南</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:"PingFang SC","Microsoft YaHei",-apple-system,sans-serif;background:#f1f5f9;color:#0f172a;line-height:1.6;padding-bottom:80px}
  .top-bar{position:sticky;top:0;z-index:50;background:#0f172a;color:#fff;padding:14px 28px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;box-shadow:0 1px 0 #1e293b}
  .top-bar a{color:#fbbf24;text-decoration:none;font-size:14px;font-weight:600}
  .top-bar a:hover{color:#fde68a}
  .top-bar-meta{font-size:12px;color:#94a3b8;letter-spacing:1px}
  .hero{background:linear-gradient(135deg,#1e3a5f,#1a56db);color:#fff;padding:48px 28px}
  .hero-inner{max-width:1100px;margin:0 auto}
  .hero-tag{display:inline-block;background:rgba(251,191,36,0.95);color:#78350f;font-size:12px;font-weight:700;letter-spacing:1px;padding:5px 12px;border-radius:14px;margin-bottom:16px}
  .hero h1{font-size:32px;font-weight:800;letter-spacing:-0.5px;margin-bottom:14px;line-height:1.3}
  .hero h1 em{color:#fbbf24;font-style:normal}
  .hero p{font-size:15px;color:#dbeafe;line-height:1.8;max-width:760px}
  .hero-stats{display:flex;gap:36px;margin-top:24px;flex-wrap:wrap}
  .hero-stat-num{font-size:30px;font-weight:800;color:#fbbf24}
  .hero-stat-label{font-size:12px;color:#cbd5e1;letter-spacing:1px;margin-top:4px}
  .howto{max-width:1100px;margin:32px auto 0;padding:0 28px}
  .howto-card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:24px 28px}
  .howto-card h2{font-size:18px;color:#1e3a5f;margin-bottom:14px;display:flex;align-items:center;gap:10px}
  .howto-card h2 .badge{background:#fbbf24;color:#78350f;font-size:11px;padding:3px 9px;border-radius:10px;font-weight:700;letter-spacing:1px}
  .howto-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:8px}
  .howto-step{background:#f8fafc;border-left:3px solid #1a56db;padding:14px 16px;border-radius:0 8px 8px 0}
  .howto-step-num{font-size:11px;color:#1a56db;font-weight:700;letter-spacing:1px;margin-bottom:4px}
  .howto-step-text{font-size:13px;color:#334155;line-height:1.65}
  .howto-step-text code{background:#e0e7ff;color:#3730a3;padding:1px 6px;border-radius:3px;font-family:"SF Mono",monospace;font-size:12px}

  .container{max-width:1100px;margin:32px auto;padding:0 28px}
  .month-block{margin-bottom:36px}
  .month-head{display:flex;align-items:baseline;gap:14px;margin-bottom:14px;padding-bottom:10px;border-bottom:2px solid #e2e8f0;flex-wrap:wrap}
  .month-label{font-size:18px;font-weight:800;color:#1e3a5f;letter-spacing:-0.3px}
  .month-desc{font-size:13px;color:#64748b}
  .month-count{margin-left:auto;font-size:12px;color:#94a3b8}

  .article-list{display:grid;grid-template-columns:1fr;gap:10px}
  .article-row{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;display:flex;align-items:center;gap:14px;transition:all 0.15s;flex-wrap:wrap}
  .article-row:hover{border-color:#1a56db;box-shadow:0 2px 12px rgba(30,86,219,0.08)}
  .article-num{flex-shrink:0;width:36px;height:36px;background:#1e3a5f;color:#fff;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
  .article-num.green{background:#10b981}
  .article-num.blue{background:#0ea5e9}
  .article-num.gray{background:#6b7280}
  .article-num.purple{background:#8b5cf6}
  .article-info{flex:1;min-width:200px}
  .article-title{font-size:14px;font-weight:600;color:#0f172a;margin-bottom:3px;line-height:1.4}
  .article-meta{font-size:11px;color:#94a3b8;letter-spacing:0.5px}
  .article-actions{display:flex;gap:6px;flex-wrap:wrap}
  .btn{font-family:inherit;font-size:12px;font-weight:600;border:none;cursor:pointer;padding:7px 12px;border-radius:6px;text-decoration:none;display:inline-flex;align-items:center;gap:5px;transition:all 0.15s}
  .btn-primary{background:#1a56db;color:#fff}
  .btn-primary:hover{background:#1e40af}
  .btn-primary.copied{background:#10b981}
  .btn-ghost{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0}
  .btn-ghost:hover{background:#e2e8f0;color:#0f172a}

  /* Toast */
  .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(120%);background:#10b981;color:#fff;padding:14px 24px;border-radius:10px;font-size:14px;font-weight:600;box-shadow:0 8px 24px rgba(16,185,129,0.3);transition:transform 0.3s ease;z-index:200}
  .toast.show{transform:translateX(-50%) translateY(0)}

  /* Modal */
  .modal-mask{position:fixed;inset:0;background:rgba(15,23,42,0.7);backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:100;padding:20px}
  .modal-mask.show{display:flex}
  .modal{background:#fff;border-radius:16px;max-width:680px;width:100%;max-height:85vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,0.4)}
  .modal-head{padding:18px 22px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;gap:14px}
  .modal-title{font-size:15px;font-weight:700;color:#1e3a5f}
  .modal-close{background:none;border:none;font-size:24px;cursor:pointer;color:#94a3b8;line-height:1;padding:0 4px}
  .modal-close:hover{color:#0f172a}
  .modal-body{padding:20px 22px;overflow-y:auto;flex:1}
  .modal-body pre{font-family:"PingFang SC","Microsoft YaHei",monospace;font-size:13px;line-height:1.85;color:#0f172a;white-space:pre-wrap;word-wrap:break-word;background:#f8fafc;padding:18px 20px;border-radius:8px;border:1px solid #e2e8f0;max-height:none}
  .modal-foot{padding:14px 22px;background:#f8fafc;border-top:1px solid #e2e8f0;display:flex;gap:10px;justify-content:flex-end}

  @media (max-width:640px){
    .hero h1{font-size:24px}
    .hero p{font-size:14px}
    .article-row{flex-direction:column;align-items:stretch}
    .article-actions{justify-content:flex-end}
  }
</style>
</head>
<body>

<div class="top-bar">
  <a href="../v22-xhs-hub.html">← 返回 39 篇日历</a>
  <span class="top-bar-meta">小红书发布操作台 · v1.0</span>
</div>

<div class="hero">
  <div class="hero-inner">
    <span class="hero-tag">作战物料 · 一键复制</span>
    <h1>小红书发布操作台 · <em>39 篇一键复制</em></h1>
    <p>每篇文章已按小红书最佳格式排版好（标题 + 正文 + CTA + 话题标签），点击【📋 一键复制】→ 切到小红书粘贴 → 段落、空行、emoji 完美保留。再也不用手动调格式。</p>
    <div class="hero-stats">
      <div><div class="hero-stat-num">39</div><div class="hero-stat-label">篇 · 全部就绪</div></div>
      <div><div class="hero-stat-num">≈3 秒</div><div class="hero-stat-label">复制 + 粘贴 = 发布</div></div>
      <div><div class="hero-stat-num">100%</div><div class="hero-stat-label">换行 / 空行保真</div></div>
    </div>
  </div>
</div>

<div class="howto">
  <div class="howto-card">
    <h2>使用说明 <span class="badge">建议收藏本页</span></h2>
    <div class="howto-list">
      <div class="howto-step"><div class="howto-step-num">STEP 1</div><div class="howto-step-text">挑出你今天要发的那一篇（按月度日历顺序）</div></div>
      <div class="howto-step"><div class="howto-step-num">STEP 2</div><div class="howto-step-text">点击右侧 <code>📋 一键复制</code> → 浏览器弹绿色提示『已复制』</div></div>
      <div class="howto-step"><div class="howto-step-num">STEP 3</div><div class="howto-step-text">打开小红书创作中心 → 上传 9 张图 → 在正文区按 <code>Ctrl+V</code> 粘贴</div></div>
      <div class="howto-step"><div class="howto-step-num">STEP 4</div><div class="howto-step-text">补图（可用 Figma 或 visuals 底稿）→ 点发布。完。</div></div>
    </div>
  </div>
</div>

<div class="container">
__MONTH_BLOCKS__
</div>

<div id="toast" class="toast">✓ 已复制到剪贴板</div>

<div id="modal" class="modal-mask">
  <div class="modal">
    <div class="modal-head">
      <div class="modal-title" id="modal-title">预览</div>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body"><pre id="modal-body-text"></pre></div>
    <div class="modal-foot">
      <button class="btn btn-ghost" onclick="closeModal()">关闭</button>
      <button class="btn btn-primary" id="modal-copy-btn" onclick="modalCopy()">📋 复制全文</button>
    </div>
  </div>
</div>

<script>
const PUBLISH_DATA = __PUBLISH_DATA__;

function showToast(msg, ok=true){
  const t = document.getElementById('toast');
  t.textContent = (ok?'✓ ':'✗ ') + msg;
  t.style.background = ok ? '#10b981' : '#dc2626';
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'), 1800);
}

async function copyArticle(num, btn){
  const text = PUBLISH_DATA[num];
  if(!text){ showToast('未找到内容', false); return; }
  try {
    await navigator.clipboard.writeText(text);
    if(btn){
      const old = btn.innerHTML;
      btn.innerHTML = '✓ 已复制';
      btn.classList.add('copied');
      setTimeout(()=>{ btn.innerHTML = old; btn.classList.remove('copied'); }, 1500);
    }
    showToast('第 ' + num + ' 篇已复制 · 切到小红书粘贴即可');
  } catch(e){
    fallbackCopy(text);
    showToast('已用兜底方式复制');
  }
}

function fallbackCopy(text){
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
}

let currentModalNum = null;
function openModal(num, title){
  currentModalNum = num;
  document.getElementById('modal-title').textContent = '#' + num + ' · ' + title;
  document.getElementById('modal-body-text').textContent = PUBLISH_DATA[num] || '(未找到内容)';
  document.getElementById('modal').classList.add('show');
}
function closeModal(){
  document.getElementById('modal').classList.remove('show');
}
function modalCopy(){
  if(currentModalNum != null){
    copyArticle(currentModalNum, document.getElementById('modal-copy-btn'));
  }
}
document.getElementById('modal').addEventListener('click', (e)=>{
  if(e.target.id === 'modal') closeModal();
});
document.addEventListener('keydown', (e)=>{
  if(e.key === 'Escape') closeModal();
});
</script>

</body>
</html>
'''


def render_hub(all_articles, publish_map):
    type_to_class = {'🟢': 'green', '🔵': 'blue', '⚪': 'gray', '🟣': 'purple'}
    blocks = []
    for m in MONTHS:
        lo, hi = m['range']
        items = [a for a in all_articles if lo <= a['num'] <= hi]
        if not items:
            continue
        rows = []
        for a in items:
            cls = type_to_class.get(a.get('type', '⚪'), 'gray')
            t_safe = html.escape(a['title'])
            t_attr = a['title'].replace('"', '&quot;').replace("'", "\\'")
            week = a.get('week', '')
            day = a.get('day', '')
            type_label = a.get('type', '⚪')
            rows.append(f'''      <div class="article-row">
        <div class="article-num {cls}">{a['num']}</div>
        <div class="article-info">
          <div class="article-title">{t_safe}</div>
          <div class="article-meta">{type_label} · W{week} · {day} · {len(publish_map[a['num']])} 字（含标签）</div>
        </div>
        <div class="article-actions">
          <button class="btn btn-ghost" onclick="openModal({a['num']}, '{t_attr}')">👁️ 预览</button>
          <a class="btn btn-ghost" href="xhs{a['num']:02d}.txt" download>📥 .txt</a>
          <button class="btn btn-primary" onclick="copyArticle({a['num']}, this)">📋 一键复制</button>
        </div>
      </div>''')

        block = f'''<div class="month-block">
  <div class="month-head">
    <span class="month-label">{m['label']}</span>
    <span class="month-desc">{m['desc']}</span>
    <span class="month-count">{len(items)} 篇</span>
  </div>
  <div class="article-list">
{chr(10).join(rows)}
  </div>
</div>'''
        blocks.append(block)

    publish_json = json.dumps(publish_map, ensure_ascii=False)

    html_out = HUB_TPL.replace('__MONTH_BLOCKS__', '\n'.join(blocks))
    html_out = html_out.replace('__PUBLISH_DATA__', publish_json)
    return html_out

# ==========================================================
# 主流程
# ==========================================================
def main():
    art1 = parse_xhs01()
    all_articles = [art1] + ARTICLES

    short_bodies = load_short_bodies()
    overridden = []
    if short_bodies:
        for a in all_articles:
            if a['num'] in short_bodies:
                a['body'] = short_bodies[a['num']]
                # 精简版自带内嵌 CTA 钩子，不再附加原长版 CTA
                a['cta'] = ''
                overridden.append(a['num'])

    publish_map = {}
    for a in all_articles:
        text = build_publish_text(a)
        publish_map[a['num']] = text
        fp = OUT_DIR / f'xhs{a["num"]:02d}.txt'
        fp.write_text(text, encoding='utf-8')

    hub_html = render_hub(all_articles, publish_map)
    (OUT_DIR / 'index.html').write_text(hub_html, encoding='utf-8')

    txt_count = len([1 for a in all_articles])
    avg_len = sum(len(t) for t in publish_map.values()) / len(publish_map)
    over = [(n, len(t)) for n, t in publish_map.items() if len(t) > 1000]
    print(f'[OK] 已生成 {txt_count} 个 .txt 文件 + 1 个 hub 页')
    print(f'     输出目录: {OUT_DIR}')
    print(f'     平均长度: {avg_len:.0f} 字 / 篇')
    print(f'     hub 页 : {OUT_DIR / "index.html"}')
    print()
    if overridden:
        print(f'[精简版已应用] {len(overridden)} 篇：{overridden}')
    if over:
        print(f'[字数超 1000] 还有 {len(over)} 篇待精简：')
        for n, length in sorted(over, key=lambda x: -x[1])[:10]:
            print(f'       #{n:02d} · {length} 字（超 {length-1000}）')
        if len(over) > 10:
            print(f'       ... 还有 {len(over)-10} 篇')
    else:
        print('[字数全部达标] ✓ 全部 39 篇都在 1000 字内')


if __name__ == '__main__':
    main()
