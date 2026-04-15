# 项目地图 | Project Map

> **🎯 使用指南：改 X 只读 Y 目录** - 按需加载，避免上下文噪音

## 四大模块概览

| 项目 | 路径 | 技术栈 | 部署方式 | 入口文件 | 相关目录 |
|------|------|--------|----------|----------|----------|
| **Telegram 订阅系统** | `tg-subscription/` | FastAPI + Bot + Celery + React | 独立部署（VPS + Vercel） | `app/main.py` + `mini-app/src/main.tsx` | 仅此目录 + `docs/` |
| **Telegram 俱乐部系统** | `tg-club/` | FastAPI + React Admin + Mini App | 独立部署，调用订阅系统API | `backend/app/main.py` | 仅此目录，依赖订阅系统 |
| **保险指南站** | `insurance-guide/` | 静态HTML + FastAPI简报 + 爬虫 | 静态部署 + VPS脚本 | `public/index.html` + `fastapi_app/main.py` | 仅此目录 |
| **投资工具集** | 根目录散布 | 静态HTML + Python脚本 | 纯本地/静态 | 见下方列表 | 根目录 `*.html` + `investment_tracker/` |

## 投资模块文件清单
```
investment_tracker/          # Python 追踪脚本
stock-valuation-calculator.html    # 估值计算器
investment-tracker.html           # 投资追踪表
damodaran_analysis.html          # 达摩达兰分析
value_investing_*.html           # 价值投资系列
us-stock-learning.html           # 美股学习
static/stock-learning.html      # 静态版本
```

## 🚀 快速开始指南

### 改订阅系统 → 只关注
```bash
cd tg-subscription/
# 忽略其他三个模块
```

### 改俱乐部系统 → 需要订阅系统API
```bash 
cd tg-club/
# 同时参考 docs/ 中的API对接文档
```

### 改保险内容 → 独立操作
```bash
cd insurance-guide/
# 完全独立，无依赖
```

### 改投资工具 → 根目录 + investment_tracker/
```bash
# 主要是 HTML 文件，直接浏览器打开测试
```

---

## 🤖 **自动化工具**

**上下文切换系统** - 告别手动改 `.cursorignore`：
- 📖 **使用指南**：[CONTEXT_AUTOMATION.md](CONTEXT_AUTOMATION.md)
- ⚡ **快速切换**：`python3 context_switch.py <模式>`
- 🎯 **Cursor集成**：`Cmd+Shift+P` → "Tasks: Run Task" → 选择模式

**📝 维护说明**：
- 各模块有独立的 requirements.txt / package.json
- 部署文档在 `docs/06-deployment-runbook.md`（仅 tg-* 系统）
- 保险和投资模块的具体使用见各自目录的 README.md