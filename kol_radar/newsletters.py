#!/usr/bin/env python3
"""
Newsletter / 博客 RSS 数据源

这 6 位 KOL 里有 4 位运营官方 newsletter（SemiAnalysis / Fabricated Knowledge /
I/O Fund / Clouded Judgement），且自带 RSS。推文常常只是给长文
引流的「钩子」，真正的深度观点、数据与模型在 newsletter 全文里——所以这是比 X API
更优质的「研究」来源：免费、稳定、提供全文或长摘要，且不需要任何 token。

Substack / 多数博客的 RSS 会在 <content:encoded> 里直接塞全文，这里优先取它，
省掉一次额外的正文抓取请求；取不到再退回 <description>。
"""

from __future__ import annotations

import re
import html
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from xml.etree import ElementTree as ET

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# RSS 里 content:encoded 的命名空间
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"

MAX_BODY_CHARS = 2000  # newsletter 正文比推文长，给更大的摘要额度


@dataclass
class NewsletterPost:
    kol_handle: str
    title: str = ""
    link: str = ""
    published: str = ""
    excerpt: str = ""        # 正文摘要（截断）
    word_count: int = 0
    paywalled: bool = False  # 是否疑似仅摘要（付费墙）

    def to_dict(self) -> dict:
        return asdict(self)


def _http_get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _strip_html(raw: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def fetch_newsletter(handle: str, rss_url: str, limit: int = 5) -> list:
    """抓取某个 newsletter 的最近 N 篇，返回 NewsletterPost 列表。"""
    raw = _http_get(rss_url)
    root = ET.fromstring(raw)
    posts = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()

        # 优先全文 content:encoded，退回 description
        body_html = it.findtext(CONTENT_NS) or it.findtext("description") or ""
        body = _strip_html(body_html)
        words = body.split()

        posts.append(NewsletterPost(
            kol_handle=handle,
            title=html.unescape(title),
            link=link,
            published=pub,
            excerpt=body[:MAX_BODY_CHARS] + ("…" if len(body) > MAX_BODY_CHARS else ""),
            word_count=len(words),
            # 经验阈值：substack 付费文的 RSS 往往只给几十~200 词的预览
            paywalled=len(words) < 200,
        ))
    return posts


def fetch_newsletter_safe(handle: str, rss_url: str, limit: int = 5) -> tuple[list, str]:
    """带异常包装：返回 (posts, status)。status 为 'ok' 或错误摘要。"""
    if not rss_url:
        return [], "无 newsletter 源"
    try:
        return fetch_newsletter(handle, rss_url, limit), "ok"
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return [], str(e)
