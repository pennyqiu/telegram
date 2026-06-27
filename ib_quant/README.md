# ib_quant · IB 量化交易模块

> 基于 **IB Gateway + ib_async** 的可下单量化交易系统，支持正股 / 期权，
> 内置多重安全护栏、策略框架、独立 Web 切页看板，并通过 **Hook 回调** 实时
> 触达 **Telegram / 邮箱**。

⚠️ **本模块会真实下单。** 与同仓库 `ib_monitor/`（只读风控）不同，本模块在
Gateway 层 `READ_ONLY_API=no`、代码层 `readonly=False`。请务必先在
**模拟盘 + DRY_RUN** 跑通后再考虑实盘。本项目仅供技术研究，不构成投资建议。

---

## 📁 目录结构

```
ib_quant/
├── README.md                # 本文件
├── guides/
│   ├── 01-account-setup.md   # 子账户申请、交易权限、市场数据、费用清单
│   ├── 02-api-deployment.md  # IB API 申请与部署（Gateway/TWS、登录流程、Docker）
│   └── 03-strategy-guide.md  # 策略框架说明与开发指南
├── config.py                # 配置（全部走 .env）
├── ib_client.py             # IB 交易客户端：登录/拉列表/查价/下单/周期检查 + 安全护栏
├── hooks.py                 # 事件钩子总线（发布-订阅，触达来源）
├── notifier.py              # 多通道通知：Telegram + 邮箱（注册为 hook 处理器）
├── strategies/
│   ├── base.py              # 策略基类 + 注册表
│   └── ma_cross.py          # 示例策略：双均线交叉
├── scheduler.py             # 周期性检查 + 策略轮询 + 每日报告 + 心跳
├── web/server.py            # FastAPI 看板服务
├── dashboard/index.html     # 量化策略「独立切页」看板
├── main.py                  # 程序入口
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 🧭 五大需求落点

| 需求 | 实现位置 |
|------|----------|
| 1. 量化策略在独立切页 | `dashboard/index.html`（含「量化策略」Tab）+ `web/server.py` |
| 2. 子账户申请 / 权限 / 费用 | `guides/01-account-setup.md` |
| 3. 登录 / 操作 / API 示例（登录、拉列表、查价、下单、周期检查） | `ib_client.py` + `guides/02-api-deployment.md` |
| 4. IB API 申请与部署 | `guides/02-api-deployment.md` + `docker-compose.yml` |
| 5. Hook / 回调触达 Telegram / 邮箱 | `hooks.py` + `notifier.py` |

---

## 🚀 快速开始（模拟盘）

```bash
cd ib_quant
cp .env.example .env
# 编辑 .env：填 IB_ACCOUNT(DUxxxx)、IB_USERNAME/PASSWORD、TELEGRAM_*
# 保持 TRADING_MODE=paper、DRY_RUN=true（先空跑验证链路）

docker compose up -d           # 启动 IB Gateway + 交易程序
docker compose logs -f ib-quant
```

打开看板（量化策略切页）：<http://服务器IP:8800>

验证链路 OK 后，分阶段放开：

1. `DRY_RUN=true` → 跑通策略信号与通知，**不真实下单**。
2. `DRY_RUN=false` + `TRADING_MODE=paper` → 模拟盘真实下单测试。
3. `TRADING_MODE=live` + `ALLOW_LIVE=true` → 实盘（务必先收紧护栏阈值）。

---

## 🛡️ 安全护栏（真实资金的最后防线）

所有订单（含策略自动下单与看板手动下单）都会经过 `ib_client._check_guards`：

| 护栏 | 环境变量 | 作用 |
|------|----------|------|
| 空跑模式 | `DRY_RUN` | 只记录不发送，链路验证神器 |
| 实盘闸门 | `ALLOW_LIVE` | `TRADING_MODE=live` 时必须显式 `true` |
| 标的白名单 | `SYMBOL_WHITELIST` | 只允许交易指定标的 |
| 单笔金额 | `MAX_ORDER_NOTIONAL` | 单笔名义金额上限 |
| 单标的持仓 | `MAX_POSITION_NOTIONAL` | 单标的累计市值上限 |
| 单日笔数 | `MAX_DAILY_ORDERS` | 防策略 bug 疯狂下单 |

---

## 🔔 通知 / 触达

事件流经 `hooks.py` 总线，`notifier.py` 把 Telegram / 邮箱注册为处理器：

- **连接、信号、下单、成交、被拒、错误、每日报告** 均会推送。
- 邮箱默认只推重要事件（下单/成交/拒绝/错误/日报），避免淹没。
- 扩展新通道（企业微信、Server酱…）：写一个 `async handler` 并 `register(None, handler)`。

详见各 `guides/` 文档。
