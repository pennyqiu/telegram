# 03 · 策略框架与开发指南

> 覆盖需求 1：量化策略以「插件」形式注册，运行状态展示在独立 Web 切页。

---

## 一、运行模型

```
scheduler (每 POLL_INTERVAL_SECONDS 秒)
   └─ Engine.poll_once()
        ├─ 拉账户/持仓 → 写入 STATE（看板读取）
        └─ 对每个启用策略调用 strategy.on_bar(ctx)
                 └─ 策略内：查价 → 算信号 → ctx.buy()/ctx.sell()
                          └─ IBTradingClient 安全护栏 → (DRY_RUN?) → 下单
                                   └─ emit(Event.*) → hooks → Telegram/邮箱 + 看板事件流
```

每个订单事件、成交回调都通过 `hooks` 总线广播，看板与通知通道同时收到。

---

## 二、写一个新策略

1. 在 `strategies/` 新建 `my_strategy.py`：

```python
from .base import Strategy, StrategyContext, register_strategy

@register_strategy("my_strategy")          # 注册名 = ENABLED_STRATEGIES 里写的名字
class MyStrategy(Strategy):
    async def on_bar(self, ctx: StrategyContext) -> None:
        quotes = await ctx.quotes(ctx.universe)
        for sym in ctx.universe:
            q = quotes.get(sym)
            if not q or q.mid <= 0:
                continue
            # 你的信号逻辑……
            if 满足买入条件:
                await ctx.signal("my_strategy", sym, "BUY", "理由")
                await ctx.buy(sym, qty=1)              # 自动过护栏 / DRY_RUN
```

2. 在 `strategies/__init__.py` 导入它（触发注册）：
```python
from . import my_strategy  # noqa: F401
```

3. 在 `.env` 启用：
```
ENABLED_STRATEGIES=ma_cross,my_strategy
UNIVERSE=AAPL,MSFT,NVDA
```

---

## 三、`StrategyContext` 可用方法

| 方法 | 说明 |
|------|------|
| `await ctx.quote(sym)` / `ctx.quotes([...])` | 查实时价 |
| `await ctx.positions()` | 当前持仓列表 |
| `await ctx.buy(sym, qty, limit=None)` | 买入（限价传 limit） |
| `await ctx.sell(sym, qty, limit=None)` | 卖出 |
| `await ctx.signal(name, sym, "BUY", reason)` | 广播信号（触达 TG/邮箱 + 看板） |

> 下单方法均返回 `OrderResult`，被护栏拒绝时 `accepted=False`、`reason` 说明原因。

---

## 四、示例策略：双均线交叉（`ma_cross.py`）

- 维护每标的最近 `LONG=20` 个轮询周期的中间价。
- 短均线(5) 上穿长均线(20) → 金叉买入；下穿且有多头 → 死叉卖出。
- 仅用轮询价近似 K 线，用于**跑通链路**。

> 生产策略建议改用 `reqHistoricalData` 拉标准 K 线，并加入止损 / 仓位管理 / 滑点控制。

---

## 五、看板「量化策略」切页

`dashboard/index.html` 顶部 Tab 切换，「🧠 量化策略」页展示：
- 已启用策略列表、标的池；
- 最近策略信号流（来自 hooks 事件）；
- 顶部「暂停策略」按钮：一键停止自动下单（仅刷新数据），紧急时使用。

「🛒 手动下单」页可直接下单测试，**同样经过全部安全护栏与 DRY_RUN**。

---

## 六、上线前 checklist

- [ ] 模拟盘 + `DRY_RUN=true` 观察信号是否符合预期。
- [ ] 收紧 `SYMBOL_WHITELIST` / `MAX_ORDER_NOTIONAL` / `MAX_DAILY_ORDERS`。
- [ ] `DRY_RUN=false` 在模拟盘真实下单，核对成交回调与通知。
- [ ] 实盘前确认 `TRADING_MODE=live` + `ALLOW_LIVE=true`，并把阈值调到可承受范围。
- [ ] 确认 Telegram / 邮箱能收到下单与异常通知。
