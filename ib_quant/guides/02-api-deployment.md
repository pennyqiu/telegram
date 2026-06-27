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

### 1. 需要启用的 API 选项（两种程序通用）
不论用 Gateway 还是 TWS，最终都要让下面这几项生效。区别只在**怎么改**（界面点 / 环境变量）。

| 选项 | 设置 | 说明 |
|------|------|------|
| **Enable ActiveX and Socket Clients** | ✅ 开启 | 总开关，不开 Python 连不上 |
| **Read-Only API** | ❌ 关闭 | 本模块要下单；纯监控场景才保留只读更安全 |
| **Socket port** | 实盘 `4001` / 模拟盘 `4002` | Docker 镜像内部用 `4003/4004`，与本地区分避免冲突 |
| **Allow connections from localhost only** | ❌ 关闭（远程/容器） | 关闭后才接受非本机连接，配合 Trusted IPs 使用 |
| **Trusted IPs** | 加入客户端机器 IP | 容器内填服务名解析出的 IP；务必只放白名单 |
| **Master API client ID** | 留空 | 建议留空，由各连接用 `IB_CLIENT_ID` 区分 |
| **Bypass Order Precautions for API Orders** | ✅ 开启 | 免去 API 下单时的数量/金额二次确认弹窗（无人值守必需）；本模块已有自有护栏 |

---

### 2. 【你的方案】IB Gateway — 无图形界面 / Linux 后台模式
Gateway 没有交易界面、占资源小，是服务器 7×24 无人值守的首选。Linux 后台运行**推荐直接用 Docker 镜像**，
上面那些 API 选项全部由环境变量注入，**不用点任何界面**。

**做法（推荐，对应第三节 Docker Compose）**：
1. 选用镜像 `ghcr.io/gnzsnz/ib-gateway`（已内置 Gateway + 自动登录 + 可选 VNC）。
2. 在 `.env` 里填好下列变量，容器启动时自动写进 Gateway 配置：

```bash
IB_USERNAME=你的IB登录名     # compose 会映射成容器内 TWS_USERID
IB_PASSWORD=你的IB密码       # compose 会映射成容器内 TWS_PASSWORD
TRADING_MODE=paper          # 先用模拟盘；实盘改 live
# 下单许可在 compose 里已设 READ_ONLY_API=no，无需在 .env 配置
# 2FA（手机推送/动态码）属于登录环节，详见本节第 4 小节
```

3. `docker compose up -d` 启动，容器内 Gateway 自动登录并在 `4003`(实盘)/`4004`(模拟) 监听。
4. Python 端通过 compose 网络用服务名 + 内部端口连接（无需 Trusted IPs 手填 IP）。
5. 验证：`docker compose logs -f ibq-gateway` 看到登录成功，再用本模块 `connect()` 握手。

> Linux 服务器上**不要装桌面版手动点界面**——既费资源又无法无人值守。
> 镜像内已带 Xvfb/IBC，会替你完成"启动 Gateway → 自动登录 → 保活"的全过程。

**（备选）裸装 Gateway + IBC 脚本**：若不想用 Docker，可在 Linux 上自行安装
IB Gateway 安装包 + [IBC](https://github.com/IbcAlpha/IBC) 实现自动登录，
并在 IBC 配置文件里写死上表 API 选项。维护成本更高，一般不推荐。

---

### 3. 【备选】TWS — 有图形界面（本地调试 / Windows、Mac 桌面）
TWS 是完整的图形交易终端，适合**人工盯盘或本地开发调试**，不适合服务器无人值守。
启用 API 靠鼠标点菜单：

1. 启动并登录 TWS（实盘或 Paper 模拟盘）。
2. 顶部菜单 **File / Edit → Global Configuration → API → Settings**。
3. 按上文表格逐项勾选 / 填写（端口实盘 `7496` / 模拟 `7497`，注意与 Gateway 不同）。
4. 在 **Trusted IPs** 加入客户端机器 IP（本机调试填 `127.0.0.1`）。
5. 点 **Apply / OK** 保存，TWS 开始在该端口监听。
6. `.env` 里 `IB_PORT` 改成 TWS 端口后，用本模块 `connect()` 验证。

> 选项含义与 Gateway 完全一致，只是 TWS 端口是 `7496/7497`、入口在 **Global Configuration**。
> 本项目生产用 Gateway，TWS 仅作本地手动验证用途。

### 4. 2FA（两步验证）自动化——服务器无人值守的关键

**先理解 IB 的登录规则**，否则下面的方案会看不懂：
- 登录 = 用户名 + 密码（第一因子）+ 一个**第二因子**（手机/动态码）。
- IBC 能替你自动填用户名密码，但**第二因子 IB 不允许程序自动完成**（见下）。
- IB 规定：每周日 01:00（美东时间）会作废令牌，**那之后第一次启动必须人工过一次 2FA**；
  这一周内靠「每日自动重启复用会话」就不用再验证。所以现实目标是：**一周只人工点一次**。

---

#### 方案 A：IBKR Mobile 推送（IB Key）—— 推荐，官方认可，本项目默认
原理：登录时 IB 给你手机 App 推一条确认，你点一下「同意」即可，**不需要输入任何码**。

配置（已对应你的 `docker-compose.yml`）：
1. 手机装 **IBKR Mobile** App，登录账号，启用 **IB Key**（设置 → Secure Login / 2FA）。
2. `.env` 填好登录信息（compose 会映射成镜像变量）：

```bash
IB_USERNAME=你的IB登录名      # → 容器内 TWS_USERID
IB_PASSWORD=你的IB密码        # → 容器内 TWS_PASSWORD
TRADING_MODE=paper           # 先模拟盘，实盘再改 live
```

3. `docker compose up -d` 启动后，Gateway 自动填账密并触发手机推送。
   compose 里 `TWOFACTOR_TIMEOUT=180` 表示：等你点确认最多等 180 秒，超时自动重试推送。
4. **你在手机上点一次「同意」** → 登录完成，开始监听端口。
5. 之后这一周，容器靠每日自动重启复用会话，不再打扰你；**下周日再点一次**即可。

> 这是 IB、IBC、`gnzsnz/ib-gateway` 都正式支持的方式，最稳，缺点是每周需要你手动点 1 次。
> 如果服务器在国内、手机推送偶尔收不到，可在 App 里手动「重新发送」，或拉长 `TWOFACTOR_TIMEOUT`。

---

#### 方案 B：TOTP 动态码（`IB_TOTP_SECRET` 的真正含义）—— 备选，有争议，谨慎
**什么是 TOTP**：Time-based One-Time Password，基于一个**共享密钥 + 当前时间**算出的 6 位数字，
每 30 秒变一次（就是 Google Authenticator 里那种码）。

**密钥从哪来**：在 IB 把第二因子设成 **Mobile Authenticator / 第三方验证器** 时，
IB 会给你一段 **Base32 密钥**（一串字母数字），同时给个二维码。
路径大致：**Client Portal → Settings → User Settings → Secure Login System →
选用 Authenticator App → 显示密钥/二维码**（不同时期界面略有差异）。
这串密钥就是要填进 `.env` 的 `IB_TOTP_SECRET` 的东西：

```bash
IB_TOTP_SECRET=JBSWY3DPEHPK3PXP   # 示例，Base32；真实值从 IB 获取
```

有了密钥，任何程序都能自己算出当前 6 位码（Python `pyotp` 或命令行 `oathtool`）：

```python
import pyotp
print(pyotp.TOTP("JBSWY3DPEHPK3PXP").now())   # → 例如 492057，30秒一变
```

**⚠️ 现实限制（务必先看，否则会白忙）**：
1. **官方 IBC 不会自动把这个码输进登录框**——作者明确拒绝，理由是：程序既能填密码、
   又能算动态码，就等于无人值守也能登录，2FA 形同虚设。
2. 因此「自动 TOTP 登录」只能靠**非官方魔改镜像/脚本**实现，IBKR 可能视为违规，风险自负。
3. **本项目当前的 `docker-compose.yml` 并没有把 `IB_TOTP_SECRET` 传给 Gateway 容器**，
   所以现在即使填了也**不生效**——它只是个预留位。要用得自己改造镜像，不建议新手碰。

> 结论：**新手 / 求稳就用方案 A**（每周手动点一次推送）。TOTP 自动登录属于灰色地带，
> 收益是"全自动"，代价是安全性下降 + 维护非官方镜像，确有需要再单独评估。

---

> 🔐 **安全提醒**：无论哪种方式，`IB_PASSWORD`、`IB_TOTP_SECRET` 都等同账户钥匙，
> 只存服务器 `.env`（已在 `.gitignore`），**切勿提交 Git、切勿截图外发**。
> 服务器本身也要加固（防火墙、SSH 密钥登录、最小权限），详见 `04-vps-deployment.md`。

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
