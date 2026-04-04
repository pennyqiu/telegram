# 原生嵌入 Telegram 方案设计

> 目标：用户从发现产品到完成付费订阅，全程不离开 Telegram App

---

## 1. Telegram 原生能力全景

| 能力 | API | 用途 |
|------|-----|------|
| **Mini App** | `WebApp` JS SDK | 内嵌 H5 页面，承载订阅中心 UI |
| **Stars 月付订阅** | `sendInvoice` + `subscription_period` | 原生周期付费，Telegram 自动续费 |
| **Stars 一次性付费** | `sendInvoice` + `currency=XTR` | 季付/年付一次性 Invoice |
| **加入请求审核** | `chatJoinRequest` | 付费验证后自动放行频道入口 |
| **Deep Link** | `t.me/bot?startapp=xxx` | 从频道/分享链接直达订阅中心 |
| **Bot Menu Button** | `setChatMenuButton` | Bot 底部固定「订阅中心」入口 |

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Telegram App                                 │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Telegram Mini App（内嵌 H5）                     │   │
│  │   ┌────────────┐  ┌──────────────┐  ┌───────────────────┐   │   │
│  │   │  套餐选择   │  │  订阅状态    │  │  账单/历史记录    │   │   │
│  │   │  Plan List │  │  My Status  │  │  Invoice History  │   │   │
│  │   └─────┬──────┘  └──────────────┘  └───────────────────┘   │   │
│  │         │ WebApp.openInvoice()                                │   │
│  └─────────┼────────────────────────────────────────────────────┘   │
│            │                                                         │
│  ┌─────────▼────────────────────────────────────────────────────┐   │
│  │              Telegram 原生支付弹层                             │   │
│  │   ┌──────────────────────────────────────────────────────┐   │   │
│  │   │  💫 订阅 Pro 专业版                                    │   │   │
│  │   │  每月 550 Stars · 自动续费                             │   │   │
│  │   │                          [确认支付] [取消]             │   │   │
│  │   └──────────────────────────────────────────────────────┘   │   │
│  └─────────┬────────────────────────────────────────────────────┘   │
│            │ successful_payment 事件                                  │
└────────────┼────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     后端服务（最小化）                                 │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│   │  Bot Handler  │  │  Mini App   │  │     定时任务              │  │
│   │  支付回调处理  │  │  API 接口   │  │  到期提醒 / 移出频道      │  │
│   └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                              │                                        │
│                    ┌─────────▼──────────┐                            │
│                    │   PostgreSQL + Redis│                            │
└────────────────────┴────────────────────┴────────────────────────────┘
```

---

## 3. Mini App 详细设计

### 3.1 入口方式

```
方式一：Bot Menu Button（主入口，最推荐）
─────────────────────────────────────────
用户打开 Bot 对话框
  └── 底部固定「订阅中心」按钮（所有用户可见）
        └── 点击打开 Mini App 全屏页面

方式二：Inline Button（命令触发）
─────────────────────────────────
/start 或 /status 命令
  └── Bot 回复消息 + [打开订阅中心] 按钮
        └── 点击打开 Mini App

方式三：Deep Link 分享（裂变增长）
────────────────────────────────────
t.me/YourBot?startapp=ref_userId
  └── 打开 Bot + 自动启动 Mini App
        └── 记录推荐关系，支持返佣
```

### 3.2 Mini App 页面结构

```
Mini App
├── / 首页（套餐选择）
│   ├── 套餐卡片（Stars 价格、功能对比）
│   ├── 试用 / 立即订阅按钮 → 触发 Stars 支付弹层
│   └── 当前已订阅则展示状态
│
├── /status 我的订阅
│   ├── 当前套餐 + 到期时间
│   ├── 升级/降级套餐
│   └── 取消自动续费（引导至 Telegram 设置）
│
├── /invoices 账单记录
│   └── 历史支付记录（Stars 金额 + 日期 + 状态）
│
└── /channels 我的频道
    └── 已解锁频道快速入口
```

### 3.3 Mini App 与 Bot 的通信

```javascript
const tg = window.Telegram.WebApp;

// 身份验证：无需注册，直接使用 Telegram 用户信息
const initData = tg.initData;           // 发给后端做签名验证
const user = tg.initDataUnsafe.user;    // { id, first_name, username }

// 触发支付：不跳转外部页面，弹出 Telegram 原生支付框
async function handleSubscribe(planId) {
  const { invoiceLink } = await api.createInvoice({ planId });

  tg.openInvoice(invoiceLink, (status) => {
    if (status === 'paid') {
      tg.HapticFeedback.notificationOccurred('success');
      tg.showPopup({ message: '订阅成功！' });
      refreshStatus();
    }
  });
}

// 自适应 Telegram 主题色（深色/浅色无缝融合）
document.documentElement.dataset.theme = tg.colorScheme;
```

---

## 4. Stars 原生订阅集成

### 4.1 创建月付订阅 Invoice

```python
# 生成 invoice link，供 Mini App 调用 openInvoice
link = await bot.create_invoice_link(
    title="Pro 专业版",
    description="每月自动续费，随时可在 Telegram 设置中取消",
    payload=f"sub_{user_id}_{plan_id}_{sub_id}",
    currency="XTR",
    prices=[LabeledPrice("Pro 月付", 550)],
    subscription_period=2592000,    # 30天，开启 Telegram 原生自动续费
)
```

### 4.2 Stars 汇率参考（2026）

| Stars 数量 | 约等于 USD | 约等于 CNY | 到手（扣30%平台费） |
|-----------|-----------|-----------|------------------|
| 250 XTR | ~$5 | ~¥36 | ~¥25 |
| 550 XTR | ~$11 | ~¥79 | ~¥55 |
| 1400 XTR | ~$28 | ~¥200 | ~¥140 |

### 4.3 自动续费处理

Telegram 续费成功后再次触发 `successful_payment`，通过 `is_recurring` 字段区分：

```python
async def successful_payment_handler(update: Update, context):
    payment = update.message.successful_payment

    if payment.is_recurring:
        # 自动续费：延长有效期
        await subscription_service.handle_renewal(user_id, payment)
    else:
        # 首次订阅：激活 + 引导加入频道
        await subscription_service.activate(sub_id, payment)
```

---

## 5. 频道访问控制：Join Request 方案

```
用户 → 点击「申请加入」付费频道
  └── Bot 收到 chatJoinRequest 事件
        ├── 查 Redis 缓存（5min TTL，高频场景极快）
        ├── 有效订阅 → approve_chat_join_request（自动通过）
        └── 无订阅 → decline + 私聊发送订阅引导（附 Mini App 按钮）
```

**优势：**
- 无需管理邀请链接，不存在链接被转发滥用的问题
- Bot 有完整控制权，取消订阅后可随时移出
- 天然支持重新加入（重新订阅后再次申请即可通过）

---

## 6. 完整用户旅程

```
① 用户发现入口
   └── 搜索 Bot / 频道分享链接 / 朋友推荐 Deep Link

② 打开 Bot → 底部出现「订阅中心」按钮

③ 点击「订阅中心」→ Telegram 内打开 Mini App
   └── 套餐展示，自动适配深色/浅色主题

④ 选择套餐 → 点击「订阅」
   └── 弹出 Telegram 原生支付确认框
   └── 一键确认，Stars 余额直接扣除

⑤ 支付成功
   └── Mini App 内成功提示 + 触感反馈
   └── Bot 私聊发送欢迎消息

⑥ 申请加入付费频道
   └── Bot 自动审核通过

⑦ Telegram 每月自动续费
   └── Bot 发送续费成功通知

⑧ 到期前 3 天（如关闭了自动续费）
   └── Bot 私聊发送提醒，附 Mini App 续费按钮

⑨ 取消订阅
   └── Telegram 设置 → 订阅 → 取消
   └── 或 Mini App 内操作
   └── 到期后 Bot 自动移出频道
```

---

## 7. 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| Bot 框架 | `python-telegram-bot` v21 | 异步，支持所有最新 API |
| Mini App 前端 | React + Vite + `@telegram-apps/telegram-ui` | 官方组件库，主题无缝融合 |
| 后端服务 | FastAPI（异步） | 轻量 API，Webhook 处理 |
| 数据库 | PostgreSQL + Redis | 持久化 + 订阅状态缓存 |
| 定时任务 | Celery + Redis Beat | 到期提醒、移出频道 |
| Mini App 部署 | Vercel / Cloudflare Pages | 免费，全球 CDN |
| Bot 后端部署 | Docker Compose（单机）/ Fly.io | 低成本 |

---

## 8. 部署结构与通信机制

### 8.1 整体部署拓扑

```
                        互联网
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
  ┌──────────────┐ ┌─────────────┐ ┌──────────────────┐
  │ Telegram 服务器│ │  用户设备   │ │  Vercel / CF     │
  │ (api.telegram│ │  Telegram   │ │  Pages（CDN）     │
  │    .org)     │ │  App        │ │  Mini App 静态资源 │
  └──────┬───────┘ └──────┬──────┘ └────────┬─────────┘
         │  Webhook POST  │  HTTPS API 请求  │
         │  (Bot 事件推送) │  (Mini App 调用) │
         ▼                ▼                  │
  ┌─────────────────────────────────────────┘
  │            你的服务器（VPS / Fly.io）
  │
  │  ┌───────────────────────────────────────┐
  │  │   Nginx（反代 + SSL 终止）             │
  │  │   443 → 8000（FastAPI）               │
  │  └───────────────┬───────────────────────┘
  │                  │
  │  ┌───────────────▼───────────────────────┐
  │  │   FastAPI App（Bot + Mini App API）    │
  │  │   · POST /webhooks/telegram  ← TG 推送 │
  │  │   · GET  /plans              ← Mini App│
  │  │   · POST /payments/invoice   ← Mini App│
  │  └───────┬───────────────┬───────────────┘
  │          │               │
  │  ┌───────▼──────┐ ┌──────▼──────┐
  │  │  PostgreSQL  │ │    Redis    │
  │  │  (持久化)    │ │ (缓存+队列) │
  │  └──────────────┘ └──────┬──────┘
  │                          │
  │  ┌───────────────────────▼───────────────┐
  │  │   Celery Worker + Beat（定时任务）     │
  │  │   · 每天扫描到期订阅，发提醒           │
  │  │   · 每小时处理宽限期/踢人             │
  │  └───────────────────────────────────────┘
  └────────────────────────────────────────────
```

---

### 8.2 与 Telegram 的通信机制：Webhook

系统使用 **Webhook 模式**（生产推荐），而非轮询（Polling）。

#### 两种模式对比

| | Webhook（生产） | Long Polling（开发调试） |
|---|---|---|
| 原理 | Telegram 主动 POST 到你的服务器 | Bot 反复调用 `getUpdates` 拉取 |
| 延迟 | 毫秒级 | 1-2 秒 |
| 资源消耗 | 极低，有消息才处理 | 持续占用连接 |
| 要求 | 需公网 HTTPS 域名 | 无需公网 IP |
| 适用场景 | 生产部署 | 本地开发 |

#### Webhook 注册流程

```
部署启动时，Bot 向 Telegram 注册 Webhook 地址：

Bot → Telegram API
POST https://api.telegram.org/bot{TOKEN}/setWebhook
{
  "url": "https://api.your-domain.com/webhooks/telegram",
  "secret_token": "your_random_secret",   ← 防伪造请求
  "allowed_updates": [
    "message",
    "callback_query",
    "pre_checkout_query",
    "chat_join_request"
  ]
}
```

#### Webhook 收消息流程

```
用户在 Telegram 操作（付款 / 点按钮 / 申请加入频道）
          │
          ▼
Telegram 服务器 → POST https://api.your-domain.com/webhooks/telegram
                  Headers:
                    X-Telegram-Bot-Api-Secret-Token: your_random_secret
                  Body: { update_id, message / callback_query / ... }
          │
          ▼
FastAPI 收到请求
  1. 验证 Secret Token（防伪造）
  2. 交给 python-telegram-bot 解析 Update
  3. 路由到对应 Handler（命令/支付/加群审核）
  4. 异步处理业务逻辑
  5. 调用 Telegram Bot API 回复用户（Bot 主动发请求给 TG）
```

#### Bot 主动发消息

Bot 收到 Webhook 后，主动调用 Telegram API 回复：

```
FastAPI App → HTTPS → api.telegram.org/bot{TOKEN}/sendMessage
                                              /answerPreCheckoutQuery
                                              /approveChatJoinRequest
                                              ...
```

> **关键点**：Webhook 是 Telegram → 你的服务器（单向推送），Bot 回复是你的服务器 → Telegram（主动调用），两个方向都是 HTTPS。

---

### 8.3 Mini App 通信机制

Mini App 前端与后端的通信分两条链路：

```
┌─────────────────────────────────────────────────────┐
│  链路 1：Mini App ↔ Telegram 客户端（本地通信）       │
│                                                      │
│  Mini App JS (WebApp SDK)                            │
│    tg.initData          → 获取用户身份（无需登录）    │
│    tg.openInvoice(link) → 触发原生支付弹层            │
│    tg.HapticFeedback    → 触感反馈                   │
│    tg.colorScheme       → 读取主题色                 │
│                                                      │
│  这部分通信在 Telegram App 内部完成，不走网络          │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  链路 2：Mini App ↔ 你的后端（REST API）              │
│                                                      │
│  Mini App                                            │
│    headers: { X-Init-Data: tg.initData }             │
│    GET  /plans              → 获取套餐列表            │
│    POST /payments/invoice   → 创建支付 Invoice        │
│    GET  /subscriptions/current → 查询订阅状态         │
│                                                      │
│  后端验证 initData 签名 → 确认用户身份               │
│  → 无需 Cookie / JWT，Telegram 背书即信任             │
└─────────────────────────────────────────────────────┘
```

---

### 8.4 SSL / 域名要求

| 组件 | 域名需求 | SSL 方案 |
|------|----------|----------|
| Bot 后端 | 必须有公网域名 + HTTPS | Let's Encrypt（免费）/ Nginx 自动申请 |
| Mini App | 必须 HTTPS | Vercel / CF Pages 自动提供 |
| 数据库 / Redis | 内网即可，不需要公网 | 不需要 SSL |

---

### 8.5 推荐部署方案

#### 方案 A：单机 VPS（月费约 $6，适合冷启动）

```
VPS（如 DigitalOcean / Vultr / 腾讯云）
├── Nginx（反代 + Let's Encrypt SSL）
├── Docker Compose
│   ├── fastapi-app（Bot + API）
│   ├── celery-worker
│   ├── celery-beat
│   ├── postgres
│   └── redis
└── 域名：api.your-domain.com → 指向 VPS IP
```

#### 方案 B：Fly.io（按用量付费，冷启动更简单）

```
Fly.io
├── fly-app（FastAPI，自动 HTTPS）
├── fly-worker（Celery Worker）
├── Fly Postgres（托管 PG）
└── Upstash Redis（托管 Redis，免费额度够用）

Mini App → Vercel（免费部署，自动 HTTPS）
```

#### 本地开发调试

```bash
# 使用 ngrok 将本地端口暴露为公网 HTTPS，临时用于 Webhook 调试
ngrok http 8000
# 得到 https://xxxx.ngrok.io
# 注册为 Webhook: setWebhook?url=https://xxxx.ngrok.io/webhooks/telegram

# 或直接用 Polling 模式开发，无需公网
python -m app.main --polling
```

---

## 9. 开发优先级

| Sprint | 周期 | 交付 |
|--------|------|------|
| 1 | 1 周 | Bot + Stars 月付 + Join Request 权限 |
| 2 | 1 周 | 自动续费处理 + 宽限期 + 到期踢人 |
| 3 | 1-2 周 | Mini App 套餐页 + 状态页 |
| 4 | 1 周 | Mini App 接入支付 + 账单页 |
| 5 | 按需 | 管理统计后台 + 推荐返佣 |
