"""
ib_quant 量化交易程序入口

启动流程：
  1. 注册通知通道（Telegram / 邮箱）到事件总线。
  2. 连接 IB Gateway（交易模式，含实盘安全闸门）。
  3. 立即跑一次策略轮询。
  4. 启动调度器（策略轮询 / 每日报告 / 心跳）。
  5. 可选启动 Web 看板（独立切页）。
  6. 持续运行直到收到停止信号。
"""

import asyncio
import logging
import signal
import sys

import config
import notifier
from hooks import emit, Event
from ib_client import IBTradingClient
from scheduler import Engine, create_scheduler, STATE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    notifier.setup()  # 接入通知通道

    client = IBTradingClient()
    engine = Engine(client)
    scheduler = None
    web_task = None

    async def shutdown(sig_name: str) -> None:
        logger.info("收到信号 %s，正在优雅退出...", sig_name)
        STATE["running"] = False
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)
        await client.disconnect()
        await emit(Event.DISCONNECTED, {"reason": f"收到 {sig_name} 信号，已安全退出"})

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig, lambda s=sig.name: asyncio.create_task(shutdown(s))
            )
        except NotImplementedError:
            pass  # Windows 不支持

    try:
        logger.info("正在连接 IB Gateway（交易模式）...")
        await client.connect()
        STATE["running"] = True

        # 启动可选 Web 看板
        if config.WEB.enabled:
            from web.server import start_web
            web_task = asyncio.create_task(start_web(engine))
            logger.info("Web 看板已启动：http://%s:%s", config.WEB.host, config.WEB.port)

        # 启动即跑一次
        await engine.poll_once()

        scheduler = create_scheduler(engine)
        scheduler.start()
        logger.info("调度器已启动：策略轮询每 %s 秒",
                    config.STRATEGY.poll_interval_seconds)

        while True:
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，退出...")
    except Exception as e:
        logger.critical("主程序异常退出: %s", e, exc_info=True)
        await emit(Event.ERROR, {"message": f"主程序崩溃：<code>{e}</code>"})
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)
        if web_task:
            web_task.cancel()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
