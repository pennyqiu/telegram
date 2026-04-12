"""
定时抓取投资大师最新产出，存入 Redis，供前端 API 查询。

抓取源：
  - Damodaran   : Substack RSS
  - Ben Felix   : YouTube 频道 RSS
  - Howard Marks: Oaktree Capital 网页（无 RSS，直接解析 HTML）
  - Rational Reminder: 播客 RSS

调度：每天 07:00 (Asia/Shanghai) 自动运行，结果缓存 25 小时。
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

REDIS_KEY = "influencer_updates"
CACHE_TTL = 90_000          # 25 小时，单位秒
HTTP_TIMEOUT = 20           # 单次请求超时

SOURCES = {
    "damodaran": {
        "name": "Aswath Damodaran",
        "label": "Substack 最新文章",
        "type": "rss",
        "url": "https://aswathdamodaran.substack.com/feed",
    },
    "ben_felix": {
        "name": "Ben Felix",
        "label": "YouTube 最新视频",
        "type": "rss",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC0kgMCHN2YE0lAg95qLzEWg",
    },
    "rational_reminder": {
        "name": "Rational Reminder",
        "label": "播客最新集",
        "type": "rss",
        "url": "https://feeds.simplecast.com/5fqcCl3W",
    },
    "howard_marks": {
        "name": "Howard Marks",
        "label": "Oaktree 最新 Memo",
        "type": "html",
        "url": "https://www.oaktreecapital.com/insights/memo",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ─── RSS / Atom 解析 ───────────────────────────────────────────────────────────

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
}


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _attr(el, tag: str, attr: str) -> str:
    child = el.find(tag)
    return (child.get(attr) or "").strip() if child is not None else ""


def parse_rss(xml_text: str, limit: int = 5) -> list[dict]:
    """解析标准 RSS 2.0 或 Atom 1.0，返回最新 limit 条"""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("RSS parse error: %s", e)
        return items

    # ── Atom 格式 ──────────────────────────────
    if root.tag in ("{http://www.w3.org/2005/Atom}feed", "feed"):
        atom_ns = "http://www.w3.org/2005/Atom"
        for entry in root.findall(f"{{{atom_ns}}}entry")[:limit]:
            link_el = entry.find(f"{{{atom_ns}}}link")
            url = link_el.get("href", "") if link_el is not None else ""
            title = entry.findtext(f"{{{atom_ns}}}title", "").strip()
            published = entry.findtext(
                f"{{{atom_ns}}}published",
                entry.findtext(f"{{{atom_ns}}}updated", "")
            ).strip()
            summary = entry.findtext(f"{{{atom_ns}}}summary", "").strip()
            # YouTube media:group/media:description
            mg = entry.find("{http://search.yahoo.com/mrss/}group")
            if mg is not None:
                desc = mg.findtext("{http://search.yahoo.com/mrss/}description", "")
                if desc:
                    summary = desc.strip()[:200]
            items.append({
                "title": title,
                "url": url,
                "date": _fmt_date(published),
                "summary": summary[:200] if summary else "",
            })

    # ── RSS 2.0 格式 ───────────────────────────
    else:
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item")[:limit]:
            title = _text(item, "title")
            link  = _text(item, "link")
            date  = _text(item, "pubDate")
            desc  = _text(item, "description")
            # 去掉 HTML 标签
            desc = re.sub(r"<[^>]+>", "", desc)[:200]
            items.append({
                "title": title,
                "url": link,
                "date": _fmt_date(date),
                "summary": desc,
            })

    return items


# ─── Howard Marks HTML 解析 ───────────────────────────────────────────────────

def parse_oaktree_memos(html: str, limit: int = 5) -> list[dict]:
    """
    从 Oaktree 备忘录页面提取最新 memo 标题和链接。
    页面结构可能随 Oaktree 改版而变化，用正则兜底。
    """
    items = []
    # 匹配形如 href="/insights/howard-marks/..." 的链接 + 附近的标题文字
    pattern = re.compile(
        r'href="(/insights/memo/[^"]+)"[^>]*>([^<]{10,200})<',
        re.IGNORECASE,
    )
    seen = set()
    for m in pattern.finditer(html):
        path, title = m.group(1), m.group(2).strip()
        if path in seen:
            continue
        seen.add(path)
        items.append({
            "title": title,
            "url": f"https://www.oaktreecapital.com{path}",
            "date": "",
            "summary": "",
        })
        if len(items) >= limit:
            break

    # 如果正则没匹配到，用更宽松的模式
    if not items:
        pattern2 = re.compile(
            r'href="(/insights/[^"]*memo[^"]*)"[^>]*>([^<]{10,150})<',
            re.IGNORECASE,
        )
        seen2: set[str] = set()
        for m in pattern2.finditer(html):
            path, title = m.group(1), m.group(2).strip()
            if path in seen2:
                continue
            seen2.add(path)
            items.append({
                "title": title,
                "url": f"https://www.oaktreecapital.com{path}",
                "date": "",
                "summary": "",
            })
            if len(items) >= limit:
                break

    return items


# ─── 日期格式化 ────────────────────────────────────────────────────────────────

def _fmt_date(raw: str) -> str:
    """将各种日期字符串统一格式化为 YYYY-MM-DD"""
    if not raw:
        return ""
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 最后尝试提取 YYYY-MM-DD 格式的子串
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else raw[:10]


# ─── 单个来源抓取 ──────────────────────────────────────────────────────────────

def fetch_source(key: str, cfg: dict) -> dict:
    result = {
        "key": key,
        "name": cfg["name"],
        "label": cfg["label"],
        "items": [],
        "error": None,
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(cfg["url"])
            resp.raise_for_status()
            if cfg["type"] == "rss":
                result["items"] = parse_rss(resp.text)
            else:
                result["items"] = parse_oaktree_memos(resp.text)
    except Exception as e:
        result["error"] = str(e)
        log.warning("fetch_source [%s] failed: %s", key, e)
    return result


# ─── Celery 主任务 ────────────────────────────────────────────────────────────

@celery_app.task(name="fetch_influencer_updates", bind=True, max_retries=2)
def fetch_influencer_updates(self):
    """
    抓取全部来源，合并后写入 Redis。
    每天 07:00 Asia/Shanghai 由 Celery Beat 触发。
    也可手动触发：
        celery -A app.tasks.celery_app call fetch_influencer_updates
    """
    import redis as redis_lib
    from app.core.config import settings

    results: dict[str, dict] = {}
    for key, cfg in SOURCES.items():
        results[key] = fetch_source(key, cfg)
        log.info(
            "fetch_source [%s]: %d items, error=%s",
            key, len(results[key]["items"]), results[key]["error"],
        )

    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sources": results,
    }

    try:
        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        r.setex(REDIS_KEY, CACHE_TTL, json.dumps(payload, ensure_ascii=False))
        log.info("influencer_updates saved to Redis (TTL=%ds)", CACHE_TTL)
    except Exception as e:
        log.error("Redis write failed: %s", e)
        raise self.retry(exc=e, countdown=300)

    return {k: len(v["items"]) for k, v in results.items()}
