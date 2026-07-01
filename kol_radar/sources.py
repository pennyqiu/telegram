#!/usr/bin/env python3
"""
KOL 推文数据源后端

X / 推特官方对未授权抓取限制很严，单一来源都不稳定，因此这里做成
「可切换 + 自动降级」的多后端结构。通过环境变量 KOL_SOURCE 选择优先后端：

  - x_api : X 官方 API v2（最稳、质量最高，需 X_BEARER_TOKEN，付费）
  - nitter: 某个 Nitter 实例的 RSS（免费，但公共实例经常挂，需自备 NITTER_BASE）
  - rsshub: 某个 RSSHub 实例（免费/自建，路由 /twitter/user/:handle，需 RSSHUB_BASE）

主程序会按 [优先后端 → 其余后端] 顺序依次尝试，任一成功即返回。
所有后端统一产出 Tweet 列表，屏蔽上游差异。
"""

from __future__ import annotations

import os
import re
import html
import json
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 从推文正文里剔除的「自链接」域名（指向推文本身/图片，而非外部文章）
SELF_DOMAINS = ("t.co", "twitter.com", "x.com", "pic.twitter.com")

URL_RE = re.compile(r"https?://[^\s<>\"']+")


@dataclass
class Tweet:
    kol_handle: str
    id: str = ""
    text: str = ""
    created_at: str = ""          # ISO8601 字符串
    tweet_url: str = ""           # 指向推文本身
    article_urls: list = field(default_factory=list)  # 推文里引用的外部文章链接
    source: str = ""              # 抓取后端来源（x_api / nitter / rsshub）

    def to_dict(self) -> dict:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════════════════

def _http_get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _clean_text(raw: str) -> str:
    """去 HTML 标签 + 反转义实体，得到纯文本推文。"""
    no_tags = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(no_tags)
    return re.sub(r"\s+", " ", text).strip()


def _is_external(url: str) -> bool:
    low = url.lower()
    return not any(d in low for d in SELF_DOMAINS)


def _extract_article_urls(*texts: str) -> list:
    """从一段或多段文本/HTML 中提取去重后的外部文章链接。"""
    found, seen = [], set()
    for t in texts:
        if not t:
            continue
        # 优先从 HTML 的 href 取（更干净），再兜底正则全文扫描
        for m in re.findall(r'href=["\'](https?://[^"\']+)["\']', t):
            for u in (m,):
                u = u.rstrip(".,;)】」)")
                if _is_external(u) and u not in seen:
                    seen.add(u)
                    found.append(u)
        for u in URL_RE.findall(re.sub(r"<[^>]+>", " ", t)):
            u = u.rstrip(".,;)】」)")
            if _is_external(u) and u not in seen:
                seen.add(u)
                found.append(u)
    return found


# ════════════════════════════════════════════════════════════════════
#  后端 1：X 官方 API v2
# ════════════════════════════════════════════════════════════════════

def fetch_via_x_api(handle: str, limit: int = 10) -> list:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未配置 X_BEARER_TOKEN，跳过 x_api 后端")

    headers = {"Authorization": f"Bearer {token}"}
    # 1) 用户名 → user id
    uid_raw = _http_get(
        f"https://api.x.com/2/users/by/username/{handle}",
        headers=headers,
    )
    uid = json.loads(uid_raw).get("data", {}).get("id")
    if not uid:
        raise RuntimeError(f"x_api 未能解析 @{handle} 的用户 ID")

    # 2) 拉取最近推文，展开 entities.urls 拿到 expanded_url
    params = (
        f"max_results={max(5, min(limit, 100))}"
        "&tweet.fields=created_at,entities,text"
        "&exclude=retweets,replies"
    )
    raw = _http_get(
        f"https://api.x.com/2/users/{uid}/tweets?{params}",
        headers=headers,
    )
    payload = json.loads(raw)
    tweets = []
    for item in payload.get("data", [])[:limit]:
        urls = []
        for u in item.get("entities", {}).get("urls", []):
            exp = u.get("expanded_url") or u.get("url", "")
            if exp and _is_external(exp):
                urls.append(exp)
        # 正文里可能还有未被 entities 收录的链接，补扫一次
        urls = list(dict.fromkeys(urls + _extract_article_urls(item.get("text", ""))))
        tweets.append(Tweet(
            kol_handle=handle,
            id=item.get("id", ""),
            text=_clean_text(item.get("text", "")),
            created_at=item.get("created_at", ""),
            tweet_url=f"https://x.com/{handle}/status/{item.get('id', '')}",
            article_urls=urls,
            source="x_api",
        ))
    return tweets


def fetch_via_x_api_archive(
    handle: str,
    since: str,
    until: str = "",
    max_total: int = 500,
    include_replies: bool = False,
) -> list:
    """全档案搜索（/2/tweets/search/all），用于一次性回溯某个时间段内的全部内容。

    需 X_BEARER_TOKEN 且账户为 pay-per-use / Enterprise（2026 起按量付费账户已放开此接口）。
    每条约 $0.005，请通过 max_total 控制成本上限。
    since/until 支持 'YYYY-MM-DD' 或完整 ISO8601（自动补全为 UTC）。
    """
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未配置 X_BEARER_TOKEN，无法使用全档案搜索")

    def _to_iso(s: str) -> str:
        s = s.strip()
        if not s:
            return ""
        if len(s) == 10:  # YYYY-MM-DD
            s += "T00:00:00Z"
        elif not s.endswith("Z") and "+" not in s:
            s += "Z"
        return s

    start_time = _to_iso(since)
    end_time = _to_iso(until)

    query = f"from:{handle} -is:retweet"
    if not include_replies:
        query += " -is:reply"

    headers = {"Authorization": f"Bearer {token}"}
    tweets = []
    next_token = ""
    while len(tweets) < max_total:
        params = {
            "query": query,
            "max_results": 500,
            "tweet.fields": "created_at,entities,text",
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if next_token:
            params["next_token"] = next_token
        qs = urllib.parse.urlencode(params)
        raw = _http_get(f"https://api.x.com/2/tweets/search/all?{qs}", headers=headers)
        payload = json.loads(raw)
        data = payload.get("data", [])
        if not data:
            break
        for item in data:
            urls = []
            for u in item.get("entities", {}).get("urls", []):
                exp = u.get("expanded_url") or u.get("url", "")
                if exp and _is_external(exp):
                    urls.append(exp)
            urls = list(dict.fromkeys(urls + _extract_article_urls(item.get("text", ""))))
            tweets.append(Tweet(
                kol_handle=handle,
                id=item.get("id", ""),
                text=_clean_text(item.get("text", "")),
                created_at=item.get("created_at", ""),
                tweet_url=f"https://x.com/{handle}/status/{item.get('id', '')}",
                article_urls=urls,
                source="x_api_archive",
            ))
        next_token = payload.get("meta", {}).get("next_token", "")
        if not next_token:
            break
    return tweets[:max_total]


# ════════════════════════════════════════════════════════════════════
#  后端 2/3：基于 RSS 的 Nitter / RSSHub
# ════════════════════════════════════════════════════════════════════

def _parse_rss(xml_bytes: bytes, handle: str, source: str, limit: int) -> list:
    """最小化 RSS 解析（不依赖 feedparser）。"""
    root = ET.fromstring(xml_bytes)
    # RSS 2.0: channel/item
    items = root.findall(".//item")
    tweets = []
    for it in items[:limit]:
        title = (it.findtext("title") or "").strip()
        desc = it.findtext("description") or ""
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        # tweet 文本优先用 description（含完整正文），title 常被截断
        text = _clean_text(desc) or _clean_text(title)
        tid = ""
        m = re.search(r"/status/(\d+)", link)
        if m:
            tid = m.group(1)
        tweets.append(Tweet(
            kol_handle=handle,
            id=tid,
            text=text,
            created_at=pub,
            tweet_url=link.replace("nitter.net", "x.com") if link else "",
            article_urls=_extract_article_urls(desc, title),
            source=source,
        ))
    return tweets


def fetch_via_nitter(handle: str, limit: int = 10) -> list:
    base = os.environ.get("NITTER_BASE", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("未配置 NITTER_BASE，跳过 nitter 后端")
    xml_bytes = _http_get(f"{base}/{handle}/rss")
    return _parse_rss(xml_bytes, handle, "nitter", limit)


def fetch_via_rsshub(handle: str, limit: int = 10) -> list:
    base = os.environ.get("RSSHUB_BASE", "https://rsshub.app").strip().rstrip("/")
    key = os.environ.get("RSSHUB_KEY", "").strip()
    suffix = f"?key={key}" if key else ""
    xml_bytes = _http_get(f"{base}/twitter/user/{handle}{suffix}")
    return _parse_rss(xml_bytes, handle, "rsshub", limit)


# ════════════════════════════════════════════════════════════════════
#  统一调度：按优先级依次尝试，任一成功即返回
# ════════════════════════════════════════════════════════════════════

BACKENDS = {
    "x_api": fetch_via_x_api,
    "nitter": fetch_via_nitter,
    "rsshub": fetch_via_rsshub,
}


def fetch_tweets(handle: str, limit: int = 10) -> tuple[list, str]:
    """
    返回 (tweets, 实际使用的后端名)。
    优先用 KOL_SOURCE 指定的后端，失败则按 BACKENDS 顺序降级。
    """
    preferred = os.environ.get("KOL_SOURCE", "").strip().lower()
    order = []
    if preferred in BACKENDS:
        order.append(preferred)
    order += [b for b in BACKENDS if b not in order]

    errors = []
    for name in order:
        try:
            tweets = BACKENDS[name](handle, limit)
            if tweets:
                return tweets, name
            errors.append(f"{name}: 返回空")
        except urllib.error.HTTPError as e:
            errors.append(f"{name}: HTTP {e.code}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    # 全部失败：返回空 + 错误摘要
    return [], "FAILED(" + "; ".join(errors) + ")"


def fetch_tweets_archive(
    handle: str, since: str, until: str = "", max_total: int = 500,
    include_replies: bool = False,
) -> tuple[list, str]:
    """回溯抓取模式：仅支持 x_api（需 pay-per-use 权限），失败直接报错，不降级。"""
    try:
        tweets = fetch_via_x_api_archive(handle, since, until, max_total, include_replies)
        return tweets, "x_api_archive"
    except urllib.error.HTTPError as e:
        return [], f"FAILED(x_api_archive: HTTP {e.code})"
    except Exception as e:  # noqa: BLE001
        return [], f"FAILED(x_api_archive: {e})"
