#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「美股持仓复盘」目录下的所有 Markdown 文档打包成一个可离线浏览的单页网站。

用法：
    python tools/build_site.py

产物：
    站点/index.html   —— 自包含单文件（Markdown 内容以 base64 内嵌，双击即可打开，
                          也可随仓库部署到静态托管上查看）。

设计要点：
- 内容 base64 内嵌，避免 file:// 下 fetch 跨域问题，双击本地文件即可查看。
- 文档改动后重新运行本脚本即可刷新站点。
- 仅做「查看器」，不硬编码任何行情/持仓数字，避免站点与文档脱节。
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
from pathlib import Path

# 复盘根目录 = 本脚本的上级目录
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "站点"
OUT_FILE = OUT_DIR / "index.html"

# 分组显示名与排序权重（数字越小越靠前）
GROUP_ORDER = {
    "核心文档": 0,
    "标的档案": 1,
    "预选标的": 2,
    "操作手册": 3,
    "期权专题": 4,
    "历史复盘": 5,
    "提示词与模板": 6,
    "工具": 7,
    "其他": 9,
}

# 核心文档内部的优先排序（未列出的按文件名排在其后）
CORE_ORDER = [
    "README.md",
    "投资规则卡.md",
    "决策日志.md",
    "主动策略-回撤响应阶梯.md",
    "持仓快照-模板.md",
    "月度快速复盘提示词.md",
    "年度审计提示词.md",
    "美股持仓深度分析提示词.md",
]

# 标的档案内部优先排序（大致按穿透仓位；仅已持仓）
SYMBOL_ORDER = [
    "MSFT.md", "TSM.md", "NVDA.md", "GOOG.md", "META.md",
    "QCOM.md", "ETF-宽基与主题.md", "_模板.md",
]

# 预选标的内部排序（索引在前，其后按前瞻 → 隐形）
CANDIDATE_ORDER = [
    "候选清单.md",
    "MA.md", "V.md", "JPM.md",
    "AAPL.md", "AMZN.md", "MU.md",
]

# 期权专题讨论区：README 作为着陆页，其余按编号
OPTIONS_ORDER = ["README.md"]

# 提示词/模板类文件名关键词
PROMPT_KEYWORDS = ("提示词", "模板")


def classify(rel: Path) -> tuple[str, int]:
    """返回 (分组名, 组内排序权重)。"""
    parts = rel.parts
    name = rel.name

    if parts[0] == "标的档案":
        # 子目录 标的档案/预选标的/ → 单独分组，不与已持仓混排
        if len(parts) >= 2 and parts[1] == "预选标的":
            idx = CANDIDATE_ORDER.index(name) if name in CANDIDATE_ORDER else 100
            return "预选标的", idx
        idx = SYMBOL_ORDER.index(name) if name in SYMBOL_ORDER else 100
        return "标的档案", idx
    if parts[0] == "历史复盘":
        # 复盘报告按日期倒序（新的在前）
        return "历史复盘", -_date_key(name)
    if parts[0] == "playbooks":
        return "操作手册", 0
    if parts[0] == "期权专题":
        # README 置顶，其余靠文件名前缀的编号自然排序
        return "期权专题", OPTIONS_ORDER.index(name) if name in OPTIONS_ORDER else 100
    if parts[0] == "tools":
        return "工具", 0

    # 顶层文件
    if len(parts) == 1:
        if any(k in name for k in PROMPT_KEYWORDS):
            return "提示词与模板", 0
        idx = CORE_ORDER.index(name) if name in CORE_ORDER else 50
        return "核心文档", idx
    return "其他", 0


def _date_key(name: str) -> int:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if not m:
        return 0
    return int("".join(m.groups()))


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def collect_docs() -> list[dict]:
    docs = []
    for md in ROOT.rglob("*.md"):
        rel = md.relative_to(ROOT)
        # 跳过站点自身、隐藏目录
        if rel.parts[0] in ("站点",):
            continue
        if any(p.startswith(".") for p in rel.parts):
            continue
        text = md.read_text(encoding="utf-8")
        group, order = classify(rel)
        title = extract_title(text, md.stem)
        docs.append({
            "id": str(rel).replace("\\", "/"),
            "title": title,
            "group": group,
            "group_order": GROUP_ORDER.get(group, 9),
            "order": order,
            "path": str(rel).replace("\\", "/"),
            "b64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        })
    docs.sort(key=lambda d: (d["group_order"], d["order"], d["title"]))
    return docs


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>美股持仓复盘 · 文档中心</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root{
  --bg:#0f1419; --panel:#171d26; --panel2:#1e2632; --border:#2a3441;
  --text:#e6edf3; --muted:#8b98a8; --accent:#4f9cff; --accent2:#31d0aa;
  --red:#ff6b6b; --green:#31d0aa; --amber:#f5b544;
  --sidebar-w:280px;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.7}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* 布局 */
.app{display:flex;height:100vh;overflow:hidden}
.sidebar{width:var(--sidebar-w);flex:0 0 var(--sidebar-w);background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.brand{padding:18px 18px 12px;border-bottom:1px solid var(--border)}
.brand h1{font-size:16px;margin:0 0 4px}
.brand .sub{font-size:12px;color:var(--muted)}
.search{padding:12px 14px;border-bottom:1px solid var(--border)}
.search input{width:100%;padding:8px 10px;background:var(--panel2);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px}
.nav{overflow-y:auto;flex:1;padding:8px 0}
.nav .group{padding:12px 18px 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.nav a.item{display:block;padding:7px 18px;font-size:13.5px;color:var(--text);border-left:3px solid transparent;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav a.item:hover{background:var(--panel2);text-decoration:none}
.nav a.item.active{background:var(--panel2);border-left-color:var(--accent);color:#fff}
.nav a.item.hidden{display:none}

.main{flex:1;overflow-y:auto;position:relative}
.topbar{position:sticky;top:0;z-index:5;background:rgba(15,20,25,.85);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);padding:10px 28px;display:flex;align-items:center;gap:12px}
.topbar .menu-btn{display:none;background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 10px;cursor:pointer}
.topbar .crumb{font-size:13px;color:var(--muted)}
.topbar .spacer{flex:1}
.topbar .gen{font-size:11px;color:var(--muted)}
.content{max-width:900px;margin:0 auto;padding:28px 32px 80px}

/* Markdown 排版 */
.md h1{font-size:26px;border-bottom:1px solid var(--border);padding-bottom:.3em;margin-top:0}
.md h2{font-size:21px;border-bottom:1px solid var(--border);padding-bottom:.25em;margin-top:1.6em}
.md h3{font-size:17px;margin-top:1.4em}
.md h4{font-size:15px;color:var(--muted);margin-top:1.2em}
.md p,.md li{color:#d7dee6}
.md strong{color:#fff}
.md code{background:var(--panel2);padding:.15em .4em;border-radius:5px;font-size:.88em;font-family:"SF Mono",Consolas,Monaco,monospace}
.md pre{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;overflow:auto}
.md pre code{background:none;padding:0}
.md blockquote{margin:1em 0;padding:.6em 1em;border-left:4px solid var(--accent);background:var(--panel2);border-radius:0 8px 8px 0;color:#c6d0da}
.md blockquote p{margin:.4em 0}
.md table{border-collapse:collapse;width:100%;margin:1.1em 0;font-size:13.5px;display:block;overflow-x:auto}
.md th,.md td{border:1px solid var(--border);padding:8px 11px;text-align:left;vertical-align:top}
.md th{background:var(--panel2);color:#fff;position:sticky;top:0}
.md tr:nth-child(even) td{background:rgba(255,255,255,.02)}
.md hr{border:none;border-top:1px solid var(--border);margin:1.8em 0}
.md ul,.md ol{padding-left:1.4em}
.md img{max-width:100%;border-radius:8px}

/* 涨跌/状态着色（纯展示） */
.md td:contains{}
.disclaimer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);font-size:12px;color:var(--muted)}

/* 移动端 */
.backdrop{display:none}
@media (max-width:820px){
  .sidebar{position:fixed;left:0;top:0;bottom:0;z-index:30;transform:translateX(-100%);transition:transform .22s ease}
  .sidebar.open{transform:translateX(0)}
  .backdrop.show{display:block;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:20}
  .topbar .menu-btn{display:inline-block}
  .content{padding:20px 18px 60px}
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar" id="sidebar">
    <div class="brand">
      <h1>📊 美股持仓复盘</h1>
      <div class="sub">文档中心 · 个人投资纪律记录</div>
    </div>
    <div class="search"><input id="search" type="search" placeholder="🔍 搜索文档标题…" autocomplete="off"></div>
    <nav class="nav" id="nav"></nav>
  </aside>
  <div class="backdrop" id="backdrop"></div>
  <main class="main" id="main">
    <div class="topbar">
      <button class="menu-btn" id="menuBtn">☰</button>
      <span class="crumb" id="crumb"></span>
      <span class="spacer"></span>
      <span class="gen">生成于 __GEN_TIME__</span>
    </div>
    <div class="content"><article class="md" id="doc"></article>
      <div class="disclaimer">⚠️ 本站点仅为个人投资记录，不构成投资建议。内容随源 Markdown 文档更新，重新运行 <code>tools/build_site.py</code> 刷新。</div>
    </div>
  </main>
</div>

<script id="docs-data" type="application/json">__DOCS_JSON__</script>
<script>
const DOCS = JSON.parse(document.getElementById('docs-data').textContent);
function b64utf8(b64){const bin=atob(b64);const bytes=Uint8Array.from(bin,c=>c.charCodeAt(0));return new TextDecoder('utf-8').decode(bytes);}

marked.setOptions({gfm:true, breaks:false, headerIds:true, mangle:false});

// 文档 id / 目录 → 索引的映射，用于把站内 Markdown 链接改写成 hash 跳转
const ID_MAP = new Map();
const DIR_MAP = new Map();
DOCS.forEach((d,i)=>{
  ID_MAP.set(d.id, i);
  const parts = d.id.split('/');
  let acc='';
  for(let k=0;k<parts.length-1;k++){
    acc = acc ? acc+'/'+parts[k] : parts[k];
    if(!DIR_MAP.has(acc)) DIR_MAP.set(acc, i);   // 目录默认落到首篇
  }
});
DOCS.forEach((d,i)=>{                              // 若目录下有 README，优先作为该目录着陆页
  if(d.id.toLowerCase().endsWith('/readme.md')){
    DIR_MAP.set(d.id.slice(0, d.id.lastIndexOf('/')), i);
  }
});

function resolveRel(baseDir, rel){
  const stack = baseDir ? baseDir.split('/') : [];
  rel.split('/').forEach(part=>{
    if(part==='' || part==='.') return;
    if(part==='..') stack.pop();
    else stack.push(part);
  });
  return stack.join('/');
}

// 把当前文档里指向「已收录文档」的相对链接改写成 #hash 跳转（单页站点内部导航）
function rewriteLinks(d){
  const baseDir = d.id.includes('/') ? d.id.slice(0, d.id.lastIndexOf('/')) : '';
  docEl.querySelectorAll('a[href]').forEach(a=>{
    let href = a.getAttribute('href');
    if(!href || /^(https?:|mailto:|tel:|#)/i.test(href)) return;   // 外链/锚点不动
    const hi = href.indexOf('#');
    if(hi>=0) href = href.slice(0, hi);                            // 去掉 #fragment
    if(!href) return;
    let path; try{ path = decodeURIComponent(href); }catch(e){ path = href; }
    const resolved = resolveRel(baseDir, path);
    let hitId = null;
    if(ID_MAP.has(resolved)) hitId = resolved;
    else { const dir = resolved.replace(/\/+$/,''); if(DIR_MAP.has(dir)) hitId = DOCS[DIR_MAP.get(dir)].id; }
    if(hitId!=null) a.setAttribute('href', '#'+encodeURIComponent(hitId));
  });
}

// 构建侧边栏
const nav = document.getElementById('nav');
const groups = {};
DOCS.forEach((d,i)=>{ (groups[d.group] ||= []).push(i); });
Object.keys(groups).forEach(g=>{
  const gh = document.createElement('div'); gh.className='group'; gh.textContent=g; nav.appendChild(gh);
  groups[g].forEach(i=>{
    const d = DOCS[i];
    const a = document.createElement('a');
    a.className='item'; a.href='#'+encodeURIComponent(d.id); a.textContent=d.title; a.dataset.idx=i;
    a.title = d.path;
    nav.appendChild(a);
  });
});

const docEl = document.getElementById('doc');
const crumb = document.getElementById('crumb');

function render(idx){
  const d = DOCS[idx];
  if(!d) return;
  docEl.innerHTML = marked.parse(b64utf8(d.b64));
  crumb.textContent = d.path;
  rewriteLinks(d);
  document.querySelectorAll('.nav a.item').forEach(a=>a.classList.toggle('active', a.dataset.idx==idx));
  document.getElementById('main').scrollTop = 0;
  colorize();
  closeSidebar();
}

// 给表格里的状态/涨跌文字上色（纯展示增强）
function colorize(){
  docEl.querySelectorAll('td, li, strong').forEach(el=>{
    const t = el.textContent.trim();
    if(/^(✓|已决|保留|成立|未触发|合规|是)/.test(t) || /浮盈|止盈/.test(t)) el.style.color = 'var(--green)';
    else if(/^(✗|追缴|超限|不足|强制平仓|否)/.test(t) || /浮亏|-\d+\.\d%|触发/.test(t)) {}
  });
}

function idxFromHash(){
  const h = decodeURIComponent(location.hash.replace(/^#/,''));
  const i = DOCS.findIndex(d=>d.id===h);
  return i>=0 ? i : 0;
}
window.addEventListener('hashchange', ()=>render(idxFromHash()));

// 搜索过滤
document.getElementById('search').addEventListener('input', e=>{
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('.nav a.item').forEach(a=>{
    const hit = a.textContent.toLowerCase().includes(q) || (a.title||'').toLowerCase().includes(q);
    a.classList.toggle('hidden', q && !hit);
  });
  document.querySelectorAll('.nav .group').forEach(g=>{
    let n=g.nextElementSibling, any=false;
    while(n && n.classList.contains('item')){ if(!n.classList.contains('hidden')) any=true; n=n.nextElementSibling; }
    g.style.display = any ? '' : 'none';
  });
});

// 移动端抽屉
const sidebar=document.getElementById('sidebar'), backdrop=document.getElementById('backdrop');
function closeSidebar(){sidebar.classList.remove('open');backdrop.classList.remove('show');}
document.getElementById('menuBtn').onclick=()=>{sidebar.classList.toggle('open');backdrop.classList.toggle('show');};
backdrop.onclick=closeSidebar;

render(idxFromHash());
</script>
</body>
</html>
"""


def main():
    docs = collect_docs()
    OUT_DIR.mkdir(exist_ok=True)
    docs_json = json.dumps(docs, ensure_ascii=False)
    gen_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (HTML_TEMPLATE
            .replace("__DOCS_JSON__", docs_json)
            .replace("__GEN_TIME__", gen_time))
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"✅ 站点已生成：{OUT_FILE}")
    print(f"   收录文档 {len(docs)} 篇，分组：" +
          "、".join(sorted({d['group'] for d in docs}, key=lambda g: GROUP_ORDER.get(g, 9))))
    print(f"   双击打开或部署静态托管即可查看。")


if __name__ == "__main__":
    main()
