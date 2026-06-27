"""
事件钩子 / 回调总线（Hook System）

设计目的：满足「通过类似 hook 或回调，通知到 Telegram 或邮箱」的需求。

工作方式（发布-订阅）：
  - 交易过程中的关键节点（连接、信号、下单、成交、被拒、错误、日报）
    通过 emit(Event.XXX, payload) 发布事件。
  - 任意数量的处理器（handler）用 @on(Event.XXX) 或 register() 订阅。
  - notifier.py 在导入时把 Telegram / 邮箱处理器注册进来，
    这样业务代码完全不关心「往哪推」，新增触达通道只需再注册一个 handler。

最近事件还会缓存在内存里，供 Web 看板「切页」实时展示。
"""

import asyncio
import logging
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class Event(str, Enum):
    CONNECTED = "connected"            # 已连接 IB
    DISCONNECTED = "disconnected"      # 连接断开
    SIGNAL = "signal"                  # 策略产生交易信号
    ORDER_SUBMITTED = "order_submitted"  # 订单已提交
    ORDER_STATUS = "order_status"      # 订单状态变化
    ORDER_FILLED = "order_filled"      # 订单成交
    ORDER_REJECTED = "order_rejected"  # 订单被护栏/IB 拒绝
    DAILY_REPORT = "daily_report"      # 每日报告
    ERROR = "error"                    # 异常 / 心跳超时


# handler 签名：async def handler(event: Event, payload: dict) -> None
Handler = Callable[[Event, dict], Awaitable[None]]

_handlers: dict[Event, list[Handler]] = {}
_global_handlers: list[Handler] = []   # 订阅所有事件

# 供 Web 看板展示的最近事件环形缓冲
RECENT_EVENTS: deque = deque(maxlen=200)


def register(event: Event | None, handler: Handler) -> None:
    """注册一个处理器。event=None 表示订阅所有事件。"""
    if event is None:
        _global_handlers.append(handler)
    else:
        _handlers.setdefault(event, []).append(handler)


def on(event: Event | None = None):
    """装饰器写法：@on(Event.ORDER_FILLED)"""
    def deco(func: Handler) -> Handler:
        register(event, func)
        return func
    return deco


async def emit(event: Event, payload: dict | None = None) -> None:
    """
    发布事件。所有 handler 并发执行，单个 handler 异常不影响其它 handler，
    也不会冒泡打断交易主流程（通知失败绝不能拖垮交易）。
    """
    payload = payload or {}
    record = {
        "event": event.value,
        "payload": payload,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    RECENT_EVENTS.append(record)
    logger.debug("emit %s %s", event.value, payload)

    handlers = _handlers.get(event, []) + _global_handlers
    if not handlers:
        return

    results = await asyncio.gather(
        *(h(event, payload) for h in handlers),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            logger.error("事件处理器异常 (%s): %s", event.value, r)


def recent_events(limit: int = 50) -> list[dict]:
    """返回最近 N 条事件（最新在前），供 Web 看板使用。"""
    items = list(RECENT_EVENTS)[-limit:]
    items.reverse()
    return items
