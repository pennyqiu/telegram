"""
IB 风控监控程序入口

启动流程：
  1. 连接 IB Gateway（只读模式）
  2. 发送启动成功通知
  3. 立即执行一次风控检查
  4. 启动定时调度器（实时检查 + 每日报告）
  5. 持续运行，直到手动停止
"""

import asyncio
import logging
import signal
import sys

from ib_client import IBReadOnlyClient
from notifier import send_connection_status, send_alert, AlertLevel
from scheduler import create_scheduler, run_risk_check

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    client = IBReadOnlyClient()
    scheduler = None

    async def shutdown(sig_name: str) -> None:
        logger.info("收到信号 %s，正在优雅退出...", sig_name)
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)
        await client.disconnect()
        await send_alert(
            title="🛑 IB 监控程序已停止",
            body=f"收到 {sig_name} 信号，监控程序已安全退出。",
            level=AlertLevel.INFO,
        )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig.name: asyncio.create_task(shutdown(s)),
            )
        except NotImplementedError:
            # Windows 不支持 add_signal_handler，忽略
            pass

    try:
        logger.info("正在连接 IB Gateway...")
        await client.connect()

        await send_connection_status(
            connected=True,
            detail="IB 风控监控程序已启动（只读模式）",
        )

        # 启动后立即执行一次完整风控检查
        logger.info("执行启动时风控检查...")
        await run_risk_check(client)

        # 启动定时调度器
        scheduler = create_scheduler(client)
        scheduler.start()
        logger.info(
            "定时调度器已启动：实时检查每 %s 秒，每日报告时间已配置",
            scheduler.get_job("risk_check").trigger.interval.seconds
            if hasattr(scheduler.get_job("risk_check").trigger, "interval")
            else "N/A",
        )

        # 保持主循环运行
        while True:
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，正在退出...")
    except Exception as e:
        logger.critical("主程序异常退出: %s", e, exc_info=True)
        await send_alert(
            title="💥 IB 监控程序崩溃",
            body=f"<code>{e}</code>\n\n请检查服务器日志并重启程序。",
            level=AlertLevel.RED,
        )
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
