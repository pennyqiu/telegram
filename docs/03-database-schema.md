# 数据库 Schema 设计

## 1. 实体关系图（ERD）

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────┐
│    users    │       │  subscriptions   │       │    plans    │
│─────────────│       │──────────────────│       │─────────────│
│ id (PK)     │◄──1:N─│ user_id (FK)     │──N:1─►│ id (PK)     │
│ telegram_id │       │ plan_id (FK)     │       │ name        │
│ username    │       │ status           │       │ stars_price │
│ first_name  │       │ started_at       │       │ billing_    │
│ last_name   │       │ expires_at       │       │   cycle     │
│ language    │       │ trial_ends_at    │       │ features    │
│ created_at  │       │ cancelled_at     │       │ channels    │
│ updated_at  │       │ tg_charge_id     │       │ trial_days  │
└─────────────┘       │ created_at       │       │ is_active   │
                      └────────┬─────────┘       │ created_at  │
                               │ 1:N             └─────────────┘
                               ▼
                      ┌──────────────────┐
                      │    payments      │
                      │──────────────────│
                      │ id (PK)          │
                      │ subscription_id  │
                      │ user_id (FK)     │
                      │ stars_amount     │
                      │ tg_charge_id     │
                      │ is_recurring     │
                      │ status           │
                      │ paid_at          │
                      │ created_at       │
                      └──────────────────┘
```

---

## 2. 完整 DDL

### 2.1 用户表 `users`

```sql
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT NOT NULL UNIQUE,
    username        VARCHAR(64),
    first_name      VARCHAR(128) NOT NULL,
    last_name       VARCHAR(128),
    language_code   VARCHAR(8) DEFAULT 'zh',
    is_blocked      BOOLEAN DEFAULT FALSE,
    referred_by     BIGINT REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
```

### 2.2 套餐表 `plans`

```sql
CREATE TABLE plans (
    id              VARCHAR(64) PRIMARY KEY,           -- e.g. 'plan_pro_monthly'
    name            VARCHAR(128) NOT NULL,
    description     TEXT,
    stars_price     INTEGER NOT NULL,                  -- Telegram Stars 数量
    billing_cycle   VARCHAR(16) NOT NULL,              -- monthly / one_time
    trial_days      INTEGER NOT NULL DEFAULT 0,
    features        JSONB NOT NULL DEFAULT '[]',       -- 功能权限列表
    channels        JSONB NOT NULL DEFAULT '[]',       -- 可访问的频道/群组 ID 列表
    sort_order      INTEGER DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 示例数据
INSERT INTO plans VALUES (
    'plan_basic_monthly', 'Basic 基础版月付', '每月自动续费',
    250, 'monthly', 7,
    '["channel_a", "daily_update"]',
    '["-1001234567890"]',
    1, TRUE, NOW(), NOW()
);

INSERT INTO plans VALUES (
    'plan_pro_monthly', 'Pro 专业版月付', '全功能，每月自动续费',
    550, 'monthly', 7,
    '["channel_a", "channel_b", "ai_chat", "archive"]',
    '["-1001234567890", "-1009876543210"]',
    2, TRUE, NOW(), NOW()
);
```

### 2.3 订阅表 `subscriptions`

```sql
CREATE TYPE subscription_status AS ENUM (
    'pending',    -- 待支付
    'trialing',   -- 试用中
    'active',     -- 有效
    'expiring',   -- 即将到期（3天内）
    'grace',      -- 宽限期
    'paused',     -- 暂停
    'cancelled',  -- 已取消（到期前仍有效）
    'expired'     -- 已过期
);

CREATE TABLE subscriptions (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id),
    plan_id             VARCHAR(64) NOT NULL REFERENCES plans(id),
    status              subscription_status NOT NULL DEFAULT 'pending',

    started_at          TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,
    trial_ends_at       TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    grace_ends_at       TIMESTAMPTZ,

    -- 升降档记录
    previous_plan_id    VARCHAR(64) REFERENCES plans(id),
    upgraded_from_id    BIGINT REFERENCES subscriptions(id),

    -- Telegram 支付凭证
    tg_charge_id        VARCHAR(128),                  -- successful_payment 中的 charge_id

    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sub_user_id ON subscriptions(user_id);
CREATE INDEX idx_sub_status ON subscriptions(status);
CREATE INDEX idx_sub_expires_at ON subscriptions(expires_at);
```

### 2.4 支付记录表 `payments`

```sql
CREATE TYPE payment_status AS ENUM (
    'pending',
    'paid',
    'failed',
    'refunded'
);

CREATE TABLE payments (
    id                  BIGSERIAL PRIMARY KEY,
    subscription_id     BIGINT NOT NULL REFERENCES subscriptions(id),
    user_id             BIGINT NOT NULL REFERENCES users(id),

    stars_amount        INTEGER NOT NULL,              -- Stars 数量
    tg_charge_id        VARCHAR(256) UNIQUE NOT NULL,  -- Telegram charge ID（幂等键）
    is_recurring        BOOLEAN DEFAULT FALSE,         -- 是否为自动续费

    status              payment_status NOT NULL DEFAULT 'pending',

    paid_at             TIMESTAMPTZ,
    refunded_at         TIMESTAMPTZ,

    billing_period_start TIMESTAMPTZ,
    billing_period_end   TIMESTAMPTZ,

    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_payments_user_id ON payments(user_id);
CREATE INDEX idx_payments_sub_id ON payments(subscription_id);
CREATE INDEX idx_payments_charge_id ON payments(tg_charge_id);
```

### 2.5 通知记录表 `notifications`

```sql
CREATE TYPE notification_type AS ENUM (
    'subscription_activated',
    'subscription_expiring',
    'subscription_expired',
    'payment_success',
    'renewal_reminder'
);

CREATE TABLE notifications (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    type            notification_type NOT NULL,
    subscription_id BIGINT REFERENCES subscriptions(id),
    message         TEXT,
    is_sent         BOOLEAN DEFAULT FALSE,
    sent_at         TIMESTAMPTZ,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notif_user_id ON notifications(user_id);
CREATE INDEX idx_notif_pending ON notifications(is_sent) WHERE is_sent = FALSE;
```

### 2.6 操作审计表 `audit_logs`

```sql
CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id),
    action      VARCHAR(64) NOT NULL,          -- e.g. 'subscription.activated'
    entity_type VARCHAR(32),
    entity_id   BIGINT,
    old_value   JSONB,
    new_value   JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at);
```

---

## 3. 关键查询示例

### 查询用户当前有效订阅

```sql
SELECT s.*, p.name AS plan_name, p.features, p.channels
FROM subscriptions s
JOIN plans p ON s.plan_id = p.id
WHERE s.user_id = $1
  AND s.status IN ('active', 'expiring', 'trialing', 'grace', 'cancelled')
  AND s.expires_at > NOW()
ORDER BY s.expires_at DESC
LIMIT 1;
```

### 查询需要发送到期提醒的订阅

```sql
SELECT s.*, u.telegram_id, u.first_name, p.name AS plan_name
FROM subscriptions s
JOIN users u ON s.user_id = u.id
JOIN plans p ON s.plan_id = p.id
WHERE s.status = 'active'
  AND s.expires_at BETWEEN NOW() AND NOW() + INTERVAL '3 days'
  AND NOT EXISTS (
    SELECT 1 FROM notifications n
    WHERE n.subscription_id = s.id
      AND n.type = 'subscription_expiring'
      AND n.created_at > NOW() - INTERVAL '1 day'
  );
```

### 统计 Stars 月收入

```sql
SELECT
    DATE_TRUNC('month', paid_at) AS month,
    SUM(stars_amount)            AS total_stars,
    COUNT(DISTINCT user_id)      AS paying_users
FROM payments
WHERE status = 'paid'
GROUP BY 1
ORDER BY 1 DESC
LIMIT 12;
```

---

## 4. Redis 数据结构

| Key 模式 | 类型 | TTL | 用途 |
|----------|------|-----|------|
| `user:mini_app_session:{telegram_id}` | Hash | 1h | Mini App initData 验证缓存 |
| `payment:processed:{charge_id}` | String | 30d | 支付幂等，防重复处理 |
| `sub:active:{telegram_id}` | String | 5min | 订阅状态缓存（Join Request 快速验权） |
| `rate_limit:{telegram_id}` | Counter | 1min | 请求频率限制 |
