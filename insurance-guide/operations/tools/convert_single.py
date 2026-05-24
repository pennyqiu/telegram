#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用版：把 insurance-guide/articles/ 下任意单篇 HTML 文章
转换成"公众号 HTML（带样式）" + "知乎 MD（原生 Markdown）"。
用法：python convert_single.py <html_file> <output_basename>
例： python convert_single.py insurance-guide/articles/cpa-01-dividend-trap.html "公众号_港险分红智商税"
"""

import sys
import re
from bs4 import BeautifulSoup

WECHAT_CSS = """
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
       max-width:677px;margin:30px auto;padding:0 18px;color:#333;
       font-size:16px;line-height:1.85;background:#fff;}
  h1{font-size:22px;font-weight:800;color:#1a1a1a;text-align:center;
     margin:30px 0 18px;padding-bottom:12px;border-bottom:2px solid #1a56db;line-height:1.4;}
  h2{font-size:19px;font-weight:700;color:#1a56db;margin:34px 0 14px;
     padding-left:12px;border-left:4px solid #1a56db;line-height:1.4;}
  h3{font-size:17px;font-weight:700;color:#1e3a5f;margin:24px 0 12px;}
  h4{font-size:16px;font-weight:700;color:#374151;margin:20px 0 10px;}
  p{margin:14px 0;text-align:justify;letter-spacing:0.3px;}
  strong{color:#1a56db;font-weight:700;}
  blockquote{margin:18px 0;padding:14px 18px;background:#f8fafc;
             border-left:4px solid #1a56db;border-radius:0 8px 8px 0;
             color:#475569;font-size:15px;}
  blockquote p{margin:6px 0;}
  ul,ol{margin:14px 0;padding-left:24px;}
  li{margin:8px 0;line-height:1.8;}
  hr{border:none;border-top:1px dashed #cbd5e1;margin:28px 0;}
  table{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px;}
  th,td{border:1px solid #e2e8f0;padding:10px 12px;text-align:left;}
  th{background:#1a56db;color:#fff;font-weight:700;}
  tr:nth-child(even) td{background:#f8fafc;}
  .callout{margin:20px 0;padding:16px 18px;border-radius:10px;font-size:15px;line-height:1.75;}
  .callout.warning{background:#fef3c7;border-left:4px solid #f59e0b;color:#78350f;}
  .callout.info{background:#dbeafe;border-left:4px solid #1a56db;color:#1e3a8a;}
  .callout.success{background:#d1fae5;border-left:4px solid #10b981;color:#064e3b;}
  .callout.danger{background:#fee2e2;border-left:4px solid #ef4444;color:#7f1d1d;}
  .formula{margin:18px 0;padding:14px 18px;background:#f1f5f9;border-radius:8px;
           font-family:"Consolas","SF Mono",monospace;font-size:14px;color:#1e293b;
           white-space:pre-wrap;line-height:1.7;border:1px dashed #94a3b8;}
  .warn-block{margin:20px 0;padding:16px 18px;background:#fef3c7;border-left:4px solid #f59e0b;
              border-radius:0 8px 8px 0;color:#78350f;font-size:15px;line-height:1.75;}
  .warn-block strong{color:#b45309;}
  .key-insight,.key-insight-body{margin:20px 0;padding:16px 18px;background:#dbeafe;
                                 border-left:4px solid #1a56db;border-radius:0 8px 8px 0;
                                 color:#1e3a8a;font-size:15px;line-height:1.8;}
  .author-info,.brand-bar{display:none;}
  .meta{text-align:center;color:#64748b;font-size:13px;margin-bottom:20px;}
  .summary{margin:20px 0 30px;padding:16px 18px;background:#f8fafc;
           border-left:3px solid #1a56db;border-radius:0 8px 8px 0;
           color:#475569;font-size:15px;line-height:1.8;}
  .toc{margin:24px 0;padding:18px 22px;background:#f1f5f9;border-radius:10px;
       font-size:14px;color:#475569;}
  .toc-title{font-weight:700;color:#1a56db;margin-bottom:8px;}
</style>
"""


# ---------------- 提取 ----------------
def extract(html_file):
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    # 标题
    t = soup.find('div', class_='article-title-main') or soup.find('h1', class_='article-title-main')
    if t is None:
        t = soup.find('h1')
    title = t.get_text().strip() if t else '未命名文章'

    # 摘要
    s = (soup.find('div', class_='article-summary')
         or soup.find('div', class_='v22-summary'))
    summary = s.get_text().strip() if s else ''

    # 主体：article 标签下，去掉 meta/toc/导航/末尾 section-end
    article = soup.find('article')
    if not article:
        article = soup.find('div', class_='article-body')

    # 把要剔除的容器先 decompose 掉
    for cls in ['article-meta', 'top-bar', 'section-end', 'toc']:
        for el in article.find_all('div', class_=cls):
            el.decompose()

    return title, summary, article


# ---------------- 公众号 HTML ----------------
def to_wechat_html(title, summary, article, brand_meta='— CPA × 香港保险 —'):
    parts = []
    for el in article.children:
        if getattr(el, 'name', None) is None:
            continue
        # 跳过明显是导航/分割文字
        if el.name == 'h2' and el.get_text().strip() in ('---', '——'):
            continue
        parts.append(str(el))
    body = ''.join(parts)

    summary_html = f'<div class="summary">{summary}</div>' if summary else ''
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
{WECHAT_CSS}
</head>
<body>
<div class="meta">{brand_meta}</div>
<h1>{title}</h1>
{summary_html}
{body}
</body>
</html>
"""


# ---------------- 知乎 Markdown ----------------
def inline_md(el):
    out = []
    for child in el.children:
        if getattr(child, 'name', None) is None:
            out.append(str(child))
        elif child.name in ('strong', 'b'):
            out.append(f"**{child.get_text()}**")
        elif child.name in ('em', 'i'):
            out.append(f"*{child.get_text()}*")
        elif child.name == 'code':
            out.append(f"`{child.get_text()}`")
        elif child.name == 'br':
            out.append("\n")
        elif child.name == 'a':
            href = child.get('href', '')
            txt = child.get_text()
            out.append(f"[{txt}]({href})" if href else txt)
        else:
            out.append(child.get_text())
    return ''.join(out)


def el_to_md(el):
    name = el.name
    if name == 'h1':
        return f"# {el.get_text().strip()}\n\n"
    if name == 'h2':
        return f"## {el.get_text().strip()}\n\n"
    if name == 'h3':
        return f"### {el.get_text().strip()}\n\n"
    if name == 'h4':
        return f"#### {el.get_text().strip()}\n\n"
    if name == 'hr':
        return "\n---\n\n"
    if name == 'blockquote':
        lines = []
        children = el.find_all('p', recursive=False)
        if not children:
            txt = inline_md(el).strip()
            for line in txt.split('\n'):
                lines.append(f"> {line}" if line.strip() else ">")
        else:
            for c in children:
                txt = inline_md(c).strip()
                for line in txt.split('\n'):
                    lines.append(f"> {line}" if line.strip() else ">")
        return "\n".join(lines) + "\n\n"
    if name == 'p':
        return inline_md(el).strip() + "\n\n"
    if name == 'ul':
        items = [f"- {inline_md(li).strip()}" for li in el.find_all('li', recursive=False)]
        return "\n".join(items) + "\n\n"
    if name == 'ol':
        items = [f"{i}. {inline_md(li).strip()}" for i, li in enumerate(el.find_all('li', recursive=False), 1)]
        return "\n".join(items) + "\n\n"
    if name == 'table':
        return table_to_md(el)
    if name == 'div':
        cls = el.get('class', [])
        if cls and 'callout' in cls:
            label_map = {'warning': '⚠️ ', 'info': '💡 ', 'success': '✅ ', 'danger': '🚫 '}
            prefix = ''
            for k, v in label_map.items():
                if k in cls:
                    prefix = v
                    break
            inner_text = el.get_text().strip()
            inner_text = re.sub(r'\s+\n', '\n', inner_text)
            lines = [f"> {prefix}{line}".rstrip() if i == 0 else f"> {line}".rstrip()
                     for i, line in enumerate(inner_text.split('\n'))]
            return "\n".join(lines) + "\n\n"
        if cls and 'formula' in cls:
            inner = el.get_text().strip()
            return f"```\n{inner}\n```\n\n"
        if cls and ('warn-block' in cls or 'warning-block' in cls):
            inner_text = el.get_text().strip()
            lines = [f"> ⚠️ {line}".rstrip() if i == 0 else f"> {line}".rstrip()
                     for i, line in enumerate(inner_text.split('\n'))]
            return "\n".join(lines) + "\n\n"
        if cls and ('key-insight' in cls or 'key-insight-body' in cls):
            inner_text = el.get_text().strip()
            lines = [f"> 💡 {line}".rstrip() if i == 0 else f"> {line}".rstrip()
                     for i, line in enumerate(inner_text.split('\n'))]
            return "\n".join(lines) + "\n\n"
        # 普通 div：递归处理
        out = ''
        for c in el.children:
            if getattr(c, 'name', None):
                out += el_to_md(c)
        return out
    return ''


def table_to_md(table):
    rows = table.find_all('tr')
    if not rows:
        return ''
    md_rows = []
    header_done = False
    for i, r in enumerate(rows):
        cells = r.find_all(['th', 'td'])
        line = '| ' + ' | '.join(c.get_text().strip().replace('\n', ' ') for c in cells) + ' |'
        md_rows.append(line)
        if i == 0 and not header_done:
            md_rows.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
            header_done = True
    return "\n".join(md_rows) + "\n\n"


def to_zhihu_md(title, summary, article):
    out = [f"# {title}\n\n"]
    if summary:
        out.append(f"> {summary}\n\n")
        out.append("---\n\n")
    for el in article.children:
        if getattr(el, 'name', None) is None:
            continue
        if el.name == 'h2' and el.get_text().strip() in ('---', '——'):
            continue
        md = el_to_md(el)
        if md:
            out.append(md)
    text = ''.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + '\n'


# ---------------- 主流程 ----------------
def main():
    if len(sys.argv) < 3:
        print('Usage: python convert_single.py <html_file> <basename>')
        sys.exit(1)
    html_file = sys.argv[1]
    basename = sys.argv[2]
    title, summary, article = extract(html_file)
    wechat_html = to_wechat_html(title, summary, article)
    zhihu_md = to_zhihu_md(title, summary, article)
    wx_path = f'公众号_{basename}.html'
    zh_path = f'知乎_{basename}.md'
    with open(wx_path, 'w', encoding='utf-8') as f:
        f.write(wechat_html)
    with open(zh_path, 'w', encoding='utf-8') as f:
        f.write(zhihu_md)
    print('OK')
    print(f'  {wx_path}')
    print(f'  {zh_path}')
    print(f'  TITLE: {title}')


if __name__ == '__main__':
    main()
