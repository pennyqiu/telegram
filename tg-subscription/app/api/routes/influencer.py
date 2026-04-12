"""
GET /api/v1/influencer-updates
读取 Celery 任务写入 Redis 的投资大师最新内容缓存，直接返回给前端。
"""

import json
import logging

import redis as redis_lib
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.tasks.influencer_tracker import REDIS_KEY, fetch_influencer_updates

log = logging.getLogger(__name__)
router = APIRouter()


def _get_redis():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


@router.get("/influencer-updates")
async def get_influencer_updates(refresh: bool = False):
    """
    返回最新的投资大师内容更新。

    - 正常情况下直接返回 Redis 缓存（TTL 25 小时）
    - ?refresh=true  立即重新抓取（会增加响应时间约 5-15 秒）
    - 缓存不存在时自动触发后台任务，并返回 202 + 提示信息
    """
    r = _get_redis()

    if refresh:
        # 同步执行（仅供管理员手动刷新使用）
        try:
            fetch_influencer_updates.apply()
        except Exception as e:
            log.error("refresh failed: %s", e)
            raise HTTPException(status_code=500, detail=f"刷新失败: {e}")

    raw = r.get(REDIS_KEY)

    if not raw:
        # 缓存未命中：触发后台任务，返回 202
        fetch_influencer_updates.delay()
        return JSONResponse(
            status_code=202,
            content={
                "status": "pending",
                "message": "内容正在后台抓取，通常需要 10-20 秒，请稍后刷新页面。",
                "sources": {},
            },
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="缓存数据损坏，请使用 ?refresh=true 重新抓取")

    return JSONResponse(content={"status": "ok", **data})
