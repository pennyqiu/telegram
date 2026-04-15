# Telegram 多系统仓库

> **🗺️ 项目导航**：本仓库包含 4 个独立系统，请查看 **[PROJECTS.md](PROJECTS.md)** 了解全貌和使用指南。

| 系统 | 描述 | 快速链接 |
|------|------|----------|
| **Telegram 订阅系统** | Stars 原生订阅 + Mini App | [详情](#telegram-订阅与周期付费系统) / [目录](tg-subscription/) |
| **Telegram 俱乐部系统** | 足球队管理系统 | [目录](tg-club/) |
| **保险指南系统** | 保险知识与决策工具 | [详情](insurance-guide/) |
| **投资工具集** | 股票估值、追踪等工具 | [详情](INVESTMENT_TOOLS.md) |

---

# Telegram 订阅与周期付费系统

> 基于 Telegram Mini App + Stars 原生订阅的全闭环付费解决方案，用户全程不离开 Telegram App。

## 项目概览

本项目为 Telegram 生态提供一套完整的**订阅制服务 + 周期付费**解决方案，支持内容频道、工具服务、社群访问等场景。

### 核心能力

| 能力 | 描述 |
|------|------|
| 原生订阅 | Telegram Stars 月付，平台自动续费，用户无感 |
| Mini App | 内嵌订阅中心，套餐选择/状态查看/账单，无需跳出 App |
| 权限控制 | Join Request 机制，付费后自动放行，到期自动移出 |
| 到期管理 | 到期提醒、宽限期、自动踢出全流程自动化 |
| 数据统计 | Stars 收入、订阅数、流失率等核心指标 |

---

## 文档目录

```
docs/
├── 01-architecture.md        # 整体方案架构与用户旅程
├── 02-subscription.md        # 订阅套餐与生命周期设计
├── 03-database-schema.md     # 数据库 Schema 设计
├── 04-implementation.md      # 代码实现方案
├── 05-club-player-system.md  # 俱乐部与球员推荐系统设计
└── 06-deployment-runbook.md  # 生产部署手册（含 VPS 购买、域名、初始化、冒烟测试）
```

---

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| Bot 框架 | `python-telegram-bot` v21 | 异步，支持所有最新 API |
| Mini App 前端 | React + Vite + `@telegram-apps/telegram-ui` | 官方组件库，主题无缝融合 |
| 后端服务 | FastAPI（异步） | 轻量 API，Webhook 处理 |
| 数据库 | PostgreSQL + Redis | 持久化 + 订阅状态缓存 |
| 定时任务 | Celery + Redis Beat | 到期提醒、移出频道 |
| 支付通道 | **Telegram Stars**（唯一，原生） | 无需第三方支付，无需跳出 App |
| Mini App 部署 | Vercel / Cloudflare Pages | 免费，全球 CDN |

---

## 核心流程

```
用户打开 Bot
    ↓
点击底部「订阅中心」按钮（Menu Button）
    ↓
Telegram 内打开 Mini App
    ↓
选择套餐 → 点击订阅
    ↓
弹出 Stars 原生支付确认框（一键，无需填卡）
    ↓
支付成功 → 订阅激活
    ↓
申请加入付费频道 → Bot 自动审核通过
    ↓
Telegram 每月自动续费（subscription_period）
    ↓
到期前 Bot 发提醒 / 到期后自动移出频道
```

---

*最后更新：2026-03-30*
