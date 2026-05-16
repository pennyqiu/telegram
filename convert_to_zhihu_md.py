# -*- coding: utf-8 -*-
"""
HTML → 知乎 Markdown 转换器

把 insurance-guide/articles/cpa-*.html 转换为知乎可直接粘贴的 Markdown 文件。
规则：
1. 保留：标题、加粗、列表、表格、引用、链接
2. 转换：自定义彩色框（warn/danger/green/callout/case-box）→ Markdown 引用块 + emoji 前缀
3. 转换：.formula 深色代码框 → ``` 代码块
4. 转换：.toc 阅读地图 → ## 阅读地图 + 有序列表
5. 丢弃：top-bar / sidebar / article-meta-top 等导航与装饰元素
6. 重写：标题 → # 一级标题；副标题 → > 引用块作为开头
"""
from __future__ import annotations
import os, re, sys
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).parent
SRC_DIR = ROOT / "insurance-guide" / "articles"
OUT_DIR = ROOT / "insurance-guide" / "zhihu-md"
OUT_DIR.mkdir(exist_ok=True, parents=True)


CALLOUT_PREFIX = {
    "warn-block": "⚠️ **劣势暴露：** ",
    "danger-block": "🚨 **严重警告：** ",
    "green-block": "✅ **合规建议：** ",
    "case-box": "📋 **案例：** ",
    "callout warning": "⚠️ **注意：** ",
    "callout green": "✅ ",
    "callout": "💡 ",
    "compare-block": "🔍 **对比观察：** ",
    "scenario-box": "📊 **情景：** ",
    "timeline-box": "🕒 **时间线：** ",
    "role-card": "👤 **角色：** ",
}


def _clean_text(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()


def _inline(el) -> str:
    if isinstance(el, NavigableString):
        return str(el)
    if not isinstance(el, Tag):
        return ""

    name = el.name.lower()

    if name in ("strong", "b"):
        return f"**{''.join(_inline(c) for c in el.contents).strip()}**"
    if name in ("em", "i"):
        return f"*{''.join(_inline(c) for c in el.contents).strip()}*"
    if name == "a":
        text = ''.join(_inline(c) for c in el.contents).strip()
        href = (el.get("href") or "").strip()
        if href.startswith("cpa-") and href.endswith(".html"):
            return f"**{text}**（见姐妹篇）"
        if href.startswith("../"):
            return text
        if href and not href.startswith("#"):
            return f"[{text}]({href})"
        return text
    if name == "br":
        return "\n"
    if name == "code":
        return f"`{el.get_text()}`"
    if name == "span":
        return ''.join(_inline(c) for c in el.contents)
    return ''.join(_inline(c) for c in el.contents)


def _list_to_md(el: Tag, indent: int = 0, ordered: bool = False) -> str:
    lines = []
    counter = 1
    for li in el.find_all("li", recursive=False):
        prefix = f"{counter}. " if ordered else "- "
        text_parts = []
        nested_md = ""
        for c in li.contents:
            if isinstance(c, Tag) and c.name in ("ul", "ol"):
                nested_md = "\n" + _list_to_md(c, indent + 1, ordered=(c.name == "ol"))
            else:
                text_parts.append(_inline(c))
        text = _clean_text(''.join(text_parts).replace("\n", " "))
        lines.append("  " * indent + prefix + text + nested_md)
        counter += 1
    return "\n".join(lines)


def _table_to_md(el: Tag) -> str:
    rows = el.find_all("tr")
    if not rows:
        return ""
    md = []
    head_cells = rows[0].find_all(["th", "td"])
    head = [_clean_text(''.join(_inline(c) for c in cell.contents)) for cell in head_cells]
    md.append("| " + " | ".join(head) + " |")
    md.append("| " + " | ".join(["---"] * len(head)) + " |")
    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        vals = []
        for cell in cells:
            v = _clean_text(''.join(_inline(c) for c in cell.contents))
            v = v.replace("\n", " ").replace("|", "\\|")
            vals.append(v)
        while len(vals) < len(head):
            vals.append("")
        md.append("| " + " | ".join(vals) + " |")
    return "\n".join(md)


def _block_quote_with_prefix(el: Tag, prefix: str) -> str:
    raw = ''.join(_inline(c) for c in el.contents)
    text = _clean_text(raw)
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return ""
    first = lines[0]
    rest = lines[1:]
    out = [f"> {prefix}{first}"]
    for r in rest:
        out.append(f"> {r}")
    return "\n".join(out)


def _toc_to_md(toc_div: Tag) -> str:
    title = toc_div.find(class_="toc-title")
    ol = toc_div.find("ol")
    if not ol:
        return ""
    items = []
    for i, li in enumerate(ol.find_all("li", recursive=False), 1):
        items.append(f"{i}. {_clean_text(_inline(li))}")
    title_text = _clean_text(_inline(title)) if title else "阅读地图"
    return f"## {title_text}\n\n" + "\n".join(items)


def _loss_bar_to_md(el: Tag) -> str:
    pct = el.find(class_="loss-pct")
    pct_text = _clean_text(_inline(pct)) if pct else ""
    desc_parts = []
    for c in el.contents:
        if isinstance(c, Tag) and "loss-pct" in (c.get("class") or []):
            continue
        desc_parts.append(_inline(c))
    desc = _clean_text(''.join(desc_parts))
    return f"- **{pct_text}** — {desc}"


def _formula_to_md(el: Tag) -> str:
    text = el.get_text()
    text = re.sub(r"^\n+", "", text)
    text = re.sub(r"\n+$", "", text)
    return f"```text\n{text}\n```"


def _key_insight_to_md(el: Tag) -> str:
    title = el.find(class_="key-insight-title")
    body = el.find(class_="key-insight-body")
    title_text = _clean_text(_inline(title)) if title else "关键洞察"
    body_text = _clean_text(''.join(_inline(c) for c in body.contents)) if body else ""
    return f"---\n\n### 💎 {title_text}\n\n> {body_text}"


def _has_class(el: Tag, cls: str) -> bool:
    classes = el.get("class") or []
    target = cls.split()
    return all(t in classes for t in target)


def _block_to_md(el) -> str:
    if isinstance(el, NavigableString):
        s = str(el).strip()
        return s if s else ""

    if not isinstance(el, Tag):
        return ""

    name = el.name.lower()
    classes = el.get("class") or []

    if name == "div" and any(c in classes for c in ("article-meta-top", "section-end", "meta-stats")):
        return ""

    if name == "div" and "article-meta" in classes:
        title_el = el.find(class_="article-title-main")
        summary_el = el.find(class_="article-summary")
        title = _clean_text(_inline(title_el)) if title_el else ""
        summary = _clean_text(''.join(_inline(c) for c in summary_el.contents)) if summary_el else ""
        parts = []
        if title:
            parts.append(f"# {title}")
        if summary:
            parts.append(f"> {summary}")
        return "\n\n".join(parts)

    if name == "div" and "toc" in classes:
        return _toc_to_md(el)

    # 检查 callout 类（包括复合的 callout warning / callout green）
    if name == "div":
        cls_str = " ".join(classes)
        # 优先匹配长 class 组合（callout warning / callout green）
        for cls, prefix in CALLOUT_PREFIX.items():
            if " " in cls:
                if _has_class(el, cls):
                    return _block_quote_with_prefix(el, prefix)
        # 单个 class
        for cls, prefix in CALLOUT_PREFIX.items():
            if " " not in cls and cls in classes:
                return _block_quote_with_prefix(el, prefix)

    if name == "div" and "formula" in classes:
        return _formula_to_md(el)

    if name == "div" and "key-insight" in classes:
        return _key_insight_to_md(el)

    if name == "div" and "loss-bar" in classes:
        return _loss_bar_to_md(el)

    if name in ("h1", "h2", "h3", "h4", "h5"):
        level = int(name[1])
        text = _clean_text(_inline(el))
        return ("#" * level) + " " + text

    if name == "p":
        if "cite" in classes:
            text = _clean_text(''.join(_inline(c) for c in el.contents))
            return f"---\n\n*{text}*"
        text = _clean_text(''.join(_inline(c) for c in el.contents))
        return text

    if name == "ul":
        return _list_to_md(el, ordered=False)
    if name == "ol":
        return _list_to_md(el, ordered=True)

    if name == "table":
        return _table_to_md(el)
    if name == "div" and "table-wrap" in classes:
        tbl = el.find("table")
        return _table_to_md(tbl) if tbl else ""

    if name == "blockquote":
        text = _clean_text(''.join(_inline(c) for c in el.contents))
        lines = [l for l in text.split("\n") if l.strip()]
        return "\n".join(f"> {l}" for l in lines)

    if name == "hr":
        return "---"

    if name == "div":
        parts = []
        for c in el.children:
            md = _block_to_md(c)
            if md:
                parts.append(md)
        return "\n\n".join(parts)

    return ""


def convert(html_path: Path) -> str:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    article = soup.find("article")
    if not article:
        return ""

    blocks = []
    for child in article.children:
        md = _block_to_md(child)
        if md:
            blocks.append(md)

    body = "\n\n".join(blocks)
    body = re.sub(r"\n{3,}", "\n\n", body)

    footer = "\n\n---\n\n*本文首发于个人公众号，知乎同步发布。如需进一步交流，欢迎通过公众号留言。*"
    return body + footer


def main():
    files = sorted(SRC_DIR.glob("cpa-*.html"))
    if not files:
        print(f"未找到 {SRC_DIR}/cpa-*.html")
        sys.exit(1)

    print(f"找到 {len(files)} 个 HTML 文件，开始转换 ...")
    for f in files:
        md = convert(f)
        out = OUT_DIR / (f.stem + ".md")
        out.write_text(md, encoding="utf-8")
        chars = len(md)
        kb = len(md.encode("utf-8")) / 1024
        print(f"  + {f.stem:35s} -> {out.relative_to(ROOT)} ({chars} chars / {kb:.1f} KB)")

    print(f"\n完成，输出目录: {OUT_DIR}")


if __name__ == "__main__":
    main()
