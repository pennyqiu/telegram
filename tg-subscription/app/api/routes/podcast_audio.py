"""
GET  /api/v1/podcast-audio          → 返回所有已生成的普通话音频集列表
GET  /api/v1/podcast-audio/refresh  → 立即触发翻译任务（后台异步）
GET  /audio/{filename}              → 下载/串流 MP3 文件
"""

import json
import logging
from pathlib import Path

import redis as redis_lib
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.tasks.podcast_translator import AUDIO_DIR, REDIS_PODCAST_KEY

log = logging.getLogger(__name__)
router = APIRouter()


def _redis():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


@router.get("/podcast-audio")
async def list_podcast_audio(source: str = ""):
    """
    返回已生成的普通话音频集列表。
    可选 ?source=rational_reminder 或 ?source=ben_felix 过滤。
    """
    r = _redis()
    raw = r.get(REDIS_PODCAST_KEY)
    episodes: list[dict] = json.loads(raw) if raw else []

    if source:
        episodes = [e for e in episodes if e.get("source") == source]

    # 附加音频文件大小（KB）
    for ep in episodes:
        mp3 = AUDIO_DIR / ep.get("mp3_file", "")
        ep["file_size_kb"] = round(mp3.stat().st_size / 1024) if mp3.exists() else 0
        ep["available"] = mp3.exists()

    return JSONResponse(content={"total": len(episodes), "episodes": episodes})


@router.post("/podcast-audio/refresh")
async def refresh_podcast_audio(background_tasks: BackgroundTasks):
    """
    手动触发翻译任务（异步后台执行，立即返回）。
    通常由管理员调用；Celery Beat 每天 08:00 自动运行。
    """
    from app.tasks.podcast_translator import translate_podcasts
    background_tasks.add_task(translate_podcasts.delay)
    return {"status": "triggered", "message": "翻译任务已触发，通常 1-3 分钟内完成（取决于集数）"}


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """直接串流 MP3 文件（支持 HTML5 <audio> 标签）"""
    # 安全检查：只允许字母、数字、连字符、下划线、点
    import re
    if not re.match(r"^[\w\-\.]+\.mp3$", filename):
        raise HTTPException(status_code=400, detail="无效文件名")

    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")

    return FileResponse(
        path=str(path),
        media_type="audio/mpeg",
        filename=filename,
        headers={"Accept-Ranges": "bytes"},   # 支持拖拽进度条
    )
