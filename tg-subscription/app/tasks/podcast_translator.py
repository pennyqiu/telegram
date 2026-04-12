"""
播客翻译管道：英文 → 普通话音频（完整翻译）

支持来源：
  1. Rational Reminder  — 官网提供完整文字稿，直接抓取
  2. Ben Felix YouTube  — 抓取 YouTube 自动字幕（VTT 格式）

流程：
  每集英文文字稿（10,000-20,000 词）
    └→ GPT-4o-mini 完整翻译成中文（不压缩）
         └→ OpenAI TTS nova 声音生成 MP3（分段合并）
              └→ 保存到 /audio/
                   └→ 元数据写入 Redis

调度：每天 08:00 Asia/Shanghai 检查新集并生成
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

# ── 目录配置 ────────────────────────────────────────────────────────────────
# docker-compose 会把宿主机的 ./audio_output 挂载到容器 /audio
AUDIO_DIR = Path("/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

REDIS_PODCAST_KEY = "podcast_episodes"   # Redis 中的节目索引
CACHE_TTL = 60 * 60 * 24 * 30           # 索引缓存 30 天

HTTP_TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── 来源配置 ─────────────────────────────────────────────────────────────────
PODCAST_SOURCES = [
    {
        "key": "rational_reminder",
        "name": "Rational Reminder",
        "rss": "https://feeds.simplecast.com/5fqcCl3W",
        "type": "rr_website",          # 从 rationalreminder.ca 抓取文字稿
        "max_episodes": 3,             # 每次最多处理最新 3 集
    },
    {
        "key": "ben_felix",
        "name": "Ben Felix",
        "rss": "https://www.youtube.com/feeds/videos.xml?channel_id=UC0kgMCHN2YE0lAg95qLzEWg",
        "type": "youtube_caption",     # 抓取 YouTube 自动字幕
        "max_episodes": 2,
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# 文字稿抓取
# ══════════════════════════════════════════════════════════════════════════════

def fetch_rss_items(rss_url: str, limit: int = 5) -> list[dict]:
    """从 RSS/Atom 获取最新条目 [{title, url, date, video_id?}]"""
    items = []
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(rss_url)
            r.raise_for_status()
            root = ET.fromstring(r.text)
    except Exception as e:
        log.warning("RSS fetch failed %s: %s", rss_url, e)
        return items

    # YouTube Atom
    if "youtube.com" in rss_url:
        yt_ns = "http://www.youtube.com/xml/schemas/2015"
        atom_ns = "http://www.w3.org/2005/Atom"
        for entry in root.findall(f"{{{atom_ns}}}entry")[:limit]:
            vid_el = entry.find(f"{{{yt_ns}}}videoId")
            title  = (entry.findtext(f"{{{atom_ns}}}title") or "").strip()
            link   = entry.find(f"{{{atom_ns}}}link")
            url    = link.get("href", "") if link is not None else ""
            published = (entry.findtext(f"{{{atom_ns}}}published") or "")[:10]
            items.append({
                "title": title,
                "url": url,
                "date": published,
                "video_id": vid_el.text if vid_el is not None else "",
            })
    else:
        # RSS 2.0
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item")[:limit]:
            def t(tag): return (item.findtext(tag) or "").strip()
            link = t("link") or t("enclosure")
            # 从链接提取 episode slug（如 rationalreminder.ca/podcast/310）
            m = re.search(r"rationalreminder\.ca/podcast/([^/?]+)", link)
            slug = m.group(1) if m else ""
            items.append({
                "title": t("title"),
                "url": f"https://rationalreminder.ca/podcast/{slug}" if slug else link,
                "date": t("pubDate")[:16],
                "slug": slug,
            })
    return items


def fetch_rr_transcript(episode_url: str) -> str:
    """
    从 Rational Reminder 集数页面抓取文字稿。
    文字稿在 <div class="show-notes"> 或 <div class="episode-show-notes"> 中，
    也可能在 <details> 标签内。
    """
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            resp = c.get(episode_url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        log.warning("RR transcript fetch failed %s: %s", episode_url, e)
        return ""

    # 先尝试提取 <div class="transcript"> 或 <div class="show-notes">
    patterns = [
        r'class="[^"]*transcript[^"]*"[^>]*>(.*?)</div>',
        r'class="[^"]*show.notes[^"]*"[^>]*>(.*?)</section>',
        r'<details[^>]*>(.*?)</details>',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m and len(m.group(1)) > 500:
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            text = re.sub(r"\s{2,}", " ", text).strip()
            if len(text) > 500:
                return text  # 完整返回，不截断

    # 兜底：提取页面全部正文（去掉 <script>/<style>）
    html_clean = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html_clean = re.sub(r"<style[^>]*>.*?</style>", "", html_clean, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html_clean)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def fetch_youtube_captions(video_id: str) -> str:
    """
    尝试获取 YouTube 自动字幕（英文）。
    先用 timedtext API，若失败返回空字符串。
    """
    if not video_id:
        return ""
    urls_to_try = [
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&fmt=vtt",
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en-US&fmt=vtt",
        f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en",
    ]
    for url in urls_to_try:
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers=HEADERS) as c:
                resp = c.get(url)
                if resp.status_code == 200 and len(resp.text) > 200:
                    # VTT 格式：去掉时间戳行，提取纯文字
                    lines = []
                    for line in resp.text.splitlines():
                        if "-->" in line or line.startswith("WEBVTT"):
                            continue
                        clean = re.sub(r"<[^>]+>", "", line).strip()
                        if clean:
                            lines.append(clean)
                    text = " ".join(lines)
                    text = re.sub(r"\s{2,}", " ", text)
                    if len(text) > 300:
                        return text  # 完整返回，不截断
        except Exception as e:
            log.debug("caption fetch %s failed: %s", url, e)
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# GPT 翻译 + 摘要
# ══════════════════════════════════════════════════════════════════════════════

SUMMARY_PROMPT = """你是一位专业的金融翻译，请将以下英文播客文字稿**完整翻译成中文**。

翻译要求：
1. 完整翻译全部内容，不省略、不压缩
2. 语言流畅自然，适合"通勤时收听"——句子保持节奏感
3. 人名/品牌/术语保留英文原名（如 Fama-French、VOO、Ben Felix、ETF）
4. **只输出译文正文，不要加任何标题或前言**

原文字稿：
---
{transcript}
---"""


def gpt_summarize(transcript: str, title: str, chars: int = 0) -> str:
    """调用 OpenAI GPT 将英文文字稿完整翻译成中文"""
    from openai import OpenAI
    from app.core.config import settings

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY 未配置，请在 .env 中设置")

    client = OpenAI(api_key=settings.openai_api_key)

    # GPT-4o-mini 上下文 128k token；英文字符约 4 chars/token，可处理约 500k 字符
    # 超长文字稿分段翻译再合并
    CHUNK_SIZE = 80000  # 每段约 20000 词，大多数播客一集能一次处理
    if len(transcript) <= CHUNK_SIZE:
        chunks_in = [transcript]
    else:
        # 按段落分割，避免截断句子
        chunks_in = []
        while len(transcript) > CHUNK_SIZE:
            cut = transcript.rfind("\n", 0, CHUNK_SIZE)
            if cut < 1000:
                cut = CHUNK_SIZE
            chunks_in.append(transcript[:cut])
            transcript = transcript[cut:].lstrip()
        if transcript:
            chunks_in.append(transcript)

    translated_parts = []
    for i, chunk in enumerate(chunks_in):
        prompt = SUMMARY_PROMPT.format(transcript=chunk)
        try:
            resp = client.chat.completions.create(
                model=settings.openai_translate_model,
                messages=[
                    {"role": "system", "content": "你是专业的金融内容翻译，精通中英文投资领域知识。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=16000,  # 每段最多 16000 token 输出
            )
            translated_parts.append(resp.choices[0].message.content.strip())
            log.info("translated chunk %d/%d for: %s", i + 1, len(chunks_in), title)
        except Exception as e:
            err_str = str(e)
            if "insufficient_quota" in err_str or "429" in err_str or "quota" in err_str.lower():
                raise RuntimeError(
                    "⚠️ OpenAI API 额度已用完。请前往 platform.openai.com/account/billing 充值后重试。"
                ) from e
            log.error("GPT translate failed: %s", e)
            raise

    return "\n\n".join(translated_parts)


# ══════════════════════════════════════════════════════════════════════════════
# TTS 生成
# ══════════════════════════════════════════════════════════════════════════════

def generate_tts_mp3(chinese_text: str, output_path: Path) -> None:
    """
    使用 OpenAI TTS 将中文文本转为 MP3。
    tts-1 模型，单次最大 4096 字符；超长文本分段合并。
    """
    from openai import OpenAI
    from app.core.config import settings

    client = OpenAI(api_key=settings.openai_api_key)
    voice = settings.openai_tts_voice

    # 按句号/换行分块，每块不超过 4000 字符
    chunks = _split_text(chinese_text, max_len=4000)
    audio_parts: list[bytes] = []

    for chunk in chunks:
        try:
            resp = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=chunk,
                response_format="mp3",
            )
            audio_parts.append(resp.content)
        except Exception as e:
            log.error("TTS chunk failed: %s", e)
            raise

    # 直接拼接 MP3 二进制（简单拼接，无缝效果足够好）
    with open(output_path, "wb") as f:
        for part in audio_parts:
            f.write(part)

    log.info("TTS saved: %s (%d bytes)", output_path, output_path.stat().st_size)


def _split_text(text: str, max_len: int = 4000) -> list[str]:
    """按句子拆分文本，每段不超过 max_len 字符"""
    # 按句号、问号、感叹号分割
    sentences = re.split(r"([。？！\.!?])", text)
    # 重新拼合（把标点符号加回去）
    merged: list[str] = []
    buf = ""
    i = 0
    while i < len(sentences):
        seg = sentences[i]
        punc = sentences[i + 1] if i + 1 < len(sentences) else ""
        piece = seg + punc
        if len(buf) + len(piece) > max_len and buf:
            merged.append(buf.strip())
            buf = piece
        else:
            buf += piece
        i += 2
    if buf.strip():
        merged.append(buf.strip())
    return merged or [text]


# ══════════════════════════════════════════════════════════════════════════════
# Redis 索引管理
# ══════════════════════════════════════════════════════════════════════════════

def load_index(r) -> list[dict]:
    raw = r.get(REDIS_PODCAST_KEY)
    return json.loads(raw) if raw else []


def save_index(r, episodes: list[dict]) -> None:
    # 按日期降序，保留最新 50 集
    episodes.sort(key=lambda x: x.get("date", ""), reverse=True)
    r.setex(REDIS_PODCAST_KEY, CACHE_TTL, json.dumps(episodes[:50], ensure_ascii=False))


def episode_exists(episodes: list[dict], ep_id: str) -> bool:
    return any(e["id"] == ep_id for e in episodes)


# ══════════════════════════════════════════════════════════════════════════════
# 单集处理
# ══════════════════════════════════════════════════════════════════════════════

def process_episode(source: dict, item: dict, episodes: list[dict]) -> dict | None:
    """
    处理单集：抓取文字稿 → 翻译 → TTS → 保存。
    返回新的 episode 元数据，或 None（已处理 / 无字幕）。
    """

    ep_id = f"{source['key']}_{item.get('video_id') or item.get('slug') or item['date']}"
    if episode_exists(episodes, ep_id):
        log.info("skip (already processed): %s", ep_id)
        return None

    log.info("processing: %s — %s", source["name"], item["title"])

    # 1. 获取文字稿
    if source["type"] == "rr_website":
        transcript = fetch_rr_transcript(item["url"])
    elif source["type"] == "youtube_caption":
        transcript = fetch_youtube_captions(item.get("video_id", ""))
    else:
        transcript = ""

    if len(transcript) < 200:
        log.warning("transcript too short for %s, skip", item["title"])
        return None

    # 2. GPT 完整翻译
    summary = gpt_summarize(
        transcript,
        title=item["title"],
    )

    # 3. TTS 生成 MP3
    safe_name = re.sub(r"[^\w-]", "_", ep_id)[:60]
    mp3_path = AUDIO_DIR / f"{safe_name}.mp3"
    generate_tts_mp3(summary, mp3_path)

    meta = {
        "id": ep_id,
        "source": source["key"],
        "source_name": source["name"],
        "title": item["title"],
        "date": item["date"][:10] if item["date"] else "",
        "original_url": item["url"],
        "mp3_file": mp3_path.name,
        "summary_preview": summary[:120] + "…",  # 前 120 字预览
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    log.info("episode ready: %s", meta["title"])
    return meta


# ══════════════════════════════════════════════════════════════════════════════
# Celery 任务
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="translate_podcasts", bind=True, max_retries=1)
def translate_podcasts(self):
    """
    每天 08:00 运行：检查各来源最新集，生成普通话音频摘要。

    手动触发：
        celery -A app.tasks.celery_app call translate_podcasts
    """
    from app.core.config import settings
    import redis as redis_lib

    if not settings.openai_api_key:
        log.warning("OPENAI_API_KEY 未设置，跳过播客翻译任务")
        return {"skipped": "no openai key"}

    r = redis_lib.from_url(settings.redis_url, decode_responses=True)
    episodes = load_index(r)
    new_count = 0

    for source in PODCAST_SOURCES:
        items = fetch_rss_items(source["rss"], limit=source["max_episodes"])
        for item in items:
            try:
                meta = process_episode(source, item, episodes)
                if meta:
                    episodes.append(meta)
                    new_count += 1
            except RuntimeError as e:
                # 额度耗尽等明确错误，记录后停止继续消耗
                log.error("⚠️ 停止任务：%s", e)
                save_index(r, episodes)
                return {"new_episodes": new_count, "error": str(e), "stopped_early": True}
            except Exception as e:
                log.error("episode failed [%s] %s: %s", source["key"], item.get("title"), e)

    save_index(r, episodes)
    log.info("translate_podcasts done: %d new episodes", new_count)
    return {"new_episodes": new_count, "total": len(episodes)}
