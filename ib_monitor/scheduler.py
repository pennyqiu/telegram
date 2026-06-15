"""
定时任务编排

三类任务：
  1. 实时风控检查（每 CHECK_INTERVAL_SECONDS 秒一次）
  2. 每日健康报告（DAILY_REPORT_HOUR:DAILY_REPORT_MINUTE，北京时间）
  3. 心跳看门狗（每5分钟检查一次监控程序是否正常工作）

防止静默失效：
  - 连续 3 次数据拉取失败 → 立即 Telegram 告警
  - 超过 HEARTBEAT_TIMEOUT 分钟没有成功拉取数据 → 告警（监控可能已死）
"""

import asyncio
import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ib_client import IBReadOnlyClient
from monitors import (
    check_excess_liquidity, check_concentration,
    check_gamma_watchdog, check_cc_roll, check_position_tracker,
)
from notifier import send_daily_report, send_connection_status, send_alert, AlertLevel
import config

logger = logging.getLogger(__name__)

BEIJING = pytz.timezone("Asia/Shanghai")

# 超过此分钟数没有成功拉取数据，触发"监控失效"告警
HEARTBEAT_TIMEOUT_MINUTES = 10
# 连续失败多少次触发告警（避免单次网络抖动误报）
FAILURE_ALERT_THRESHOLD = 3

_failure_alerted = False   # 已发过连续失败告警，避免重复轰炸


async def run_risk_check(client: IBReadOnlyClient) -> None:
    """单次完整风控检查，任何数据拉取失败都会中断本次检查并计入失败次数"""
    global _failure_alerted

    if not client.is_connected():
        logger.warning("IB Gateway 未连接，跳过本次风控检查")
        return

    try:
        # ── 1. 拉取账户快照 ──────────────────────────────────────────
        snap = await client.get_account_snapshot()
        if snap is None:
            logger.error("账户快照获取失败，中断本次风控检查")
            await _maybe_send_failure_alert(client, "账户资金数据（NLV/ExcessLiquidity）拉取失败")
            return

        # ── 2. 拉取持仓（None = 失败，[] = 真的没持仓）─────────────
        positions = await client.get_positions()
        if positions is None:
            logger.error("持仓数据获取失败，中断本次风控检查")
            await _maybe_send_failure_alert(client, "持仓列表拉取失败，本次风控检查已跳过")
            return

        # ── 3. 补充市场行情和 Greeks（失败不中断，但会记录警告）────
        positions = await client.enrich_with_market_data(positions)

        # ── 4. 执行各风控模块 ────────────────────────────────────────
        await check_excess_liquidity(snap)
        await check_concentration(positions, snap)
        await check_gamma_watchdog(positions)
        await check_cc_roll(positions)
        await check_position_tracker(positions)

        # ── 5. 数据正常，重置失败状态 ────────────────────────────────
        if _failure_alerted:
            await send_alert(
                title="✅ IB 监控数据恢复正常",
                body="账户数据和持仓数据已恢复正常拉取，风控监控继续运行。",
                level=AlertLevel.INFO,
            )
            _failure_alerted = False

    except Exception as e:
        logger.error("风控检查异常: %s", e, exc_info=True)
        client._consecutive_failures += 1
        await _maybe_send_failure_alert(client, f"风控检查出现未预期异常：<code>{e}</code>")


async def run_heartbeat_watchdog(client: IBReadOnlyClient) -> None:
    """
    心跳看门狗：检查距上次成功拉取数据是否超过阈值。
    防止程序表面还在运行，但实际上数据已经长时间拉取不到的静默失效。
    """
    now = datetime.now()
    last_ok = client.last_successful_check

    if last_ok is None:
        # 刚启动还没有成功过，给一段缓冲时间
        return

    elapsed_minutes = (now - last_ok).total_seconds() / 60
    if elapsed_minutes > HEARTBEAT_TIMEOUT_MINUTES:
        logger.error(
            "心跳异常：距上次成功拉取数据已超过 %.1f 分钟", elapsed_minutes
        )
        await send_alert(
            title="💀 IB 监控心跳超时！",
            body=(
                f"距上次成功拉取账户数据已超过 <b>{elapsed_minutes:.0f} 分钟</b>。\n\n"
                f"可能原因：\n"
                f"• IB Gateway 连接断开且未恢复\n"
                f"• API 调用持续超时\n"
                f"• 监控程序本身陷入异常状态\n\n"
                f"<b>请立即检查服务器和 IB Gateway 状态！</b>\n"
                f"最后成功时间：{last_ok.strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            level=AlertLevel.RED,
        )


async def run_daily_report(client: IBReadOnlyClient) -> None:
    """发送每日账户健康报告"""
    if not client.is_connected():
        await send_alert(
            title="⚠️ 每日报告生成失败",
            body="IB Gateway 未连接，无法生成每日健康报告，请检查 Gateway 状态。",
            level=AlertLevel.WARN,
        )
        return

    try:
        snap = await client.get_account_snapshot()
        if snap is None:
            await send_alert(
                title="⚠️ 每日报告生成失败",
                body="账户数据拉取失败，无法生成每日健康报告。",
                level=AlertLevel.WARN,
            )
            return

        positions = await client.get_positions()
        if positions is None:
            await send_alert(
                title="⚠️ 每日报告不完整",
                body="持仓数据拉取失败，每日报告已跳过持仓分析部分。",
                level=AlertLevel.WARN,
            )
            positions = []

        positions = await client.enrich_with_market_data(positions)

        from monitors.concentration import check_concentration as _conc
        conc_results = await _conc(positions, snap)
        conc_lines = [r.summary_line() for r in conc_results if r.is_warn or r.is_red]
        if not conc_lines:
            conc_lines = [
                r.summary_line() for r in conc_results if r.ratio > 0.05
            ] or ["  所有仓位集中度正常 ✅"]

        from monitors.gamma_watchdog import check_gamma_watchdog as _gw
        gamma_results = await _gw(positions)
        gamma_lines = [r.summary_line() for r in gamma_results]

        from monitors.cc_roll_watchdog import check_cc_roll as _cc
        cc_results = await _cc(positions)
        cc_lines = [r.summary_line() for r in cc_results] or ["  所有CC Delta正常，无需展期 ✅"]

        from monitors.position_tracker import check_position_tracker as _pt
        pt_result = await _pt(positions)
        stock_lines = [s.summary_line() for s in pt_result.stock_statuses]
        spym_lines = [pt_result.spym.summary_line()] if pt_result.spym else []

        el_pct = snap.excess_liquidity / snap.net_liquidation if snap.net_liquidation > 0 else 0

        await send_daily_report(
            nlv=snap.net_liquidation,
            excess_liquidity=snap.excess_liquidity,
            excess_liquidity_pct=el_pct,
            unrealized_pnl=snap.unrealized_pnl,
            concentration_lines=conc_lines,
            gamma_lines=gamma_lines,
            cc_lines=cc_lines,
            stock_lines=stock_lines,
            spym_lines=spym_lines,
        )
        logger.info("每日健康报告已发送")

    except Exception as e:
        logger.error("发送每日报告异常: %s", e, exc_info=True)
        await send_alert(
            title="⚠️ 每日报告生成异常",
            body=f"生成每日报告时出现异常：<code>{e}</code>",
            level=AlertLevel.WARN,
        )


async def _maybe_send_failure_alert(client: IBReadOnlyClient, reason: str) -> None:
    """连续失败次数达到阈值时发送一次告警，避免每次失败都发消息"""
    global _failure_alerted
    if client._consecutive_failures >= FAILURE_ALERT_THRESHOLD and not _failure_alerted:
        await send_alert(
            title="🔴 IB 监控数据连续拉取失败",
            body=(
                f"已连续 <b>{client._consecutive_failures} 次</b> 无法获取 IB 数据。\n"
                f"原因：{reason}\n\n"
                f"风控监控当前处于失效状态，请立即检查：\n"
                f"• IB Gateway 是否正常运行\n"
                f"• 网络连接是否正常\n"
                f"• 是否需要重新登录（每周日需手动重新认证）"
            ),
            level=AlertLevel.RED,
        )
        _failure_alerted = True


def create_scheduler(client: IBReadOnlyClient) -> AsyncIOScheduler:
    """创建并配置定时调度器"""
    scheduler = AsyncIOScheduler(timezone=BEIJING)

    # 实时风控检查
    scheduler.add_job(
        func=run_risk_check,
        trigger=IntervalTrigger(seconds=config.SCHEDULE.check_interval_seconds),
        args=[client],
        id="risk_check",
        name="实时风控检查",
        max_instances=1,
        misfire_grace_time=30,
    )

    # 心跳看门狗（每5分钟检查一次）
    scheduler.add_job(
        func=run_heartbeat_watchdog,
        trigger=IntervalTrigger(minutes=5),
        args=[client],
        id="heartbeat_watchdog",
        name="心跳看门狗",
        max_instances=1,
        misfire_grace_time=60,
    )

    # 每日健康报告
    scheduler.add_job(
        func=run_daily_report,
        trigger=CronTrigger(
            hour=config.SCHEDULE.daily_report_hour,
            minute=config.SCHEDULE.daily_report_minute,
            timezone=BEIJING,
        ),
        args=[client],
        id="daily_report",
        name="每日健康报告",
        max_instances=1,
        misfire_grace_time=300,
    )

    return scheduler
