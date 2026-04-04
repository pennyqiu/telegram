# 部署与使用手册

> 适用于 `tg-subscription`（订阅系统）和 `tg-club`（俱乐部系统）线上生产部署。

---

## 目录

```
0.  前期准备（资源采购）
    0.1 VPS 服务商选择
    0.2 购买 VPS（以 Vultr 为例）
    0.3 购买域名（以 Cloudflare 为例）
    0.4 配置 DNS 解析
    0.5 费用汇总
1.  服务器初始化
2.  部署 tg-subscription 订阅系统
3.  部署 tg-club 俱乐部系统
    3.1 拉取代码
    3.2 配置环境变量（含 Bot Token / 管理员 ID）
    3.3 修改数据库密码
    3.4 启动服务
    3.5 注册俱乐部 Bot Webhook
4.  Nginx 反向代理配置
5.  前端部署
    5.1 部署订阅系统 Mini App（Vercel）
    5.2 部署俱乐部 Mini App（Vercel）
    5.3 部署管理后台 Admin Web
    5.4 回填 Mini App URL
6.  系统联通验证
7.  冒烟测试用例
8.  常见问题排查
9.  快速命令速查
10. 系统通信架构说明
    10.1 整体通信拓扑
    10.2 用户端（Mini App）→ 俱乐部后端
    10.3 俱乐部后端 → 订阅系统（权限查询）
    10.4 管理员（Admin Web / Telegram Bot）→ 俱乐部后端
    10.5 订阅系统 → Telegram Bot
    10.6 第三方支付 → 订阅系统 Webhook
    10.7 数据权限分级说明
```

---

## 0. 前期准备（资源采购）

在部署前需要准备两样东西：一台境外 VPS 和一个域名。

### 0.1 VPS 服务商选择

**境外服务商（推荐）**

| 服务商 | 最低配置 | 月费 | 优点 | 注册地址 |
|--------|----------|------|------|----------|
| **Hetzner** | 2核 2GB | ~$4 | 性价比最高，欧洲机房 | hetzner.com |
| **Vultr** | 1核 1GB | $6 | 日本/新加坡节点，亚洲延迟低 | vultr.com |
| **DigitalOcean** | 1核 1GB | $6 | 文档最好，新手友好 | digitalocean.com |
| **Linode (Akamai)** | 1核 1GB | $5 | 稳定老牌 | linode.com |

> 推荐优先选 **Vultr 新加坡节点** 或 **Hetzner**，亚洲用户延迟最低。

**国内服务商（不推荐用于 Bot）**

| 服务商 | 月费 | 注意事项 |
|--------|------|----------|
| 腾讯云轻量 | ¥45/月 | 需 ICP 备案，访问 Telegram API 需代理 |
| 阿里云 ECS | ¥50/月 | 同上 |

> 国内服务器访问 `api.telegram.org` 会被屏蔽，**不推荐**直接用于 Bot 部署。

---

### 0.2 购买 VPS（以 Vultr 为例）

**步骤一：注册账号**

1. 访问 [vultr.com](https://www.vultr.com)
2. 填写邮箱 + 密码注册
3. 绑定信用卡或 PayPal（支持 Visa / MasterCard / 支付宝）
4. 充值 $10 起（新用户有时有赠金活动）

**步骤二：创建服务器**

```
控制台 → Products → Compute → Deploy Server

配置选择：
  Server Type:    Cloud Compute - Shared CPU
  Location:       Tokyo / Singapore（延迟最低）
  Image:          Ubuntu 22.04 LTS
  Plan:           1 vCPU  2GB RAM  50GB SSD  → $12/月（推荐，跑两个服务更稳）
                  1 vCPU  1GB RAM  25GB SSD  → $6/月（最低可用）
  Additional:     勾选 IPv4
  Hostname:       tg-bot-server（随意填）
```

**步骤三：记录服务器信息**

创建完成后（约 60 秒），控制台显示：

```
IP Address:  123.456.789.0
Username:    root
Password:    xxxxxxxxxxxxxxxx
```

> 建议立刻把 IP 和密码保存到本地备用。

---

### 0.3 购买域名（以 Cloudflare 为例）

> Telegram Webhook 必须是合法 HTTPS 域名，Let's Encrypt 免费证书可满足要求。

**推荐域名注册商**

| 服务商 | 价格 | 推荐度 | 优点 |
|--------|------|--------|------|
| **Cloudflare Registrar** | ~$9/年（.com） | ★★★★★ | 首选，自带 CDN + DNS，不赚差价 |
| **Namecheap** | ~$10/年（.com） | ★★★★ | 便宜，界面友好 |
| **GoDaddy** | ~$12/年（.com） | ★★★ | 知名，但续费价格贵 |

**Cloudflare 注册步骤**

1. 访问 [cloudflare.com](https://www.cloudflare.com) → 注册账号
2. 左侧菜单 → **Domain Registration** → **Register Domains**
3. 搜索域名（如 `yourbotname.com`）→ 加入购物车 → 结账支付
4. 支付完成后进入该域名的 **DNS 管理**页面

---

### 0.4 配置 DNS 解析

在 Cloudflare DNS 控制台添加以下 A 记录（**Proxy 状态选「DNS Only」灰色云朵**）：

```
Type    Name      Content           Proxy 状态
A       api       123.456.789.0     DNS Only（灰色云朵）
A       club      123.456.789.0     DNS Only
A       admin     123.456.789.0     DNS Only
```

最终效果：

```
api.yourdomain.com    → 服务器IP（订阅系统后端）
club.yourdomain.com   → 服务器IP（俱乐部系统后端）
admin.yourdomain.com  → 服务器IP（管理后台）
```

> DNS 解析生效通常需要 5~30 分钟，可用 `ping api.yourdomain.com` 验证是否指向正确 IP。

---

### 0.5 费用汇总

| 项目 | 费用 | 说明 |
|------|------|------|
| VPS（Vultr 新加坡 1核2GB） | $12/月 | 运行两个 Docker 服务推荐 2GB |
| 域名（Cloudflare .com） | ~$9/年 ≈ $0.75/月 | 一个域名三个子域名全覆盖 |
| SSL 证书 | 免费 | Let's Encrypt，Certbot 自动续期 |
| Mini App 托管（Vercel） | 免费 | 静态资源免费额度完全够用 |
| **合计** | **约 $13/月（¥95）** | 起步阶段用 $6/月 的 1核1GB 也能跑 |

---

## 1. 服务器初始化

SSH 连接到服务器后依次执行：

```bash
# 连接服务器（用 Vultr 控制台显示的 IP 和密码）
ssh root@123.456.789.0

# 更新系统
apt update && apt upgrade -y

# 安装必要工具
apt install -y git curl vim ufw

# 配置防火墙
ufw allow 22    # SSH
ufw allow 80    # HTTP（SSL 证书申请用）
ufw allow 443   # HTTPS
ufw enable

# 安装 Docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# 安装 Nginx + Certbot
apt install -y nginx certbot python3-certbot-nginx

# 验证安装
docker --version && docker compose version
nginx -v
```

---

## 2. 部署 tg-subscription

### 2.1 拉取代码

```bash
mkdir -p /app && cd /app
git clone https://github.com/yourname/tg-subscription.git
cd tg-subscription
```

### 2.2 配置环境变量

```bash
cp .env.example .env
vim .env
```

填写以下内容（**所有 `change_this` 必须替换**）：

```env
# 从 @BotFather 获取
TELEGRAM_BOT_TOKEN=7xxxxxxxxx:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 随机生成：openssl rand -hex 16
TELEGRAM_WEBHOOK_SECRET=abc123def456abc123def456abc123de

# 你的域名
TELEGRAM_WEBHOOK_URL=https://api.yourdomain.com/webhooks/telegram

# Mini App 部署后的地址（第 5 节完成后填写）
MINI_APP_URL=https://sub-app.yourdomain.com

# 数据库（与 docker-compose 中保持一致）
DATABASE_URL=postgresql+asyncpg://subuser:subpass@db:5432/tg_sub
REDIS_URL=redis://redis:6379/0

# 宽限/提醒天数
GRACE_PERIOD_DAYS=3
EXPIRY_REMINDER_DAYS=3

# 你自己的 Telegram 数字 ID（可在 @userinfobot 获取）
ADMIN_TELEGRAM_IDS=123456789

# 随机生成：openssl rand -hex 20
INTERNAL_API_KEY=your_internal_api_key_here
```

### 2.3 修改 docker-compose 数据库密码

```bash
vim docker-compose.yml
```

将 `POSTGRES_USER/POSTGRES_PASSWORD` 与 `.env` 中的 `DATABASE_URL` 保持一致：

```yaml
db:
  environment:
    POSTGRES_DB: tg_sub
    POSTGRES_USER: subuser
    POSTGRES_PASSWORD: subpass   # ← 改成强密码
```

### 2.4 启动服务

```bash
cd /app/tg-subscription

# 首次构建并启动（后台运行）
docker compose up -d --build

# 查看启动状态（所有服务应为 Up）
docker compose ps

# 查看日志确认无报错
docker compose logs -f app
```

### 2.5 注册 Telegram Webhook

```bash
# 替换 BOT_TOKEN 和 WEBHOOK_SECRET 为 .env 中的值
BOT_TOKEN="7xxxxxxxxx:AAxxxx"
WEBHOOK_URL="https://api.yourdomain.com/webhooks/telegram"
SECRET="abc123def456abc123def456abc123de"

curl -s "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=${WEBHOOK_URL}" \
  -d "secret_token=${SECRET}" \
  -d "allowed_updates=[\"message\",\"callback_query\",\"pre_checkout_query\",\"chat_join_request\"]"

# 期望返回：{"ok":true,"result":true}

# 验证 Webhook 注册成功
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
```

### 2.6 初始化套餐数据

```bash
# 进入数据库容器插入默认套餐
docker compose exec db psql -U subuser -d tg_sub << 'EOF'
INSERT INTO plans VALUES (
  'plan_basic_monthly', 'Basic 基础版', '核心功能，每月自动续费',
  250, 'monthly', 7, '["channel_a"]', '["-1001234567890"]', 1, TRUE, NOW(), NOW()
) ON CONFLICT DO NOTHING;

INSERT INTO plans VALUES (
  'plan_pro_monthly', 'Pro 专业版', '全功能，每月自动续费',
  550, 'monthly', 7, '["channel_a","channel_b","ai_chat"]', '["-1001234567890","-1009876543210"]', 2, TRUE, NOW(), NOW()
) ON CONFLICT DO NOTHING;
EOF
```

---

## 3. 部署 tg-club

### 3.1 拉取代码

```bash
cd /app
git clone https://github.com/yourname/tg-club.git
cd tg-club/backend
```

### 3.2 配置环境变量

```bash
cp .env.example .env
vim .env
```

```env
# 俱乐部系统数据库（独立库，不与订阅系统共用）
CLUB_DB_URL=postgresql+asyncpg://clubuser:clubpass@db:5432/tg_club
REDIS_URL=redis://redis:6379/0

# 管理后台登录账号
ADMIN_JWT_SECRET=your_jwt_secret_here   # openssl rand -hex 32
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_strong_password

# 对接订阅系统（必须与 tg-subscription 的 INTERNAL_API_KEY 一致）
SUBSCRIPTION_SERVICE_URL=http://YOUR_SERVER_IP:8000
SUBSCRIPTION_INTERNAL_API_KEY=your_internal_api_key_here

# Cloudflare R2 图片存储（可选，先留空跳过）
R2_ENDPOINT=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET=club-assets
R2_PUBLIC_URL=
```

### 3.3 修改 docker-compose 数据库密码

```bash
vim docker-compose.yml
```

```yaml
db:
  environment:
    POSTGRES_DB: tg_club
    POSTGRES_USER: clubuser
    POSTGRES_PASSWORD: clubpass   # ← 改成强密码
```

> **注意**：tg-club 使用独立的数据库实例（端口 5433），与 tg-subscription 完全隔离。

### 3.4 启动服务

```bash
cd /app/tg-club/backend

docker compose up -d --build

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f backend
```

### 3.5 注册俱乐部 Bot Webhook

```bash
CLUB_BOT_TOKEN="7xxxxxxxxx:BBxxxx"
CLUB_WEBHOOK_URL="https://club.yourdomain.com/webhooks/telegram"
CLUB_SECRET="your_random_32char_string"

curl -s "https://api.telegram.org/bot${CLUB_BOT_TOKEN}/setWebhook" \
  -d "url=${CLUB_WEBHOOK_URL}" \
  -d "secret_token=${CLUB_SECRET}" \
  -d "allowed_updates=[\"message\",\"callback_query\"]"

# 验证
curl -s "https://api.telegram.org/bot${CLUB_BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
# 期望：url 字段等于 CLUB_WEBHOOK_URL
```

> **可选启动**：`CLUB_BOT_TOKEN` 留空时，Bot 功能自动跳过，不影响 API / 管理后台正常运行。

---

## 4. Nginx 反向代理

两个系统共用一台服务器，通过 Nginx 按域名路由：

### 4.1 写入配置文件

```bash
cat > /etc/nginx/sites-available/tg-services << 'EOF'
# 订阅系统后端
server {
    listen 80;
    server_name api.yourdomain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}

# 俱乐部系统后端
server {
    listen 80;
    server_name club.yourdomain.com;
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# 管理后台（静态文件，见第 5 节部署后再配置）
server {
    listen 80;
    server_name admin.yourdomain.com;
    root /app/tg-club/admin-web/dist;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
}
EOF

# 启用配置
ln -s /etc/nginx/sites-available/tg-services /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 4.2 申请 SSL 证书

```bash
# 一次性申请三个域名的证书
certbot --nginx \
  -d api.yourdomain.com \
  -d club.yourdomain.com \
  -d admin.yourdomain.com \
  --email your@email.com \
  --agree-tos \
  --non-interactive

# 验证证书自动续期
certbot renew --dry-run
```

---

## 5. 前端部署

### 5.1 部署订阅系统 Mini App（Vercel）

Mini App 是嵌入 Telegram 的 H5 页面，推荐用 Vercel 托管（免费、全球 CDN、自动 HTTPS）。

```bash
# 本地执行（需安装 Node.js 18+）
cd tg-subscription/mini-app

echo "VITE_API_URL=https://api.yourdomain.com" > .env.production

npm install
npm run build

# Vercel CLI 部署
npm i -g vercel
vercel --prod
# 按提示操作，完成后获得 URL，如 https://tg-sub-app.vercel.app
```

### 5.2 部署俱乐部 Mini App（Vercel）

```bash
cd tg-club/mini-app
echo "VITE_CLUB_API_URL=https://club.yourdomain.com" > .env.production
npm install && npm run build
vercel --prod
# 获得 URL，如 https://tg-club-app.vercel.app
```

### 5.3 部署管理后台 Admin Web

管理后台是一个完整的 React SPA，包含俱乐部、球员、转会三个管理模块，通过账号密码登录，JWT 鉴权。

**项目文件结构**

```
tg-club/admin-web/
├── index.html                         # HTML 入口
├── vite.config.ts                     # Vite 配置，开发时代理 /api
├── package.json
└── src/
    ├── main.tsx                       # React 入口
    ├── App.tsx                        # 路由 + 侧边栏布局 + 顶部退出
    ├── api/client.ts                  # Axios 封装，自动带 JWT Header
    ├── store/useAuthStore.ts          # Zustand 登录态管理
    └── pages/
        ├── Login.tsx                  # 登录页
        ├── clubs/ClubList.tsx         # 俱乐部管理（增删改查）
        ├── players/PlayerList.tsx     # 球员管理（增删改 + 转会 + 退役）
        └── transfers/TransferList.tsx # 转会记录（列表 + 录入）
```

**本地开发（无需服务器）**

```bash
cd tg-club/admin-web
npm install
npm run dev
# 浏览器访问 http://localhost:3001
# 会自动代理 /api/* → http://localhost:8001（本地后端）
```

**生产部署：构建并上传到服务器**

```bash
# 本地构建
cd tg-club/admin-web
echo "VITE_API_URL=https://club.yourdomain.com" > .env.production
npm install && npm run build

# 上传 dist 目录到服务器
scp -r dist root@YOUR_SERVER_IP:/app/tg-club/admin-web/

# 刷新 Nginx（Nginx 已配置将 admin.yourdomain.com 指向该目录）
ssh root@YOUR_SERVER_IP "nginx -t && systemctl reload nginx"
```

部署完成后，访问 `https://admin.yourdomain.com` 即可看到登录页面。

**页面功能一览**

| 路由 | 功能 |
|------|------|
| `/login` | 账号密码登录（账号配置在 `.env` 的 `ADMIN_USERNAME/PASSWORD`） |
| `/clubs` | 俱乐部列表，支持新增、编辑、删除，设置访问权限等级 |
| `/players` | 球员列表，支持新增、编辑、删除，快捷录入转会 / 办理退役 |
| `/transfers` | 转会记录列表，支持搜索球员后录入新转会 |

### 5.4 回填 Mini App URL

```bash
ssh root@YOUR_SERVER_IP
cd /app/tg-subscription
vim .env
# 将 MINI_APP_URL 改为 Vercel 部署后的地址
# MINI_APP_URL=https://tg-sub-app.vercel.app

# 重启生效
docker compose restart app
```

---

## 6. 系统联通验证

全部部署完成后，逐项执行以下验证命令：

```bash
# ① 订阅系统健康检查
curl -s https://api.yourdomain.com/health
# 期望：{"status":"ok"}

# ② 俱乐部系统健康检查
curl -s https://club.yourdomain.com/health
# 期望：{"status":"ok"}

# ③ 订阅系统套餐列表
curl -s https://api.yourdomain.com/api/v1/plans
# 期望：{"data":[{"id":"plan_basic_monthly",...},{"id":"plan_pro_monthly",...}]}

# ④ 俱乐部系统鉴权（无 Token 应返回 401）
curl -s https://club.yourdomain.com/api/v1/clubs
# 期望：{"detail":"Invalid initData"}  或 401

# ⑤ 管理后台登录
curl -s -X POST https://club.yourdomain.com/api/v1/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_strong_password"}'
# 期望：{"token":"eyJ..."}

# ⑥ Webhook 状态确认
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Webhook OK' if d['result']['url'] else 'NOT SET')"

# ⑦ 订阅系统内部 API（供 tg-club 调用）
curl -s "https://api.yourdomain.com/api/v1/payments/verify-tier?telegram_id=123456789" \
  -H "X-Api-Key: your_internal_api_key_here"
# 期望：{"telegram_id":123456789,"tier":"free"}

# ⑧ 俱乐部 Bot 健康检查（确认 Bot 已注册 Webhook）
curl -s "https://club.yourdomain.com/health"
# 期望：{"status":"ok","bot":"enabled"}

# ⑨ 在 Telegram 找到俱乐部 Bot，发送 /start
# 期望：回复主菜单消息 + 「浏览俱乐部」「浏览球员」按钮
# 若你的 Telegram ID 在 ADMIN_TELEGRAM_IDS 中，还会出现「管理统计」「打开管理后台」按钮
```

---

## 7. 冒烟测试用例

### 测试一：Bot 基础响应

```
步骤：
  1. 打开 Telegram，搜索你的 Bot
  2. 发送 /start

期望结果：
  ✅ Bot 回复欢迎消息
  ✅ 消息底部出现「订阅中心」按钮
  ✅ 底部菜单栏出现「订阅中心」Menu Button
```

### 测试二：Mini App 套餐展示

```
步骤：
  1. 点击「订阅中心」按钮
  2. Mini App 在 Telegram 内打开

期望结果：
  ✅ 页面加载正常，显示 Basic 和 Pro 两个套餐
  ✅ 显示 Stars 价格（250 / 550）
  ✅ 无报错（检查手机 Console：Telegram → Bot → 长按 Mini App → 打开 DevTools）
```

### 测试三：Stars 支付流程（需有 Stars 余额）

```
步骤：
  1. 在 Mini App 中点击「订阅 250 Stars」
  2. 弹出 Telegram 原生支付确认框
  3. 点击「确认支付」

期望结果：
  ✅ 扣除 250 Stars
  ✅ Bot 私聊发送订阅成功消息，显示套餐名和到期日期
  ✅ 数据库中 subscriptions 表出现新记录，status = active
```

验证数据库：

```bash
docker compose exec db psql -U subuser -d tg_sub \
  -c "SELECT id, user_id, plan_id, status, expires_at FROM subscriptions ORDER BY id DESC LIMIT 3;"
```

### 测试四：频道加入权限验证

```
前置条件：
  - 已有一个 Telegram 频道/群组
  - Bot 已设为该频道管理员
  - 频道已开启「加入需审核」模式

步骤（已订阅用户）：
  1. 用已完成订阅的账号，点击频道「申请加入」

期望结果：
  ✅ 立即自动通过，无需等待
  ✅ Bot 日志出现 approve_chat_join_request 调用

步骤（未订阅用户）：
  1. 用另一个未订阅账号，申请加入同一频道

期望结果：
  ✅ 申请被拒绝
  ✅ Bot 私聊发送「需要订阅」提示，带「查看套餐」按钮
```

### 测试五：管理后台 CRUD

```bash
# 获取 Token
TOKEN=$(curl -s -X POST https://club.yourdomain.com/api/v1/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_strong_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 创建俱乐部
curl -s -X POST https://club.yourdomain.com/api/v1/admin/clubs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"曼城","short_name":"MCI","country":"英格兰","founded_year":1880,"access_tier":"basic"}'
# 期望：{"data":{"id":1}}

# 查询俱乐部列表
curl -s https://club.yourdomain.com/api/v1/admin/clubs \
  -H "Authorization: Bearer $TOKEN"
# 期望：{"data":[{"id":1,"name":"曼城",...}]}

# 创建球员
curl -s -X POST https://club.yourdomain.com/api/v1/admin/players \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"哈兰德","current_club_id":1,"position":"ST","nationality":"挪威","height_cm":194,"weight_kg":88,"rating":9.2,"access_tier":"basic"}'
# 期望：{"data":{"id":1}}

# 录入转会
curl -s -X POST https://club.yourdomain.com/api/v1/admin/transfers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"player_id":1,"from_club_id":null,"to_club_id":1,"type":"permanent","transfer_date":"2022-07-01","fee_display":"€51M"}'
# 期望：{"data":{"id":1}}
```

### 测试六：订阅权限分级（tg-club）

```bash
# ① 订阅系统查询 free 用户等级
curl -s "https://api.yourdomain.com/api/v1/payments/verify-tier?telegram_id=999999" \
  -H "X-Api-Key: your_internal_api_key_here"
# 期望：{"telegram_id":999999,"tier":"free"}

# ② 用已订阅用户的 telegram_id 查询
curl -s "https://api.yourdomain.com/api/v1/payments/verify-tier?telegram_id=123456789" \
  -H "X-Api-Key: your_internal_api_key_here"
# 期望：{"telegram_id":123456789,"tier":"basic"} 或 "pro"
```

### 测试七：自动续费（Celery 定时任务）

```bash
# 手动触发定时任务，验证到期提醒逻辑
docker compose exec worker celery -A app.tasks.celery_app call check_expiring_subscriptions

# 查看 Worker 日志确认执行
docker compose logs worker --tail=20
```

---

## 8. 常见问题排查

### Bot 没有响应 /start

```bash
# 检查 Webhook 是否正确注册
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
# 检查 last_error_message 字段，常见原因：SSL 证书问题、端口未开放

# 检查应用日志
cd /app/tg-subscription && docker compose logs app --tail=50
```

### 支付成功但订阅未激活

```bash
# 检查支付回调日志
docker compose logs app | grep "successful_payment"

# 检查是否幂等重复处理（Redis 中查询）
docker compose exec redis redis-cli get "payment:processed:CHARGE_ID"
```

### tg-club 调用订阅系统报错

```bash
# 检查两个系统的 INTERNAL_API_KEY 是否一致
grep INTERNAL_API_KEY /app/tg-subscription/.env
grep SUBSCRIPTION_INTERNAL_API_KEY /app/tg-club/backend/.env

# 手动测试连通性
docker compose exec backend curl -s \
  "http://YOUR_SERVER_IP:8000/api/v1/payments/verify-tier?telegram_id=123" \
  -H "X-Api-Key: your_internal_api_key_here"
```

### 数据库连接失败

```bash
# 检查容器状态
docker compose ps

# 重启数据库
docker compose restart db

# 查看数据库日志
docker compose logs db --tail=30
```

### SSL 证书问题

```bash
# 手动续期
certbot renew --force-renewal

# 检查证书有效期
certbot certificates
```

---

## 9. 快速命令速查

```bash
# 查看所有容器状态
cd /app/tg-subscription && docker compose ps
cd /app/tg-club/backend && docker compose ps

# 重启单个服务
docker compose restart app      # 订阅系统
docker compose restart backend  # 俱乐部系统

# 查看实时日志
docker compose logs -f app
docker compose logs -f backend

# 进入数据库
docker compose exec db psql -U subuser -d tg_sub    # 订阅系统库
docker compose exec db psql -U clubuser -d tg_club  # 俱乐部系统库

# 清除 Redis 缓存（订阅状态缓存）
docker compose exec redis redis-cli flushdb

# 更新代码并重新部署
git pull && docker compose up -d --build app
```

---

## 10. 系统通信架构说明

本节说明 **俱乐部信息系统（tg-club）与管理端** 之间所有通信路径的协议、鉴权方式和数据流向，方便排查问题和二次开发。

---

### 10.1 整体通信拓扑

```
                        ┌─────────────────────────────────────┐
                        │          Telegram 平台               │
                        │  ┌─────────┐    ┌──────────────┐   │
                        │  │ 用户 App │    │  管理员 App   │   │
                        │  └────┬────┘    └──────┬───────┘   │
                        └───────┼────────────────┼───────────┘
                                │ HTTPS           │ HTTPS
              ┌─────────────────┼─────────────────┼──────────────────┐
              │                 ↓                 ↓                  │
              │     ┌──────────────────┐  ┌───────────────────┐     │
              │     │   Mini App 前端   │  │  Telegram Bot      │     │
              │     │  (Vercel CDN)    │  │  (tg-club bot)    │     │
              │     └────────┬─────────┘  └────────┬──────────┘     │
              │              │ HTTPS API            │ PTB callbacks   │
              │              ↓                      ↓                │
              │     ┌──────────────────────────────────────────┐     │
              │     │          tg-club 后端 (FastAPI)           │     │
              │     │  :8001  club.yourdomain.com              │     │
              │     │                                          │     │
              │     │  ┌──────────────┐  ┌─────────────────┐  │     │
              │     │  │  User API    │  │   Admin API      │  │     │
              │     │  │ /api/v1/clubs│  │ /api/v1/admin/  │  │     │
              │     │  │ /api/v1/plyr │  │ clubs/players/  │  │     │
              │     │  └──────┬───────┘  └────────┬────────┘  │     │
              │     │         │ tier check         │ JWT auth  │     │
              │     │         ↓                    ↓           │     │
              │     │  ┌──────────────┐  ┌─────────────────┐  │     │
              │     │  │subscription  │  │ PostgreSQL(club) │  │     │
              │     │  │  _client.py  │  │ Redis cache      │  │     │
              │     │  └──────┬───────┘  └─────────────────┘  │     │
              │     └─────────┼────────────────────────────────┘     │
              │               │ HTTP + X-Api-Key                     │
              │               ↓                                      │
              │     ┌──────────────────────────────────────────┐     │
              │     │       tg-subscription 后端 (FastAPI)      │     │
              │     │  :8000  api.yourdomain.com               │     │
              │     │                                          │     │
              │     │  GET /api/v1/payments/verify-tier        │     │
              │     │  ┌────────────────────────────────────┐  │     │
              │     │  │  PostgreSQL(sub) + Redis cache      │  │     │
              │     │  └────────────────────────────────────┘  │     │
              │     └──────────────────────────────────────────┘     │
              │                                                       │
              │     ┌──────────────────────────────────────────┐     │
              │     │       Admin Web 前端 (Nginx 静态)         │     │
              │     │  admin.yourdomain.com → /api/v1/admin/*  │     │
              │     └──────────────────────────────────────────┘     │
              └───────────────────────────────────────────────────────┘
```

---

### 10.2 用户端（Mini App）→ 俱乐部后端

**场景**：用户在 Telegram 内打开俱乐部 Mini App，浏览俱乐部/球员信息。

| 项目 | 说明 |
|------|------|
| 协议 | HTTPS |
| 鉴权方式 | **Telegram initData 签名验证** |
| 请求头 | `X-Init-Data: <initData 字符串>` |
| 验证逻辑 | 后端用 HMAC-SHA256 校验签名，提取 `user.id` |

**请求示例**

```
GET /api/v1/clubs?search=曼城
Host: club.yourdomain.com
X-Init-Data: query_id=xxx&user=%7B%22id%22%3A123456789...&hash=abc123
```

**后端处理流程**

```
收到请求
  ↓
dependencies.get_tg_user()
  → 解析 X-Init-Data Header
  → HMAC-SHA256 验签（防伪造）
  → 提取 telegram_id
  ↓
dependencies.get_tier()
  → 调用 subscription_client.get_user_tier(telegram_id)
  → 先查 Redis 缓存（TTL 5 分钟）
  → 未命中则 HTTP 调用订阅系统
  → 返回 "free" | "basic" | "pro"
  ↓
club_service.list_clubs(db, tier, ...)
  → 按 tier 过滤字段（locked 字段提示需升级）
  → 返回结果
```

---

### 10.3 俱乐部后端 → 订阅系统（权限查询）

这是 **两个系统唯一的耦合点**，通过 HTTP 内部 API 实现，不共享数据库。

| 项目 | 说明 |
|------|------|
| 方向 | tg-club → tg-subscription |
| 协议 | HTTP（同一 VPS 内网，无需 HTTPS） |
| 鉴权 | 请求头 `X-Api-Key: <INTERNAL_API_KEY>` |
| 端点 | `GET /api/v1/payments/verify-tier?telegram_id=<id>` |
| 缓存 | Redis，TTL 5 分钟，Key: `club:tier:{telegram_id}` |
| 降级策略 | 订阅系统不可达时默认返回 `"free"`，保证可用性 |

**实际调用代码**（`subscription_client.py`）

```python
async with httpx.AsyncClient(timeout=3.0) as client:
    resp = await client.get(
        f"{settings.subscription_service_url}/api/v1/payments/verify-tier",
        params={"telegram_id": telegram_id},
        headers={"X-Api-Key": settings.subscription_internal_api_key},
    )
    tier = resp.json().get("tier", "free")
```

**配置对应关系**

```
tg-subscription/.env              tg-club/backend/.env
─────────────────                 ────────────────────────────
INTERNAL_API_KEY=secret123   →    SUBSCRIPTION_INTERNAL_API_KEY=secret123
                                  SUBSCRIPTION_SERVICE_URL=http://127.0.0.1:8000
```

> 两边的密钥 **必须完全一致**，这是最常见的配置错误，排查命令见第 8 节。

---

### 10.4 管理员通道：Admin Web → 俱乐部后端

**场景**：管理员通过浏览器打开 `admin.yourdomain.com` 管理俱乐部/球员数据。

| 项目 | 说明 |
|------|------|
| 协议 | HTTPS |
| 鉴权方式 | **JWT Token（HS256）** |
| 登录端点 | `POST /api/v1/admin/auth/login`（用户名/密码，配置在 `.env`） |
| Token 有效期 | 24 小时，存在浏览器 `localStorage` |
| 后续请求头 | `Authorization: Bearer <JWT>` |
| 前端自动跳转 | 401 响应自动跳回登录页 |

**登录流程**

```
浏览器 → POST /api/v1/admin/auth/login
  Body: {"username": "admin", "password": "xxx"}
  ↓
后端对比 ADMIN_USERNAME / ADMIN_PASSWORD（.env）
  ↓
生成 JWT（HS256，有效期 24h）
  ↓
前端存入 localStorage["admin_token"]
  ↓
后续所有 Admin API 请求自动带 Authorization: Bearer <token>
```

**Admin API 端点清单**

```
POST   /api/v1/admin/auth/login         登录，获取 JWT
GET    /api/v1/admin/clubs              俱乐部列表
POST   /api/v1/admin/clubs              新增俱乐部
PUT    /api/v1/admin/clubs/{id}         编辑俱乐部
DELETE /api/v1/admin/clubs/{id}         删除俱乐部
GET    /api/v1/admin/players            球员列表
POST   /api/v1/admin/players            新增球员
PUT    /api/v1/admin/players/{id}       编辑球员
DELETE /api/v1/admin/players/{id}       删除球员
GET    /api/v1/admin/transfers          转会记录列表
POST   /api/v1/admin/transfers          录入转会
POST   /api/v1/admin/retirements        办理退役
```

---

### 10.5 管理员通道：Telegram Bot → 俱乐部后端

**场景**：管理员在 Telegram 中直接发消息查询数据（不需要打开浏览器）。

| 项目 | 说明 |
|------|------|
| 协议 | Telegram Webhook（HTTPS POST） |
| 鉴权方式 | `X-Telegram-Bot-Api-Secret-Token` Header |
| 权限控制 | 检查 `telegram_id` 是否在 `ADMIN_TELEGRAM_IDS` 列表中 |
| Bot 数据库连接 | 通过 `context.bot_data["db_factory"]` 直连 tg-club PostgreSQL |

**Bot 命令与交互路径**

```
Telegram 用户发消息
  ↓
Telegram 服务器推送到 POST /webhooks/telegram
  ↓
main.py → _bot_app.process_update(update)
  ↓
handlers.py 分发：
  ├── /start → _main_keyboard（普通用户 + 管理员不同按钮）
  ├── /clubs → _send_club_list（直连 PostgreSQL）
  ├── /players → _send_player_list（直连 PostgreSQL）
  ├── /search <词> → 搜索 clubs + players
  ├── /stats → _send_stats（仅管理员，检查 ADMIN_TELEGRAM_IDS）
  └── callback_data 路由 → 内联键盘各级页面
```

**管理员专属功能（需要 telegram_id 在白名单中）**

```
📊 管理统计   → 显示总俱乐部数/球员数/最近转会
🖥 管理后台链接 → 跳转 admin.yourdomain.com
/stats 命令   → 同上
```

---

### 10.6 第三方支付 → 订阅系统 Webhook

**场景**：用户用微信/支付宝付款后，平台服务器主动推送通知给订阅系统。

| 渠道 | Webhook 端点 | 验证方式 |
|------|-------------|---------|
| 微信支付 | `POST /webhooks/wechat` | RSA 签名 + AES-GCM 解密（微信 v3 协议） |
| 支付宝 | `POST /webhooks/alipay` | RSA2 公钥验签（支付宝标准协议） |

**回调处理流程**

```
微信/支付宝服务器 → POST /webhooks/wechat（或 alipay）
  ↓
验签（防伪造，失败则返回 FAIL，不更新数据库）
  ↓
查找 payment_orders 表（by out_trade_no）
  ↓
更新 status → paid，记录 trade_no / paid_at
  ↓
subscription_service.activate_from_third_party()
  → 激活/续期 subscriptions 表
  → 清除 Redis 订阅缓存
  ↓
Bot.send_message(user.telegram_id)
  → 私聊发送「支付成功」通知
```

> **重要**：微信和支付宝的回调 URL 必须在商户后台提前配置白名单，否则回调不会发送。
> - 微信：商户平台 → 开发配置 → 通知 URL
> - 支付宝：开放平台 → 应用信息 → 授权回调地址

---

### 10.7 数据权限分级说明

用户访问俱乐部/球员数据时，字段按订阅等级动态过滤：

**俱乐部数据**

| 字段 | free | basic | pro |
|------|------|-------|-----|
| 名称、缩写、国家、Logo | ✅ | ✅ | ✅ |
| 成立年份、主场、容量 | ❌ | ✅ | ✅ |
| 详细描述、旗下球员列表 | ❌ | ✅ | ✅ |
| 访问 `access_tier=pro` 的俱乐部 | ❌ | ❌ | ✅ |

**球员数据**

| 字段 | free | basic | pro |
|------|------|-------|-----|
| 姓名、位置、所在俱乐部 | ✅ | ✅ | ✅ |
| 身高、体重、惯用脚、国籍 | ❌ | ✅ | ✅ |
| 转会历史（最近 1 条） | ❌ | ✅ | ✅ |
| 完整转会历史、简介 | ❌ | ❌ | ✅ |
| 相似球员推荐（`/similar`） | ❌ | ❌ | ✅ |
| 自由球员列表（`/free-agents`） | ❌ | ✅ | ✅ |

**权限判断代码**（`subscription_client.py`）

```python
def can_access(tier: str, required: str) -> bool:
    order = {"free": 0, "basic": 1, "pro": 2}
    return order.get(tier, 0) >= order.get(required, 0)
```

当用户等级不满足时，API 返回的字段中会包含：

```json
{
  "id": 1,
  "name": "曼彻斯特城",
  "_locked": true,
  "_required_tier": "basic"
}
```

前端 Mini App 读到 `_locked: true` 时，显示升级订阅提示。
