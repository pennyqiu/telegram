#!/usr/bin/env python3
"""
文章正文抓取与提取

KOL 推文里引用的外部链接（财报解读、博客、研报、新闻……）抓回来，
提取出标题 + 正文摘要，供后续研究阅读。

依赖优先级：
  - 有 bs4（BeautifulSoup）：用它做更干净的正文提取（首选，项目已装）
  - 没有 bs4：退化为正则去标签的极简提取
"""

from __future__ import annotations

import re
import html
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict

try:
    from bs4 import BeautifulSoup  # type: ignore
    _HAS_BS4 = True
except Exception:  # noqa: BLE001
    _HAS_BS4 = False

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 这些站点要么需要登录、要么是纯媒体，正文抓取意义不大，只记录链接
SKIP_BODY_DOMAINS = ("youtube.com", "youtu.be", "open.spotify.com", "podcasts.apple.com")

MAX_BODY_CHARS = 1500  # 摘要正文最大字符数，避免 JSON / HTML 过大


@dataclass
class Article:
    url: str = ""
    final_url: str = ""       # 跟随重定向后的真实地址（t.co 解包后）
    title: str = ""
    excerpt: str = ""         # 正文摘要（截断）
    word_count: int = 0
    ok: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _fetch(url: str, timeout: int = 25) -> tuple[str, str]:
    """返回 (final_url, html_text)。自动跟随重定向（含 t.co 短链）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final_url = resp.geturl()
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "xml" not in ctype:
            raise ValueError(f"非 HTML 内容（{ctype or '未知类型'}）")
        charset = "utf-8"
        m = re.search(r"charset=([\w-]+)", ctype)
        if m:
            charset = m.group(1)
        body = resp.read(2_000_000)  # 最多读 2MB
        return final_url, body.decode(charset, errors="replace")


def _extract_with_bs4(html_text: str) -> tuple[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")

    # 标题：优先 og:title，其次 <title>
    title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = og["content"].strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 去掉脚本/样式/导航等噪音
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    # 正文：优先 <article>，否则取 <p> 聚合
    container = soup.find("article") or soup.body or soup
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) > 40]  # 滤掉短噪音行
    body_text = "\n".join(paragraphs)
    if not body_text:
        body_text = container.get_text(" ", strip=True)
    return title, re.sub(r"[ \t]+", " ", body_text).strip()


def _extract_with_regex(html_text: str) -> tuple[str, str]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.S | re.I)
    title = html.unescape(title_m.group(1).strip()) if title_m else ""
    # 去 script/style，再去标签
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", cleaned))
    return title, re.sub(r"\s+", " ", text).strip()


def fetch_article(url: str) -> Article:
    art = Article(url=url)
    low = url.lower()
    if any(d in low for d in SKIP_BODY_DOMAINS):
        art.final_url = url
        art.ok = True
        art.title = "(媒体/视频链接，未抓正文)"
        return art
    try:
        final_url, html_text = _fetch(url)
        art.final_url = final_url
        if _HAS_BS4:
            title, body = _extract_with_bs4(html_text)
        else:
            title, body = _extract_with_regex(html_text)
        art.title = title or "(未提取到标题)"
        words = body.split()
        art.word_count = len(words)
        art.excerpt = body[:MAX_BODY_CHARS] + ("…" if len(body) > MAX_BODY_CHARS else "")
        art.ok = True
    except urllib.error.HTTPError as e:
        art.error = f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        art.error = str(e)
    return art
