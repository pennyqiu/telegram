# 04 · VPS 实战部署（看到真实数据）

> 目标：在一台云服务器上把 **IB Gateway + ib_quant 程序 + 看板** 跑起来，
> 24 小时无人值守，并安全地访问看板看到真实账户数据。
> 全程默认 **模拟盘 + DRY_RUN**，确认无误再放开实盘。

---

## 一、买什么样的 VPS

| 项 | 建议 |
|----|------|
| 地域 | **靠近 IB 行情服务器**：美东（US East）最佳，降低延迟与断连 |
| 配置 | 至少 **2 核 / 2GB 内存 / 20GB**（IB Gateway 是 Java，较吃内存；4GB 更稳） |
| 系统 | Ubuntu 22.04 LTS |
| 网络 | 固定公网 IP；端口默认全关，按需放行 |

> 常见选择：Vultr / DigitalOcean / Linode / AWS Lightsail 的美东节点。

---

## 二、首次登录与基础安全

```bash
ssh root@你的服务器IP

# 1) 创建非 root 用户
adduser trader
usermod -aG sudo trader

# 2) 启用防火墙：默认拒绝入站，只放行 SSH（看板不开公网，用隧道）
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw enable

# 3) 切换到 trader 用户
su - trader
```

> ⚠️ **不要**用 `ufw allow 8800` 把看板暴露公网（带敏感数据）。下文用 SSH 隧道访问。

---

## 三、安装 Docker

```bash
# 官方一键脚本
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 重新登录使 docker 组生效
exit
ssh trader@你的服务器IP

docker --version
docker compose version
```

---

## 四、拉取代码

```bash
git clone https://github.com/pennyqiu/telegram.git
cd telegram/ib_quant
```

---

## 五、配置 .env

```bash
cp .env.example .env
nano .env        # 或 vim
```

**最少要改这些**（先保持模拟盘 + 空跑）：

```bash
# Telegram（去 @BotFather 建 Bot 拿 token；给 Bot 发条消息后用 @userinfobot 拿 chat id）
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=你的token
TELEGRAM_CHAT_ID=你的chatid

# IB（模拟盘）
IB_ACCOUNT=DU1234567          # 模拟盘账户号
TRADING_MODE=paper
IB_USERNAME=你的IB用户名
IB_PASSWORD=你的IB密码
IB_TOTP_SECRET=               # 见下一节（自动登录需要）

# 安全：先空跑
DRY_RUN=true
ALLOW_LIVE=false
SYMBOL_WHITELIST=AAPL,MSFT,NVDA
```

> `.env` 已被根 `.gitignore` 忽略，不会进 Git。但仍要 `chmod 600 .env` 收紧权限。

---

## 六、IB 2FA 改 TOTP（无人值守自动登录的关键）

服务器上没人帮你点手机确认，必须把二次验证改成「时间动态码 TOTP」：

1. 登录 IB **Client Portal → Settings → User Settings → Secure Login System**。
2. 选择 **IB Key（手机）→ 启用 TOTP**，或在安全设备里添加「Authenticator App」。
3. 系统会给一串 **Base32 密钥**（也可扫码），把这串密钥填进 `.env` 的 `IB_TOTP_SECRET`。
4. Gateway 容器会用它自动生成 6 位动态码完成登录。

> ⚠️ TOTP 密钥 = 第二把钥匙，仅存服务器 `.env`，绝不外传/提交。
> IB 每周日凌晨要求重新认证一次，TOTP 方案可自动完成，无需人工。

---

## 七、启动

```bash
docker compose up -d          # 后台启动 ib-gateway + ib-quant
docker compose ps             # 看两个容器是否 healthy/running
docker compose logs -f ib-quant
```

启动正常时你会：
- 在 **Telegram 收到「🟢 已连接 IB」** 通知（说明全链路打通）；
- 日志里看到「已连接 IB Gateway... 模式=模拟盘 PAPER」「调度器已启动」。

---

## 八、安全访问看板（SSH 隧道，不暴露公网）

在**你自己的电脑**上执行：

```bash
ssh -L 8800:localhost:8800 trader@你的服务器IP
```

保持这个终端开着，然后本机浏览器打开：

```
http://localhost:8800
```

此时看板顶部应是 **PAPER + DRY_RUN** 徽章，「概览/持仓」开始显示**真实模拟盘数据**
（而不是 DEMO 演示数据）。

---

## 九、分阶段放开（务必按顺序）

| 阶段 | .env 设置 | 验证 |
|------|-----------|------|
| 1. 空跑 | `paper` + `DRY_RUN=true` | 看板/通知有数据，订单显示「DRY_RUN」不真实成交 |
| 2. 模拟实单 | `paper` + `DRY_RUN=false` | 模拟盘出现真实成交回报 |
| 3. 实盘 | `live` + `ALLOW_LIVE=true` + `DRY_RUN=false` | **先把护栏阈值调到可承受范围！** |

每次改 `.env` 后：`docker compose up -d`（会重建受影响容器）。

> 切实盘还需把 compose 的内部端口指向实盘：`IB_GATEWAY_INTERNAL_PORT=4003`（模拟盘默认 4004）。

---

## 十、日常运维

```bash
docker compose logs -f ib-quant     # 实时日志
docker compose restart ib-quant     # 重启交易程序
docker compose down                 # 停止全部
git pull && docker compose up -d --build   # 更新代码后重建
```

---

## 十一、排错速查

| 现象 | 可能原因 / 处理 |
|------|----------------|
| 看板还是 DEMO 演示数据 | 你访问的是静态托管页，不是 `:8800`；或隧道没建好 |
| 收不到「🟢 已连接 IB」 | Telegram token/chat_id 错；或 Gateway 没连上 |
| Gateway 反复重连 | TOTP 密钥错、账号密码错、或周日重认证窗口 |
| `competing live session` | 别处（手机/TWS）登录了同账户，先退掉 |
| clientId 冲突 | 与 `ib_monitor`(10) 撞号，本模块默认 20，别再占用 |
| 市价单被护栏拒绝 | 无市场数据导致拿不到价；去 Client Portal 订阅行情 |
| 下单超过上限被拒 | 调 `MAX_ORDER_NOTIONAL` / `MAX_POSITION_NOTIONAL` |

---

## 十二、安全红线

- `.env`（含 IB 密码/TOTP）绝不提交、绝不外传，`chmod 600`。
- 看板**不要**开公网，只用 SSH 隧道。
- 实盘前务必在模拟盘充分验证，并收紧全部护栏阈值。
- 本系统仅供技术研究，不构成投资建议；真实交易风险自负。
