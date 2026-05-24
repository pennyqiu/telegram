#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将HTML文章转换为：
1. 公众号版本 - HTML文件（带样式，浏览器打开后可全选复制粘贴到微信公众号编辑器）
2. 知乎版本 - Markdown文件（可直接粘贴到知乎编辑器）
"""

from bs4 import BeautifulSoup
import re

HTML_FILE = 'insurance-guide/articles/v22-persona.html'


def parse_source():
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.find('div', class_='article-body')
    return soup, body


def split_two_versions(body):
    """文章里包含【A】公众号版和【B】知乎版，按 h1 切分。"""
    elements = list(body.children)
    parts = {'wechat': [], 'zhihu': []}
    current = None
    for el in elements:
        if getattr(el, 'name', None) is None:
            continue
        if el.name == 'h1':
            text = el.get_text()
            if 'A' in text and ('公众号' in text or '\u516c\u4f17\u53f7' in text):
                current = 'wechat'
                continue
            if 'B' in text and ('知乎' in text or '\u77e5\u4e4e' in text):
                current = 'zhihu'
                continue
            if '双版本' in text or '\u53cc\u7248\u672c' in text:
                current = None
                continue
        if current:
            parts[current].append(el)
    return parts


def element_to_markdown(el):
    """将单个html元素转换为markdown字符串。"""
    name = el.name
    if name in ('h1',):
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
        for child in el.find_all(['p'], recursive=False):
            txt = inline_to_md(child).strip()
            for line in txt.split('\n'):
                lines.append(f"> {line}" if line.strip() else ">")
        if not lines:
            txt = inline_to_md(el).strip()
            for line in txt.split('\n'):
                lines.append(f"> {line}" if line.strip() else ">")
        return "\n".join(lines) + "\n\n"
    if name == 'p':
        return inline_to_md(el).strip() + "\n\n"
    if name == 'ul':
        items = []
        for li in el.find_all('li', recursive=False):
            items.append(f"- {inline_to_md(li).strip()}")
        return "\n".join(items) + "\n\n"
    if name == 'ol':
        items = []
        for i, li in enumerate(el.find_all('li', recursive=False), 1):
            items.append(f"{i}. {inline_to_md(li).strip()}")
        return "\n".join(items) + "\n\n"
    return ''


def inline_to_md(el):
    """将段落内联格式（strong/em/code）转换。"""
    parts = []
    for child in el.children:
        if getattr(child, 'name', None) is None:
            parts.append(str(child))
        elif child.name == 'strong' or child.name == 'b':
            parts.append(f"**{child.get_text()}**")
        elif child.name == 'em' or child.name == 'i':
            parts.append(f"*{child.get_text()}*")
        elif child.name == 'code':
            parts.append(f"`{child.get_text()}`")
        elif child.name == 'br':
            parts.append("\n")
        else:
            parts.append(child.get_text())
    return ''.join(parts)


def to_markdown(elements):
    out = []
    for el in elements:
        md = element_to_markdown(el)
        if md:
            out.append(md)
    text = ''.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + '\n'


# ---------------- 公众号 HTML ----------------
WECHAT_CSS = """
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
       max-width:677px;margin:30px auto;padding:0 18px;color:#333;
       font-size:16px;line-height:1.85;background:#fff;}
  h1{font-size:22px;font-weight:800;color:#1a1a1a;text-align:center;
     margin:30px 0 20px;padding-bottom:12px;border-bottom:2px solid #1a56db;}
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
  .meta{text-align:center;color:#64748b;font-size:13px;margin-bottom:20px;}
  .signature{margin-top:30px;padding:18px;background:#f1f5f9;
             border-radius:10px;font-size:15px;color:#475569;line-height:1.8;}
  .disclaimer{margin-top:24px;padding:14px;background:#fef3c7;
              border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;
              font-size:13px;color:#78350f;line-height:1.7;}
</style>
"""


def wechat_html(elements, title):
    body_html = []
    skip_next_blockquote = False
    for el in elements:
        # 把首个 blockquote（标题/副标题/配图建议块）剔除，因为它是给作者看的备注，不是正文
        if el.name == 'blockquote' and not skip_next_blockquote:
            skip_next_blockquote = True
            continue
        # 把内容里被错误识别为 h2 的 "---" 干掉
        if el.name == 'h2' and el.get_text().strip() in ('---', '——'):
            continue
        body_html.append(str(el))
    raw = ''.join(body_html)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
{WECHAT_CSS}
</head>
<body>
<div class="meta">— CPA × 香港保险 —</div>
<h1>在迅雷做了 8 年总账，<br>我为什么把简历交给了安盛</h1>
<p style="text-align:center;color:#64748b;font-size:14px;margin-top:-10px;margin-bottom:30px;">
把上市公司的财务标准，搬到家庭资产负债表上
</p>
{raw}
</body>
</html>
"""


# ---------------- 主流程 ----------------
def main():
    soup, body = parse_source()
    parts = split_two_versions(body)

    # 公众号 HTML
    wechat_html_str = wechat_html(parts['wechat'],
                                  '在迅雷做了8年总账，我为什么把简历交给了安盛')
    with open('公众号_在迅雷做了8年总账.html', 'w', encoding='utf-8') as f:
        f.write(wechat_html_str)

    # 知乎 Markdown
    zhihu_md = to_markdown(parts['zhihu'])
    title = '一个8年迅雷总账CPA，为什么转身去做香港保险？'
    zhihu_md = f"# {title}\n\n" + zhihu_md
    with open('知乎_8年迅雷CPA转做香港保险.md', 'w', encoding='utf-8') as f:
        f.write(zhihu_md)

    # 同时给一份公众号 markdown 备用
    wechat_md = to_markdown(parts['wechat'])
    wechat_md = f"# 在迅雷做了8年总账，我为什么把简历交给了安盛\n\n" + wechat_md
    with open('公众号_在迅雷做了8年总账.md', 'w', encoding='utf-8') as f:
        f.write(wechat_md)

    print('已生成：')
    print('  公众号_在迅雷做了8年总账.html  （在浏览器打开 → 全选复制 → 粘贴到公众号编辑器，保留全部样式）')
    print('  公众号_在迅雷做了8年总账.md    （Markdown版备用）')
    print('  知乎_8年迅雷CPA转做香港保险.md  （直接粘贴到知乎编辑器，知乎原生支持Markdown）')


if __name__ == '__main__':
    main()
