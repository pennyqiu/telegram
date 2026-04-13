"""重建 Redis 中的播客索引（从 /audio/ 目录扫描 MP3，并从 RSS/网页补全标题）"""
import html
import json
import re
import sys
from pathlib import Path

import httpx
import redis

REDIS_KEY = "podcast_episodes"
AUDIO_DIR = Path("/audio")
RSS_URL   = "https://rationalreminder.libsyn.com/rss"

r = redis.from_url("redis://redis:6379/0", decode_responses=True)


def _clean(text: str) -> str:
    """反转义 HTML 实体并去掉多余后缀"""
    text = html.unescape(text)
    text = re.sub(r"\s*[—\-|]\s*Rational Reminder.*$", "", text).strip()
    return text


def fetch_rss_titles() -> dict:
    """从 RSS feed 返回 {发布日期字符串: (标题, 链接)} 映射"""
    mapping = {}
    try:
        resp = httpx.get(RSS_URL, timeout=20, follow_redirects=True)
        for item in re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL):
            title_m = re.search(r"<title><!\[CDATA\[(.*?)]]></title>", item) or \
                      re.search(r"<title>(.*?)</title>", item)
            link_m  = re.search(r"<link>(.*?)</link>", item)
            pub_m   = re.search(r"<pubDate>(.*?)</pubDate>", item)
            if title_m and pub_m:
                pub = pub_m.group(1).strip()
                # e.g. "Thu, 02 Apr 2026 ..." → key "Thu  02 Apr 2026"
                # 格式化成与文件名一致
                parts = pub.split()
                if len(parts) >= 4:
                    key = f"{parts[0].rstrip(',')}  {parts[1]} {parts[2]} {parts[3]}"
                    mapping[key] = (
                        title_m.group(1).strip(),
                        link_m.group(1).strip() if link_m else "https://rationalreminder.ca/podcast",
                    )
    except Exception as e:
        print(f"  RSS fetch failed: {e}", file=sys.stderr)
    return mapping


def fetch_episode_title(num: int) -> tuple[str, str]:
    """从 rationalreminder.ca/podcast/{num} 抓取标题"""
    url = f"https://rationalreminder.ca/podcast/{num}"
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        # 尝试 <title> 标签
        m = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # 去掉 " — Rational Reminder" 等后缀
            title = re.sub(r"\s*[—\-|]\s*Rational Reminder.*$", "", raw).strip()
            if title:
                return _clean(title), url
        # 备选：<h1>
        m2 = re.search(r"<h1[^>]*>(.*?)</h1>", resp.text, re.IGNORECASE | re.DOTALL)
        if m2:
            title = re.sub(r"<[^>]+>", "", m2.group(1)).strip()
            if title:
                return _clean(title), url
    except Exception as e:
        print(f"  title fetch failed for ep{num}: {e}", file=sys.stderr)
    return f"Episode {num}", url


# ── 主流程 ────────────────────────────────────────────────────────────────────
print("Fetching RSS feed for episode titles...")
rss = fetch_rss_titles()
print(f"  Got {len(rss)} RSS entries")

episodes = []
mp3_files = sorted(AUDIO_DIR.glob("*.mp3"))
print(f"Found {len(mp3_files)} MP3 files")

for mp3 in mp3_files:
    name = mp3.stem

    ep_match = re.search(r'ep(\d+)$', name)
    if ep_match:
        num = int(ep_match.group(1))
        print(f"  Fetching title for Episode {num}...")
        title, url = fetch_episode_title(num)
        date = f"ep{num}"
    else:
        date_part = re.sub(r'^rational_reminder_', '', name).replace('_', ' ').strip()
        rss_entry = rss.get(date_part)
        if rss_entry:
            title, url = rss_entry
        else:
            title = f"Rational Reminder — {date_part}"
            url   = "https://rationalreminder.ca/podcast"
        date = date_part

    print(f"  {mp3.name} → {title}")
    episodes.append({
        "id": name,
        "source": "rational_reminder",
        "source_name": "Rational Reminder",
        "title": title,
        "date": date,
        "original_url": url,
        "mp3_file": mp3.name,
        "summary_preview": "",
        "created_at": "2026-04-12",
    })

r.set(REDIS_KEY, json.dumps(episodes, ensure_ascii=False))
print(f"\nrebuilt: {len(episodes)} episodes saved to Redis key '{REDIS_KEY}'")
