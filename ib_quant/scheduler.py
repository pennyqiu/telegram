"""
调度编排：周期性检查数据 + 运行策略 + 每日报告 + 心跳看门狗

任务：
  1. 策略轮询（每 POLL_INTERVAL_SECONDS 秒）：拉取行情 → 跑策略 → 必要时下单。
  2. 每日报告（DAILY_REPORT_HOUR:MINUTE，北京时间）：账户净值 / 持仓 / 当日订单数。
  3. 心跳看门狗（每 5 分钟）：超过阈值未成功拉数据则告警，防静默失效。
"""

import asyncio
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config
from hooks import emit, Event
from ib_client import IBTradingClient
from strategies import build_strategies, StrategyContext

logger = logging.getLogger(__name__)

BEIJING = pytz.timezone("Asia/Shanghai")
HEARTBEAT_TIMEOUT_MINUTES = 10

# 全局共享状态，供 Web 看板读取
STATE: dict = {
    "running": False,
    "paused": False,        # 看板可临时暂停策略下单
    "last_poll": None,
    "account": {},
    "positions": [],
    "orders_today": 0,
}


class Engine:
    """把客户端、策略、状态聚合在一起，便于调度器与 Web 看板共享。"""

    def __init__(self, client: IBTradingClient):
        self.client = client
        self.strategies = build_strategies(config.STRATEGY.enabled_strategies)
        self.ctx = StrategyContext(client=client, universe=config.STRATEGY.universe)

    async def poll_once(self) -> None:
        if not self.client.is_connected():
            logger.warning("未连接，跳过本轮策略轮询")
            return

        STATE["last_poll"] = datetime.now(BEIJING).isoformat(timespec="seconds")

        # 周期性检查数据：账户 + 持仓
        snap = await self.client.get_account_snapshot()
        if snap:
            STATE["account"] = {
                "net_liquidation": snap.net_liquidation,
                "available_funds": snap.available_funds,
                "buying_power": snap.buying_power,
                "unrealized_pnl": snap.unrealized_pnl,
                "realized_pnl": snap.realized_pnl,
            }
        positions = await self.client.get_positions()
        if positions is not None:
            STATE["positions"] = [
                {"symbol": p.symbol, "sec_type": p.sec_type,
                 "position": p.position, "avg_cost": p.avg_cost}
                for p in positions
            ]
        STATE["orders_today"] = self.client._orders_today

        if STATE["paused"]:
            logger.info("策略已暂停（看板设置），仅刷新数据不下单")
            return

        # 运行所有启用的策略
        for strat in self.strategies:
            try:
                await strat.on_bar(self.ctx)
            except Exception as e:
                logger.error("策略 %s 执行异常: %s", strat.name, e, exc_info=True)
                await emit(Event.ERROR, {
                    "message": f"策略 <b>{strat.name}</b> 执行异常：<code>{e}</code>"
                })


async def run_daily_report(engine: Engine) -> None:
    snap = await engine.client.get_account_snapshot()
    positions = await engine.client.get_positions() or []
    now = datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")

    if snap:
        pnl_emoji = "📈" if snap.unrealized_pnl >= 0 else "📉"
        pos_lines = "\n".join(
            f"  {p.symbol} {p.sec_type} x{p.position:g} @ ${p.avg_cost:.2f}"
            for p in positions
        ) or "  无持仓"
        text = (
            f"<code>{now}</code>\n"
            f"{'─' * 28}\n"
            f"💰 账户净值：<b>${snap.net_liquidation:,.0f}</b>\n"
            f"💵 可用资金：<b>${snap.available_funds:,.0f}</b>\n"
            f"{pnl_emoji} 未实现盈亏：<b>${snap.unrealized_pnl:+,.0f}</b>\n"
            f"📑 当日下单：<b>{engine.client._orders_today}</b> 笔\n"
            f"{'─' * 28}\n"
            f"<b>当前持仓</b>\n{pos_lines}\n"
            f"{'─' * 28}\n"
            f"模式：{'实盘' if config.is_live() else '模拟盘'}  "
            f"DRY_RUN：{config.GUARDS.dry_run}"
        )
    else:
        text = f"<code>{now}</code>\n账户数据拉取失败，请检查 IB Gateway。"

    await emit(Event.DAILY_REPORT, {"text": text})


async def run_heartbeat(engine: Engine) -> None:
    last_ok = engine.client.last_successful_check
    if last_ok is None:
        return
    elapsed = (datetime.now() - last_ok).total_seconds() / 60
    if elapsed > HEARTBEAT_TIMEOUT_MINUTES:
        await emit(Event.ERROR, {
            "message": (
                f"💀 心跳超时：距上次成功拉取数据已 <b>{elapsed:.0f} 分钟</b>。"
                f"请检查 IB Gateway 与网络。"
            )
        })


def create_scheduler(engine: Engine) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=BEIJING)

    scheduler.add_job(
        func=engine.poll_once,
        trigger=IntervalTrigger(seconds=config.STRATEGY.poll_interval_seconds),
        id="strategy_poll", name="策略轮询",
        max_instances=1, misfire_grace_time=30,
    )
    scheduler.add_job(
        func=run_heartbeat, args=[engine],
        trigger=IntervalTrigger(minutes=5),
        id="heartbeat", name="心跳看门狗",
        max_instances=1, misfire_grace_time=60,
    )
    scheduler.add_job(
        func=run_daily_report, args=[engine],
        trigger=CronTrigger(
            hour=config.STRATEGY.daily_report_hour,
            minute=config.STRATEGY.daily_report_minute,
            timezone=BEIJING,
        ),
        id="daily_report", name="每日报告",
        max_instances=1, misfire_grace_time=300,
    )
    return scheduler
