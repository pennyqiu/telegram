"""
Web 看板服务（量化策略「独立切页」）

提供一个轻量 FastAPI 服务，dashboard/index.html 通过这些接口实时展示：
  - 账户状态 / 持仓 / 当日订单数
  - 策略信号与订单事件流（来自 hooks 总线缓存）
  - 暂停 / 恢复策略下单（紧急开关）
  - 手动下单（仍然经过 IBTradingClient 的全部安全护栏）

接口前缀 /api，根路径 / 返回看板页面。
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

import config
from hooks import recent_events
from scheduler import Engine, STATE

logger = logging.getLogger(__name__)

_DASHBOARD = Path(__file__).parent.parent / "dashboard" / "index.html"


class ManualOrder(BaseModel):
    symbol: str
    action: str               # BUY / SELL
    quantity: float
    order_type: str = "MKT"   # MKT / LMT
    limit_price: float = 0.0


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="ib_quant 看板", docs_url="/api/docs")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        if _DASHBOARD.exists():
            return _DASHBOARD.read_text(encoding="utf-8")
        return "<h1>dashboard/index.html 未找到</h1>"

    @app.get("/api/status")
    async def status():
        return {
            "mode": "live" if config.is_live() else "paper",
            "dry_run": config.GUARDS.dry_run,
            "running": STATE["running"],
            "paused": STATE["paused"],
            "last_poll": STATE["last_poll"],
            "account": STATE["account"],
            "orders_today": STATE["orders_today"],
            "strategies": [s.name for s in engine.strategies],
            "universe": config.STRATEGY.universe,
            "guards": {
                "max_order_notional": config.GUARDS.max_order_notional,
                "max_position_notional": config.GUARDS.max_position_notional,
                "max_daily_orders": config.GUARDS.max_daily_orders,
                "whitelist": config.GUARDS.symbol_whitelist,
            },
        }

    @app.get("/api/positions")
    async def positions():
        return STATE["positions"]

    @app.get("/api/events")
    async def events(limit: int = 50):
        return recent_events(limit)

    @app.get("/api/quote/{symbol}")
    async def quote(symbol: str):
        q = await engine.client.get_quote(symbol.upper())
        if not q:
            return JSONResponse({"error": "无行情"}, status_code=404)
        return {"symbol": q.symbol, "last": q.last, "bid": q.bid,
                "ask": q.ask, "close": q.close, "mid": q.mid}

    @app.post("/api/pause")
    async def pause():
        STATE["paused"] = True
        return {"paused": True}

    @app.post("/api/resume")
    async def resume():
        STATE["paused"] = False
        return {"paused": False}

    @app.post("/api/order")
    async def manual_order(order: ManualOrder):
        """手动下单——依然经过全部安全护栏与 DRY_RUN。"""
        if order.order_type.upper() == "LMT":
            r = await engine.client.place_limit_order(
                order.symbol, order.action, order.quantity, order.limit_price)
        else:
            r = await engine.client.place_market_order(
                order.symbol, order.action, order.quantity)
        return {
            "accepted": r.accepted, "dry_run": r.dry_run, "status": r.status,
            "reason": r.reason, "order_id": r.order_id,
        }

    return app


async def start_web(engine: Engine) -> None:
    app = create_app(engine)
    cfg = uvicorn.Config(
        app, host=config.WEB.host, port=config.WEB.port,
        log_level="warning", loop="asyncio",
    )
    server = uvicorn.Server(cfg)
    await server.serve()
