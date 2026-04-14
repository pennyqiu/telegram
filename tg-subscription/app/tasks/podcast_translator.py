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
        "rss": "https://rationalreminder.libsyn.com/rss",
        "type": "rr_website",          # 从 rationalreminder.ca 抓取文字稿
        "max_episodes": 3,             # 每次最多处理最新 3 集
    },
    # Ben Felix YouTube 字幕太短（自动字幕通常只有几百字），暂时停用
    # {
    #     "key": "ben_felix",
    #     "name": "Ben Felix",
    #     "rss": "https://www.youtube.com/feeds/videos.xml?channel_id=UCDXTQ8nWmx_EhZ2v-kp7QxA",
    #     "type": "youtube_caption",
    #     "max_episodes": 2,
    # },
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
            # 提取原版 MP3（enclosure url="..."）
            enclosure = item.find("enclosure")
            original_mp3 = enclosure.get("url", "") if enclosure is not None else ""
            # 从链接提取 episode slug（如 rationalreminder.ca/podcast/310）
            m = re.search(r"rationalreminder\.ca/podcast/([^/?]+)", link)
            slug = m.group(1) if m else ""
            items.append({
                "title": t("title"),
                "url": f"https://rationalreminder.ca/podcast/{slug}" if slug else link,
                "date": t("pubDate")[:16],
                "slug": slug,
                "original_mp3": original_mp3,
            })
    return items


def fetch_rr_transcript(episode_url: str, title: str = "") -> str:
    """
    从 Rational Reminder 集数页面抓取文字稿。
    优先用 rationalreminder.ca/podcast/<num> 格式的官网地址。
    """
    # 从标题或 URL 提取集数号，构造官网地址
    ep_num = ""
    # 从标题提取 "Episode 402" 里的数字
    m = re.search(r"Episode\s+(\d+)", title, re.IGNORECASE)
    if m:
        ep_num = m.group(1)
    # 从 URL 提取末尾数字
    if not ep_num:
        m = re.search(r"/(\d+)[^/]*$", episode_url)
        if m:
            ep_num = m.group(1)

    urls_to_try = []
    if ep_num:
        urls_to_try.append(f"https://rationalreminder.ca/podcast/{ep_num}")
    urls_to_try.append(episode_url)  # 兜底原始 URL

    for url in urls_to_try:
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
                resp = c.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            log.warning("RR transcript fetch failed %s: %s", url, e)
            continue

        # Squarespace / rationalreminder.ca 常用结构
        patterns = [
            r'<div[^>]+class="[^"]*sqs-block-content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]+class="[^"]*transcript[^"]*"[^>]*>(.*?)</(?:div|section)>',
            r'<div[^>]+class="[^"]*show.?notes?[^"]*"[^>]*>(.*?)</(?:div|section)>',
            r'<div[^>]+class="[^"]*entry.?content[^"]*"[^>]*>(.*?)</div>',
            r'<article[^>]*>(.*?)</article>',
            r'<details[^>]*>(.*?)</details>',
            r'<div[^>]+class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
        ]
        best = ""
        for pat in patterns:
            for m in re.finditer(pat, html, re.IGNORECASE | re.DOTALL):
                text = re.sub(r"<[^>]+>", " ", m.group(1))
                text = re.sub(r"\s{2,}", " ", text).strip()
                if len(text) > len(best):
                    best = text
            if len(best) > 2000:
                break

        if len(best) > 500:
            log.info("transcript fetched from %s: %d chars", url, len(best))
            return best

        # 兜底：去掉 script/style 后提取全部正文
        html_clean = re.sub(r"<(?:script|style|nav|header|footer)[^>]*>.*?</(?:script|style|nav|header|footer)>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html_clean)
        text = re.sub(r"\s{2,}", " ", text).strip()
        if len(text) > 500:
            log.info("transcript fallback from %s: %d chars", url, len(text))
            return text

    return ""


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
    # 按日期降序，保留最新 200 集（不设过期时间，由 Redis AOF 持久化保证不丢失）
    episodes.sort(key=lambda x: x.get("date", ""), reverse=True)
    r.set(REDIS_PODCAST_KEY, json.dumps(episodes[:200], ensure_ascii=False))


def episode_exists(episodes: list[dict], ep_id: str) -> bool:
    # 同时检查 mp3 文件名，兼容 rebuild_index.py 生成的不同 id 格式
    safe_name = re.sub(r"[^\w-]", "_", ep_id)[:60]
    mp3_name = f"{safe_name}.mp3"
    return any(e["id"] == ep_id or e.get("mp3_file", "") == mp3_name for e in episodes)


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
        transcript = fetch_rr_transcript(item["url"], title=item["title"])
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
        "original_mp3": item.get("original_mp3", ""),
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

    # 防护：如果 Redis 索引为空但磁盘上有 MP3，先自动重建索引
    if not episodes and AUDIO_DIR.exists():
        mp3_count = len(list(AUDIO_DIR.glob("*.mp3")))
        if mp3_count > 0:
            log.warning("Redis 索引为空但磁盘有 %d 个 MP3，跳过本次覆盖，请手动运行 rebuild_index.py", mp3_count)
            return {"skipped": "index empty but mp3 files exist, run rebuild_index.py first"}

    for source in PODCAST_SOURCES:
        items = fetch_rss_items(source["rss"], limit=source["max_episodes"])
        source_episodes_to_process = [
            (source, item) for item in items
            if not episode_exists(episodes, f"{source['key']}_{item.get('video_id') or item.get('slug') or item['date']}")
        ]

        # 并发处理同一来源的多集（最多2个并发，避免触发 OpenAI 限速）
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(process_episode, src, itm, episodes): (src, itm)
                for src, itm in source_episodes_to_process
            }
            for future in as_completed(futures):
                src, itm = futures[future]
                try:
                    meta = future.result()
                    if meta:
                        episodes.append(meta)
                        new_count += 1
                except RuntimeError as e:
                    log.error("⚠️ 停止任务：%s", e)
                    save_index(r, episodes)
                    return {"new_episodes": new_count, "error": str(e), "stopped_early": True}
                except Exception as e:
                    log.error("episode failed [%s] %s: %s", src["key"], itm.get("title"), e)

    save_index(r, episodes)
    log.info("translate_podcasts done: %d new episodes", new_count)
    return {"new_episodes": new_count, "total": len(episodes)}


# ══════════════════════════════════════════════════════════════════════════════
# 回溯翻译：按指定集数批量处理历史集
# ══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="backfill_episodes", bind=True, max_retries=0, time_limit=7200)
def backfill_episodes(self, episode_numbers: list[int], source_key: str = "rational_reminder"):
    """
    回溯翻译指定集数列表。

    手动触发示例：
        docker compose exec worker celery -A app.tasks.celery_app call backfill_episodes \
          --args='[[100,101,102,103,104,105,106,107,108,109,110]]'

    参数：
        episode_numbers: 要翻译的集数列表，如 [100, 101, 102]
        source_key: 来源键，目前支持 "rational_reminder"
    """
    import redis as redis_lib
    from app.core.config import settings
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not settings.openai_api_key:
        log.warning("OPENAI_API_KEY 未设置，跳过回溯翻译")
        return {"skipped": "no openai key"}

    r = redis_lib.from_url(settings.redis_url, decode_responses=True)
    episodes = load_index(r)
    new_count = 0
    failed = []

    # 构造虚拟 item 列表
    items = []
    for num in episode_numbers:
        ep_id = f"{source_key}_ep{num}"
        if episode_exists(episodes, ep_id):
            log.info("skip (already processed): episode %d", num)
            continue
        items.append({
            "title": f"Episode {num}",
            "url": f"https://rationalreminder.ca/podcast/{num}",
            "date": f"ep{num}",
            "slug": str(num),
            "_ep_id_override": ep_id,
        })

    if not items:
        log.info("backfill: all episodes already processed")
        return {"new_episodes": 0, "total": len(episodes), "message": "已全部处理过"}

    log.info("backfill: %d episodes to process: %s", len(items), [i["title"] for i in items])

    source = next((s for s in PODCAST_SOURCES if s["key"] == source_key), None)
    if not source:
        return {"error": f"unknown source_key: {source_key}"}

    # 并发处理，最多2个同时跑
    def _process(item):
        ep_id = item.pop("_ep_id_override")
        transcript = fetch_rr_transcript(item["url"], title=item["title"])
        if len(transcript) < 200:
            log.warning("transcript too short for %s, skip", item["title"])
            return None
        summary = gpt_summarize(transcript, title=item["title"])
        safe_name = re.sub(r"[^\w-]", "_", ep_id)[:60]
        mp3_path = AUDIO_DIR / f"{safe_name}.mp3"
        generate_tts_mp3(summary, mp3_path)
        meta = {
            "id": ep_id,
            "source": source_key,
            "source_name": source["name"],
            "title": item["title"],
            "date": item["date"],
            "original_url": item["url"],
            "mp3_file": mp3_path.name,
            "summary_preview": summary[:120] + "…",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d"),
            "backfill": True,
        }
        log.info("backfill episode ready: %s", meta["title"])
        return meta

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_process, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                meta = future.result()
                if meta:
                    episodes.append(meta)
                    new_count += 1
                    save_index(r, episodes)  # 每完成一集就保存，防止中途失败丢数据
            except RuntimeError as e:
                log.error("⚠️ 停止回溯：%s", e)
                return {"new_episodes": new_count, "error": str(e), "failed": failed}
            except Exception as e:
                log.error("backfill failed %s: %s", item.get("title"), e)
                failed.append(item.get("title"))

    save_index(r, episodes)
    log.info("backfill done: %d new episodes, %d failed", new_count, len(failed))
    return {"new_episodes": new_count, "total": len(episodes), "failed": failed}

