# 订阅方案设计

## 1. 订阅套餐模型

### 1.1 套餐分层

```
┌───────────────────────────────────────────────────────┐
│                   套餐层级设计                          │
│                                                       │
│  ┌─────────┐   ┌─────────┐   ┌─────────────────────┐ │
│  │  Free   │   │  Basic  │   │       Pro           │ │
│  │  免费版  │   │  基础版  │   │      专业版          │ │
│  │  0 Stars│   │ 250 XTR │   │     550 XTR/月       │ │
│  └─────────┘   └─────────┘   └─────────────────────┘ │
│       ↑              ↑                  ↑              │
│    无需付款        核心功能          全功能 + 优先支持   │
└───────────────────────────────────────────────────────┘
```

### 1.2 套餐详细定义

| 字段 | 说明 | 示例 |
|------|------|------|
| plan_id | 套餐唯一标识 | `plan_pro_monthly` |
| name | 套餐名称 | 专业版月付 |
| stars_price | Stars 价格 | 550 |
| billing_cycle | 计费周期 | monthly（Stars 原生仅支持月付） |
| trial_days | 试用天数（0 = 无试用） | 7 |
| features | 权限/功能列表（JSON） | `["channel_A", "channel_B"]` |
| is_active | 是否在售 | true |

### 1.3 Stars 定价参考

| 套餐 | Stars 价格 | 约等于 USD | 约等于 CNY |
|------|-----------|-----------|-----------|
| Basic 月付 | 250 XTR | ~$5 | ~¥36 |
| Pro 月付 | 550 XTR | ~$11 | ~¥79 |
| Pro 季付（3 × 月付发票） | 1400 XTR | ~$28 | ~¥200 |

> Stars 自动续费目前仅支持月付周期（`subscription_period=2592000`）。季付/年付采用一次性 Invoice 实现。

---

## 2. 订阅生命周期

```
  创建
   │
   ▼
┌──────────┐   Stars 支付成功   ┌──────────┐
│ PENDING  │ ────────────────► │  ACTIVE  │
│  待支付   │                   │  有效中   │
└──────────┘                   └─────┬────┘
                                     │
                    ┌────────────────┼──────────────────┐
                    │                │                  │
                    ▼                ▼                  ▼
              ┌──────────┐    ┌────────────┐    ┌────────────┐
              │ EXPIRING │    │  PAUSED    │    │ CANCELLED  │
              │  即将到期  │    │  已暂停    │    │  已取消    │
              └────┬─────┘    └────────────┘    └────────────┘
                   │
         续费成功  │  未续费（关闭自动续费）
                   │
          ┌────────┴────────┐
          ▼                 ▼
    ┌──────────┐      ┌──────────┐
    │  ACTIVE  │      │  GRACE   │  ← 宽限期（3天）
    │ 续期激活  │      │  宽限中   │
    └──────────┘      └────┬─────┘
                           │ 宽限期结束未续费
                           ▼
                     ┌──────────┐
                     │ EXPIRED  │
                     │  已过期   │  → 自动移出频道
                     └──────────┘
```

### 状态说明

| 状态 | 含义 | 用户权限 |
|------|------|----------|
| PENDING | 订单创建，等待支付 | 无 |
| ACTIVE | 订阅有效 | 完整权限 |
| EXPIRING | 3 天内到期 | 完整权限 + 收到提醒 |
| GRACE | 已到期，宽限 3 天 | 完整权限（最后机会） |
| PAUSED | 用户主动暂停 | 无 |
| CANCELLED | 用户取消，到期前仍有效 | 完整权限直到到期 |
| EXPIRED | 彻底过期 | 无，已移出频道 |

---

## 3. 订阅规则

### 3.1 升级/降级规则

| 场景 | 处理方式 |
|------|----------|
| 升档（Basic → Pro） | 立即生效，发送差价 Invoice（Stars） |
| 降档（Pro → Basic） | 当期结束后生效 |
| 取消自动续费 | 在 Telegram 设置中操作，当期结束停止 |

### 3.2 试用期规则

- 每个用户每个套餐只能试用一次
- 试用期内无需支付，到期后发送订阅引导
- 试用期不计入历史订阅时长

### 3.3 退款规则

Stars 退款通过 Telegram 平台申诉处理，Bot 侧规则如下：

| 场景 | 策略 |
|------|------|
| 付费 24h 内申请 | 协助引导至 Telegram 官方退款 |
| 付费 24h 后申请 | 不退款，当期结束停止服务 |
| 平台异常无法使用 | 按比例补偿（延长订阅时长） |

---

## 4. 权限管控机制

### 4.1 频道/群组权限配置

```json
{
  "channels": ["@channel_A", "@channel_B"],
  "groups": ["-1001234567890"],
  "bot_features": ["ai_chat", "file_export"]
}
```

### 4.2 权限验证：Join Request 方案

频道设置为"需申请加入"，付费验证流程：

```
用户点击「申请加入」付费频道
  └── Bot 收到 chatJoinRequest 事件
        ├── 有效订阅 → approve（自动通过）
        └── 无订阅  → decline + 私聊发送 Mini App 订阅引导
```

```python
async def handle_join_request(update: Update, context):
    request = update.chat_join_request
    has_sub = await subscription_service.has_active_subscription(
        request.from_user.id
    )
    if has_sub:
        await context.bot.approve_chat_join_request(
            request.chat.id, request.from_user.id
        )
    else:
        await context.bot.decline_chat_join_request(
            request.chat.id, request.from_user.id
        )
        await context.bot.send_message(
            request.from_user.id,
            "需要订阅后才能访问该频道。",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "查看订阅套餐",
                    web_app=WebAppInfo(url=MINI_APP_URL)
                )
            ]])
        )
```

### 4.3 到期移出机制

```python
async def remove_expired_member(user_id: int, channel_id: int):
    await bot.ban_chat_member(channel_id, user_id)
    await asyncio.sleep(1)
    await bot.unban_chat_member(channel_id, user_id)  # 解封，允许重新订阅后加入
```

---

## 5. 用户体验设计

### 5.1 Bot 命令列表

| 命令 | 说明 |
|------|------|
| `/start` | 欢迎页，打开 Mini App 入口 |
| `/status` | 查看当前订阅状态和到期时间 |
| `/cancel` | 引导取消自动续费（跳转 Telegram 设置） |
| `/help` | 帮助信息 |

> 套餐选择、续费、账单等操作统一在 Mini App 内完成，不再依赖命令。

### 5.2 Mini App 套餐展示（示例）

```
╔═══════════════════════════════╗
║       选择您的订阅套餐         ║
╠═══════════════════════════════╣
║  📦 Basic 基础版               ║
║  250 Stars / 月                ║
║  ✅ 访问付费频道 A              ║
║  ✅ 每日更新内容                ║
║  [ 7天免费试用 → 订阅 ]        ║
╠═══════════════════════════════╣
║  💎 Pro 专业版  ⭐ 推荐         ║
║  550 Stars / 月                ║
║  ✅ 访问全部付费频道            ║
║  ✅ 独家内容 + 历史存档         ║
║  ✅ AI 助手功能                 ║
║  [ 7天免费试用 → 订阅 ]        ║
╚═══════════════════════════════╝
```

### 5.3 续费提醒消息（示例）

```
⏰ 订阅即将到期

您的 Pro 专业版 将于 3 天后到期。

Telegram 自动续费已开启，到期后将自动扣除
550 Stars 完成续期。

如需取消，请前往 Telegram 设置 → 订阅。

[📋 打开订阅中心]
```
