# -*- coding: utf-8 -*-
"""
把根目录的 2 份 SOP / 运营矩阵 markdown
转成 insurance-guide/articles/ 下的 v22 风格 HTML 静态页。

被 index.html「内容生产物料导览」卡片直接链接，
解决线上 nginx 不服务 .md 时跳首页的问题。
"""
import os
import re
import markdown

OUT_DIR = os.path.join("insurance-guide", "articles")

PAGES = [
    {
        "src": "朋友圈长线运营矩阵.md",
        "out": "v22-friend-matrix.html",
        "tag":  "私域运营",
        "tag_color": "#16a34a",
        "title": "朋友圈长线运营矩阵 v1.0",
        "subtitle": "70/20/10 法则 + 锚点节奏 + 30 条选题日历 + 5 套文案模板",
        "stats": [("v1.0", "版本"), ("7 章", "结构"), ("300+", "行")],
        "summary": "战略手册 v2.3 配套独立专章。把朋友圈从「转化触发器」升级为「私域人格资产沉淀地」，含三维内容矩阵、锚点节奏、阶段性任务、合规红线、长线 KPI、30 条首月选题日历与 5 套高频文案模板。",
    },
    {
        "src": "知乎发布SOP.md",
        "out": "v22-zhihu-sop.html",
        "tag":  "发布流程",
        "tag_color": "#6366f1",
        "title": "11 篇 CPA 深度研报 · 知乎发布 SOP",
        "subtitle": "Markdown → 知乎富文本的完整搬运手册",
        "stats": [("11 篇", "研报"), ("4 步", "工作流"), ("SOP", "类型")],
        "summary": "把 insurance-guide/articles/cpa-*.html 的 11 篇 CPA 深度研报搬运到知乎个人主页的完整 SOP：推荐工作流、格式损耗清单、SEO 优化、合规自查、发布节奏与一次性批量上线方案。",
    },
    {
        "src": "公众号6个月内容矩阵.md",
        "out": "v22-wechat-matrix.html",
        "tag":  "公众号矩阵",
        "tag_color": "#7c3aed",
        "title": "微信公众号 6 个月内容矩阵 v1.0",
        "subtitle": "15 篇长文日历 + 三类配比 + 10 份钩子 + 跨平台联动 SOP",
        "stats": [("v1.0", "版本"), ("10 章", "结构"), ("15 篇", "长文")],
        "summary": "战略手册 v2.3 配套专章。公众号定位为「高净值财富管理内参」，含 6 个月 15 篇长文日历、政策/案例/认知三类内容配比、10 份钩子物料清单、跨小红书/知乎/朋友圈的联动 SOP 与合规边界。",
    },
]

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} · 香港保险从业全景指南</title>
<link rel="stylesheet" href="_style.css">
<style>
.v22-tag{{display:inline-block;font-size:11px;font-weight:700;letter-spacing:1px;color:#fff;padding:3px 10px;border-radius:20px;text-transform:uppercase;background:{tag_color};}}
.v22-summary{{font-size:14px;color:#374151;line-height:1.75;margin-top:14px;background:#f8fafc;border-left:3px solid {tag_color};padding:14px 16px;border-radius:0 8px 8px 0;}}
.article-body h1{{font-size:22px;border-bottom:2px solid #e5e7eb;padding-bottom:8px;}}
.article-body h2{{font-size:18px;color:#1e3a5f;margin-top:30px;}}
.article-body h3{{font-size:16px;color:#111827;margin-top:22px;}}
.article-body h4{{font-size:14px;color:#1e3a5f;margin-top:18px;font-weight:700;}}
.article-body table{{font-size:13px;}}
.article-body code{{background:#f1f5f9;color:#be185d;padding:1px 6px;border-radius:4px;font-family:'SF Mono','Consolas',monospace;font-size:13px;}}
.article-body pre{{background:#1e293b;color:#e2e8f0;padding:14px 16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6;margin:14px 0;}}
.article-body pre code{{background:transparent;color:inherit;padding:0;}}
.article-body blockquote{{border-left:4px solid {tag_color};background:#f8fafc;padding:10px 16px;color:#475569;font-style:normal;}}
.article-body ul,.article-body ol{{margin-left:24px;}}
</style>
</head>
<body>

<div class="top-bar">
  <div class="top-bar-inner">
    <a class="back-btn" href="../index.html">← 返回主页</a>
    <span class="source-tag">v2.3 作战物料 · 配套专章</span>
  </div>
</div>

<article>
  <div class="article-meta">
    <div class="article-meta-top">
      <span class="v22-tag">{tag}</span>
      <div class="meta-stats">
{stats_html}
      </div>
    </div>
    <h1 class="article-title-main">{title}</h1>
    <div class="v22-summary">{summary}</div>
  </div>

  <div class="article-body">
{body}
  </div>

  <div class="section-end">
    <a href="../index.html">← 返回主页查看其他物料</a>
  </div>
</article>

</body>
</html>
"""


def render_stats(stats):
    return "\n".join(
        '        <div class="meta-stat"><div class="meta-stat-num">{}</div><div class="meta-stat-label">{}</div></div>'.format(n, l)
        for n, l in stats
    )


def _preprocess(md_text: str) -> str:
    """python-markdown 严格要求列表前有空行；为兼容手写 md，
    在「上一行非空且非列表」紧跟列表项的位置自动补空行。"""
    out = []
    prev = ""
    list_re = re.compile(r"^\s{0,3}([-*+]|\d+\.)\s+\S")
    code_fence = re.compile(r"^\s*```")
    in_code = False
    for line in md_text.splitlines():
        if code_fence.match(line):
            in_code = not in_code
            out.append(line)
            prev = line
            continue
        if not in_code and list_re.match(line) and prev.strip() and not list_re.match(prev):
            out.append("")
        out.append(line)
        prev = line
    return "\n".join(out) + "\n"


def md_to_html(md_text):
    md_text = _preprocess(md_text)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"slugify": lambda v, _: re.sub(r"[^\w\u4e00-\u9fa5-]", "-", v).strip("-").lower()}},
    )
    return md.convert(md_text)


def build_one(page):
    with open(page["src"], "r", encoding="utf-8") as f:
        md_text = f.read()
    body = md_to_html(md_text)
    html = TEMPLATE.format(
        title=page["title"],
        tag=page["tag"],
        tag_color=page["tag_color"],
        stats_html=render_stats(page["stats"]),
        summary=page["summary"],
        body=body,
    )
    out_path = os.path.join(OUT_DIR, page["out"])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK]", page["src"], "->", out_path, "(", len(html), "B )")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for p in PAGES:
        build_one(p)


if __name__ == "__main__":
    main()
