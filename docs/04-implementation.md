# 技术实现方案

## 1. 项目结构

```
telegram-subscription-bot/
├── app/
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── commands.py         # /start /status /help
│   │   │   ├── callbacks.py        # InlineKeyboard 回调
│   │   │   ├── payments.py         # pre_checkout / successful_payment
│   │   │   └── join_requests.py    # chatJoinRequest 审核
│   │   ├── keyboards.py
│   │   └── messages.py
│   │
│   ├── api/                        # Mini App 后端接口（轻量）
│   │   ├── routes/
│   │   │   ├── plans.py            # GET /plans
│   │   │   ├── subscriptions.py    # GET /subscriptions/current
│   │   │   ├── payments.py         # POST /payments/invoice, GET /payments
│   │   │   └── webhooks.py         # POST /webhooks/telegram
│   │   └── dependencies.py         # initData 身份验证
│   │
│   ├── services/
│   │   ├── subscription_service.py
│   │   ├── payment_service.py
│   │   ├── user_service.py
│   │   └── notification_service.py
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── plan.py
│   │   ├── subscription.py
│   │   └── payment.py
│   │
│   ├── tasks/
│   │   ├── celery_app.py
│   │   └── subscription_tasks.py   # 到期提醒、踢人
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── redis.py
│   │
│   └── main.py
│
├── mini-app/                       # Mini App 前端（React + Vite）
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Plans.tsx           # 套餐选择页
│   │   │   ├── Status.tsx          # 订阅状态页
│   │   │   └── Invoices.tsx        # 账单记录页
│   │   ├── hooks/
│   │   │   └── useTelegram.ts      # WebApp SDK 封装
│   │   └── api/
│   │       └── client.ts           # 后端请求（自动带 initData 头）
│   ├── package.json
│   └── vite.config.ts
│
├── migrations/                     # Alembic 迁移
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## 2. 核心代码实现

### 2.1 Mini App initData 身份验证

Mini App 无需独立登录系统，通过 Telegram 提供的 `initData` 验证用户身份：

```python
# app/api/dependencies.py
import hmac, hashlib
from fastapi import Header, HTTPException
from urllib.parse import parse_qsl

async def verify_init_data(x_init_data: str = Header(...)) -> dict:
    """验证 Telegram Mini App initData，提取用户信息"""
    params = dict(parse_qsl(x_init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData")

    import json
    user_data = json.loads(params["user"])
    return user_data  # 包含 id, first_name, username 等
```

```python
# Mini App API 路由使用示例
@router.get("/subscriptions/current")
async def get_current_subscription(
    tg_user: dict = Depends(verify_init_data),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_or_create(db, tg_user)
    sub = await subscription_service.get_active(db, user.id)
    return {"data": sub}
```

### 2.2 Mini App 前端核心代码

```typescript
// mini-app/src/hooks/useTelegram.ts
export function useTelegram() {
  const tg = window.Telegram.WebApp;

  // 订阅支付：触发 Telegram 原生支付弹层
  const subscribe = async (planId: string) => {
    const { invoiceLink } = await api.createInvoice({ planId });

    tg.openInvoice(invoiceLink, (status) => {
      if (status === "paid") {
        tg.HapticFeedback.notificationOccurred("success");
        tg.showPopup({ message: "订阅成功！欢迎加入。" });
        refreshSubscriptionStatus();
      } else if (status === "failed") {
        tg.showPopup({ message: "支付未完成，请重试。" });
      }
    });
  };

  return {
    user: tg.initDataUnsafe.user,
    initData: tg.initData,          // 发给后端验证身份
    colorScheme: tg.colorScheme,    // 深色/浅色模式
    subscribe,
    close: tg.close,
    expand: tg.expand,
  };
}
```

```typescript
// mini-app/src/api/client.ts
const tg = window.Telegram.WebApp;

export const api = {
  async createInvoice(params: { planId: string }) {
    const res = await fetch(`${API_BASE}/payments/invoice`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Init-Data": tg.initData,   // 身份验证
      },
      body: JSON.stringify(params),
    });
    return res.json();
  },

  async getSubscription() {
    const res = await fetch(`${API_BASE}/subscriptions/current`, {
      headers: { "X-Init-Data": tg.initData },
    });
    return res.json();
  },
};
```

### 2.3 Stars 订阅支付

```python
# app/api/routes/payments.py

@router.post("/payments/invoice")
async def create_invoice(
    body: CreateInvoiceRequest,
    tg_user: dict = Depends(verify_init_data),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_or_create(db, tg_user)
    plan = await db.get(Plan, body.plan_id)

    # 创建 pending 订阅记录
    sub = await subscription_service.create_pending(db, user, plan)

    # 生成 Telegram Invoice Link
    link = await bot.create_invoice_link(
        title=plan.name,
        description=f"每月自动续费，随时可在 Telegram 设置中取消",
        payload=f"sub_{user.id}_{plan.id}_{sub.id}",
        currency="XTR",
        prices=[LabeledPrice(plan.name, plan.stars_price)],
        subscription_period=2592000,   # 月付自动续费
    )
    return {"invoiceLink": link}
```

### 2.4 支付回调处理

```python
# app/bot/handlers/payments.py

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """必须在 10 秒内回复"""
    query = update.pre_checkout_query
    try:
        _, user_id, plan_id, sub_id = query.invoice_payload.split("_", 3)
        plan = await plan_service.get(plan_id)
        if not plan or not plan.is_active:
            await query.answer(ok=False, error_message="该套餐已下架")
            return
        await query.answer(ok=True)
    except Exception:
        await query.answer(ok=False, error_message="验证失败，请重试")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    charge_id = payment.telegram_payment_charge_id

    # 幂等：防止重复处理
    if await redis.exists(f"payment:processed:{charge_id}"):
        return
    await redis.set(f"payment:processed:{charge_id}", "1", ex=2592000)

    _, user_id, plan_id, sub_id = payment.invoice_payload.split("_", 3)

    # 区分首次订阅 vs 自动续费
    if payment.is_recurring:
        await subscription_service.handle_renewal(
            int(sub_id), charge_id, payment.total_amount
        )
        await context.bot.send_message(
            update.effective_user.id,
            "已自动续费成功，感谢您的支持！"
        )
    else:
        sub = await subscription_service.activate(
            int(sub_id), charge_id, payment.total_amount
        )
        # 自动通过频道 Join Request（如果有待审核）
        await channel_service.approve_pending_requests(update.effective_user.id, sub)
        await context.bot.send_message(
            update.effective_user.id,
            f"订阅成功！\n"
            f"套餐：{sub.plan.name}\n"
            f"有效期至：{sub.expires_at.strftime('%Y-%m-%d')}\n\n"
            f"前往频道申请加入即可自动通过审核。"
        )
```

### 2.5 Join Request 审核

```python
# app/bot/handlers/join_requests.py

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user_id = request.from_user.id
    channel_id = request.chat.id

    # 优先查 Redis 缓存，减少 DB 查询
    cache_key = f"sub:active:{user_id}"
    cached = await redis.get(cache_key)

    if cached is None:
        has_sub = await subscription_service.has_active_subscription(user_id)
        await redis.set(cache_key, "1" if has_sub else "0", ex=300)
    else:
        has_sub = cached == "1"

    if has_sub:
        await context.bot.approve_chat_join_request(channel_id, user_id)
    else:
        await context.bot.decline_chat_join_request(channel_id, user_id)
        await context.bot.send_message(
            user_id,
            "访问该频道需要订阅。点击下方按钮查看套餐：",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "查看订阅套餐",
                    web_app=WebAppInfo(url=MINI_APP_URL)
                )
            ]])
        )
```

### 2.6 定时任务

```python
# app/tasks/subscription_tasks.py

@shared_task(name="check_expiring_subscriptions")
def check_expiring_subscriptions():
    """每天 10:00 执行：发送到期提醒"""
    with get_db_sync() as db:
        threshold = datetime.utcnow() + timedelta(days=3)
        subs = db.query(Subscription).filter(
            Subscription.status == "active",
            Subscription.expires_at <= threshold,
            Subscription.expires_at > datetime.utcnow(),
        ).all()

        for sub in subs:
            send_expiry_reminder.delay(sub.id)
            sub.status = "expiring"
        db.commit()


@shared_task(name="expire_subscriptions")
def expire_subscriptions():
    """每小时执行：处理到期和宽限期"""
    with get_db_sync() as db:
        now = datetime.utcnow()

        # active/expiring → grace
        for sub in db.query(Subscription).filter(
            Subscription.status.in_(["active", "expiring"]),
            Subscription.expires_at <= now,
        ).all():
            sub.status = "grace"
            sub.grace_ends_at = now + timedelta(days=3)

        # grace → expired
        for sub in db.query(Subscription).filter(
            Subscription.status == "grace",
            Subscription.grace_ends_at <= now,
        ).all():
            sub.status = "expired"
            remove_channel_access.delay(sub.user_id, sub.plan_id)

        db.commit()


@shared_task(name="remove_channel_access")
def remove_channel_access(user_id: int, plan_id: str):
    import asyncio, json
    with get_db_sync() as db:
        plan = db.get(Plan, plan_id)
        user = db.get(User, user_id)
        channels = json.loads(plan.channels)

    async def _kick():
        for channel_id in channels:
            try:
                await bot.ban_chat_member(int(channel_id), user.telegram_id)
                await asyncio.sleep(0.5)
                await bot.unban_chat_member(int(channel_id), user.telegram_id)
            except Exception:
                pass

    asyncio.run(_kick())
```

---

## 3. Bot 初始化配置

```python
# app/main.py

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, MessageHandler, ChatJoinRequestHandler,
    filters
)

async def setup_bot(app: Application):
    # 设置 Menu Button（底部固定入口）
    await app.bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="订阅中心",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    )

    # 注册处理器
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
```

---

## 4. 环境配置

```env
# .env.example

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_SECRET=random_secret_string
TELEGRAM_WEBHOOK_URL=https://api.your-domain.com/webhooks/telegram

# Mini App
MINI_APP_URL=https://your-mini-app.vercel.app

# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/tg_sub
REDIS_URL=redis://localhost:6379/0

# 业务配置
GRACE_PERIOD_DAYS=3
EXPIRY_REMINDER_DAYS=3
ADMIN_TELEGRAM_IDS=123456789
```

---

## 5. Docker Compose 部署

```yaml
version: '3.9'
services:
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [db, redis]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  worker:
    build: .
    env_file: .env
    depends_on: [db, redis]
    command: celery -A app.tasks.celery_app worker -l info

  beat:
    build: .
    env_file: .env
    depends_on: [redis]
    command: celery -A app.tasks.celery_app beat -l info

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: tg_sub
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine

volumes:
  pgdata:
```

---

## 6. 依赖清单

```txt
# requirements.txt
python-telegram-bot==21.6
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.2
redis[hiredis]==5.1.0
celery[redis]==5.4.0
pydantic-settings==2.5.2
httpx==0.27.2
```

---

## 7. 开发阶段规划

| Sprint | 周期 | 交付内容 |
|--------|------|----------|
| Sprint 1 | 1 周 | Bot 基础命令 + Stars 月付 + Join Request 权限验证 |
| Sprint 2 | 1 周 | Stars 自动续费处理 + 宽限期 + 到期踢人 |
| Sprint 3 | 1-2 周 | Mini App 套餐页 + 状态页（React + TG UI） |
| Sprint 4 | 1 周 | Mini App 账单页 + 后端 initData 验证接口 |
| Sprint 5 | 按需 | 管理后台（统计/手动处理）+ 推荐返佣 |
