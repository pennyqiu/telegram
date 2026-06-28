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

## 六、实战：子账户资金规模与 QCOM Wheel 护栏配置

> 以"单账户隔离 + 在子账户里只跑高通（QCOM）期权 Wheel（飞轮）策略"为例。
> 下面是**资金规模测算框架 + 护栏配置**，不构成投资建议，金额自行决定、风险自负。

### 1. 账户隔离前提

- 主账户的大资金**不动**，只把一小笔划到**专用子账户**（如 `U20780881`）。
- 服务器用**受限第二用户名**（如 `pennyqiuapi`：能交易、**不能出金/转账**）登录，
  且该用户**只能访问这个子账户**——隔离才成立。`.env` 里 `IB_ACCOUNT` 填子账户号。

### 2. Wheel（飞轮）策略机械需求

1. 卖**现金担保看跌（Cash-Secured Put）**收权利金；
2. 被行权 → 以行权价买入 **100 股/张** QCOM；
3. 持股后卖**备兑看涨（Covered Call）**继续收权利金；
4. 被叫走 → 回到第 1 步循环。

核心约束是现金担保看跌：**1 张合约 = 100 股**，必须备足「行权价 × 100」现金。

### 3. 资金规模（QCOM 现价 ~$196 估算）

| 规模 | 占用资金（行权价 ~$190） | 说明 |
|------|--------------------------|------|
| **1 张合约** | ≈ **$19,000–20,000** | 跑通一轮 Wheel 的**最小有效资金** |
| 2 张合约 | ≈ $38,000–40,000 | 可分散不同行权价/到期 |

- 低于 ~$20k 连一张现金担保 put 都做不了（裸卖风险大、违背隔离初衷，不建议）。
- **建议起步**：先模拟盘 0 真金跑通自动化 → 真金第一步放 **~$20,000（1 张合约）**。
- **集中度上限**：单一标的（QCOM）建议**不超过总资产 ~10%**。

### 4. 对应 `.env` 护栏配置

```bash
IB_ACCOUNT=U20780881             # 子账户号（受限用户能访问的那个）
ENABLED_STRATEGIES=qcom_wheel    # 只启用该策略
UNIVERSE=QCOM                    # 标的池只有高通
SYMBOL_WHITELIST=QCOM            # 白名单只放高通，杜绝误交易其它标的
MAX_POSITION_NOTIONAL=20000      # 单标的持仓市值上限 ≈ 1 张合约
MAX_ORDER_NOTIONAL=20000         # 单笔订单名义金额上限
MAX_DAILY_ORDERS=10              # 单日下单笔数上限，防失控
DRY_RUN=true                     # 先空跑，确认无误再 false
REQUIRE_CONFIRM=true             # 实盘下单需 Telegram 人工二次确认
```

> 期权下单需账户具备**期权权限（建议 Level 1 备兑/现金担保起步）**及 **OPRA 行情订阅**，
> 详见 `01-account-setup.md`。Wheel 涉及期权合约下单，参考 `02-api-deployment.md` 第四节期权示例。

---

## 七、上线前 checklist

- [ ] 模拟盘 + `DRY_RUN=true` 观察信号是否符合预期。
- [ ] 收紧 `SYMBOL_WHITELIST` / `MAX_ORDER_NOTIONAL` / `MAX_DAILY_ORDERS`。
- [ ] `DRY_RUN=false` 在模拟盘真实下单，核对成交回调与通知。
- [ ] 实盘前确认 `TRADING_MODE=live` + `ALLOW_LIVE=true`，并把阈值调到可承受范围。
- [ ] 确认 Telegram / 邮箱能收到下单与异常通知。
- [ ] 子账户资金已按规模划入，且受限用户仅能访问该子账户（隔离生效）。
