# IB 风控监控程序

基于 IB Gateway + ib_async 的 Portfolio Margin 账户只读风控监控，通过 Telegram 推送告警。

## 监控功能

| 功能 | 触发条件 | 告警级别 |
|------|---------|---------|
| 剩余流动性预警 | ExcessLiquidity / NLV < 50% | ⚠️ 黄色 |
| 剩余流动性红线 | ExcessLiquidity / NLV < 40% | 🚨 红色 |
| 单股集中度预警 | 单股市值 / NLV > 27% | ⚠️ 黄色 |
| 单股集中度红线 | 单股市值 / NLV > 30% | 🚨 红色 |
| Gamma 死亡警戒 | 空头期权 DTE ≤ 14 且 ATM 附近 | 🚨 红色 |
| 每日健康报告 | 每天 08:30（北京时间） | ✅ 日报 |

## 安全说明（只读保障）

本程序采用**双层只读防护**，确保不会对你的账户执行任何交易操作：

1. **Gateway 层**：在 `docker-compose.yml` 中已设置 `READ_ONLY_API=yes`，IB Gateway 会在连接级别拒绝所有下单/撤单请求。
2. **代码层**：`ib_client.py` 中仅调用 `reqPositions`、`reqAccountSummary`、`reqTickers` 等只读方法，完全不引入 `Order` 相关类。

## 快速开始

### 1. 准备配置文件

```bash
cp .env.example .env
```

编辑 `.env`，填入：
- `TELEGRAM_BOT_TOKEN`：Telegram Bot Token
- `ALERT_CHAT_ID`：接收告警的 Chat ID
- `IB_USERNAME` / `IB_PASSWORD`：IB 账户密码（用于 Gateway 登录）
- `IB_ACCOUNT`：IB 账户号（如 U12345678）

### 2. 配置 IB 账户 TOTP（2FA 自动化）

为了让 IB Gateway 在服务器上实现无人值守自动登录，需要将账户的 2FA 改为 **TOTP（手机验证器）** 模式，并获取 TOTP 密钥（Base32 格式）。

> **安全提示**：TOTP 密钥需妥善保管，仅存储在服务器的 `.env` 文件中，不要提交到 Git。

### 3. 启动服务

```bash
docker compose up -d
```

查看日志：
```bash
docker compose logs -f ib-monitor
```

### 4. 验证连接

程序启动后会向 Telegram 发送 `🟢 IB Gateway 已连接` 消息，并立即执行一次完整风控检查。

## 本地调试（无 Docker）

```bash
pip install -r requirements.txt

# 本地需先手动启动 IB Gateway 并登录
# 然后运行：
python main.py
```

## 目录结构

```
ib_monitor/
├── config.py               # 配置读取
├── ib_client.py            # IB 只读连接层
├── notifier.py             # Telegram 推送
├── monitors/
│   ├── excess_liquidity.py # 剩余流动性监控
│   ├── concentration.py    # 单股集中度监控
│   └── gamma_watchdog.py   # Gamma 死亡警戒线
├── scheduler.py            # 定时任务
├── main.py                 # 程序入口
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## 风控阈值调整

所有阈值均通过 `.env` 文件配置，无需修改代码：

```bash
EXCESS_LIQUIDITY_WARN=0.50   # 剩余流动性预警（占NLV）
EXCESS_LIQUIDITY_RED=0.40    # 剩余流动性红线
CONCENTRATION_WARN=0.27      # 单股集中度预警
CONCENTRATION_RED=0.30       # 单股集中度红线
GAMMA_DTE_THRESHOLD=14       # Gamma警戒DTE天数
CHECK_INTERVAL_SECONDS=60    # 实时检查间隔（秒）
DAILY_REPORT_HOUR=8          # 每日报告时间（北京时间）
```
