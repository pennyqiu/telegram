# 02 · IB API 申请与部署（登录流程 + 操作示例）

> 覆盖需求 3、4：获取登录权限 / 操作权限、操作 API 示例（登录、拉股票列表、
> 查价、下单买卖、周期检查），以及 API 接口的申请与部署。

---

## 一、IB 的三种 API（选型）

| API | 形态 | 说明 | 本项目 |
|-----|------|------|--------|
| **TWS API** | Socket（需 TWS 桌面端在线） | 功能全，但要图形界面 | — |
| **IB Gateway** | Socket（轻量，无图形界面） | **服务器无人值守首选** | ✅ 采用 |
| **Client Portal Web API** | REST + WebSocket | 纯 HTTP，但需常驻网关、会话需定期保活 | 备选 |

本模块基于 **IB Gateway + `ib_async`**（Socket）。Gateway 负责账号登录与 2FA，
Python 客户端只连本地 socket，不接触你的密码。

---

## 二、登录权限：API 不需单独申请，但要「启用」

API 本身免费、无需额外申请资格。要让程序能连上，需做两件事：

### 1. 在 Gateway / TWS 启用 API
**Configure → Settings → API → Settings**：
- ✅ Enable ActiveX and Socket Clients
- ✅ 取消勾选 **Read-Only API**（本模块要下单；只读监控才勾选）
- Socket port：实盘 `4001` / 模拟盘 `4002`（Docker 容器内部为 `4003/4004`）
- Trusted IPs：加入运行程序的机器 IP（容器内用服务名）
- Master API client ID：留空或与 `IB_CLIENT_ID` 区分

### 2. 2FA（两步验证）自动化——服务器无人值守的关键
人工每次登录要手机确认 2FA，服务器跑不通。两种方案：
- **IBKR Mobile + IB Key**：手机推送确认（适合手动/半自动）。
- **TOTP（推荐自动化）**：在 Client Portal 把 2FA 改为「时间动态码 TOTP」，
  拿到 Base32 密钥，填入 `.env` 的 `IB_TOTP_SECRET`，由 Gateway 容器自动生成验证码。

> ⚠️ TOTP 密钥等同第二把钥匙，仅存服务器 `.env`，**切勿提交 Git**。
> IB 每周日凌晨会要求重新认证一次，TOTP 方案可自动完成。

---

## 三、部署：Docker Compose（推荐）

```bash
cd ib_quant
cp .env.example .env        # 填 IB_USERNAME/PASSWORD/ACCOUNT、TOTP、Telegram 等
docker compose up -d
docker compose logs -f ib-quant
```

`docker-compose.yml` 中：
- `ib-gateway` 用 `ghcr.io/gnzsnz/ib-gateway`，`READ_ONLY_API=no`，`TRADING_MODE` 由 .env 控制。
- `ib-quant` 连接 `IB_HOST=ibq-gateway`，模拟盘内部端口 `4004`、实盘 `4003`。
- 看板暴露在 `8800`。

**本地调试（无 Docker）**：先手动启动 IB Gateway 并登录，确认监听 4001/4002，
然后 `pip install -r requirements.txt && python main.py`。

---

## 四、操作 API 示例（对应代码：`ib_client.py`）

下列示例用 `ib_async`，与本模块实现一致。

### 1. 登录 / 连接（拿到操作权限）
```python
from ib_async import IB
ib = IB()
await ib.connectAsync(host="127.0.0.1", port=4002, clientId=20, readonly=False)
# 账号密码 + 2FA 已由 Gateway 完成；这里只是连本地 socket
```
> 本模块封装在 `IBTradingClient.connect()`，并带 **实盘安全闸门** `assert_live_allowed()`。

### 2. 拉取股票列表
```python
from ib_async import Stock
# 方式 A：把代码池解析为合法合约
contracts = await ib.qualifyContractsAsync(
    Stock("AAPL","SMART","USD"), Stock("MSFT","SMART","USD"))

# 方式 B：市场扫描器动态拉列表（涨幅榜等，需市场数据权限）
from ib_async import ScannerSubscription
sub = ScannerSubscription(instrument="STK", locationCode="STK.US.MAJOR",
                          scanCode="TOP_PERC_GAIN", numberOfRows=20)
rows = await ib.reqScannerDataAsync(sub, [])
symbols = [r.contractDetails.contract.symbol for r in rows]
```
> 对应 `resolve_universe()` 与 `scan_market()`。

### 3. 查询价格
```python
tickers = await ib.reqTickersAsync(Stock("AAPL","SMART","USD"))
t = tickers[0]
print(t.last, t.bid, t.ask, t.close)
```
> 对应 `get_quote()` / `get_quotes()`，已处理 nan→0。

### 4. 下单买卖（本模块会先过安全护栏）
```python
from ib_async import MarketOrder, LimitOrder
contract = Stock("AAPL","SMART","USD")
await ib.qualifyContractsAsync(contract)

# 市价买 10 股
trade = ib.placeOrder(contract, MarketOrder("BUY", 10))

# 限价卖 10 股 @ 200
trade = ib.placeOrder(contract, LimitOrder("SELL", 10, 200.0))

# 跟踪成交
ib.orderStatusEvent += lambda tr: print(tr.orderStatus.status)
```
> 对应 `place_market_order()` / `place_limit_order()`，内部经过
> 白名单 / 金额 / 持仓 / 单日笔数 护栏，且 `DRY_RUN` 时不真实发送。

### 5. 期权下单（正股之外）
```python
from ib_async import Option
opt = Option("AAPL", "20260116", 200, "C", "SMART", multiplier="100", currency="USD")
await ib.qualifyContractsAsync(opt)
trade = ib.placeOrder(opt, LimitOrder("BUY", 1, 5.0))   # 买 1 张 Call
```

### 6. 周期性检查数据
```python
# 账户资金
vals = await ib.reqAccountSummaryAsync(group="All",
        tags="NetLiquidation,AvailableFunds,BuyingPower,UnrealizedPnL")
# 持仓
positions = await ib.reqPositionsAsync()
```
> 对应 `get_account_snapshot()` / `get_positions()`，由 `scheduler.py`
> 每 `POLL_INTERVAL_SECONDS` 秒调用，并把结果写入看板共享状态 `STATE`。

---

## 五、客户端 ID 冲突提醒

同一个 Gateway 上每个连接的 `clientId` 必须唯一。本模块默认 `IB_CLIENT_ID=20`，
与只读监控 `ib_monitor`（10）区分，二者可同时连同一个 Gateway 互不干扰。
