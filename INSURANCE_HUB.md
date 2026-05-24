# 香港保险综合站 · 总览

整个保险业务的内容、知识、运营资料统一入口。

## 🚪 入口

**👉 浏览器打开**：[`insurance-guide/index.html`](insurance-guide/index.html)

这是综合 Dashboard，从这里可以进入：
- 📚 核心知识库（保险全指南 + 103 篇文章 + IRR 工具 + 30 问等）
- ✍️ 内容工厂（公众号、知乎、小红书、朋友圈 4 大渠道成稿）
- 📋 运营战略（6 个月矩阵 + SOP + 战略手册）
- 🛠️ 工具与资源（转换脚本 + PDF / Excel）

## 📂 目录架构

```
项目根目录
│
├── insurance-guide/                  ← 保险综合站根（重点）
│   ├── index.html                    🏠 综合 Dashboard 入口（新）
│   ├── guide.html                    📖 完整版保险全指南（原 index.html）
│   ├── articles/                     📚 103 篇专业文章
│   ├── wechat-copy/                  公众号旧素材库（30 篇）
│   ├── xhs-copy/                     小红书旧素材库（12 篇）
│   ├── zhihu-md/                     知乎旧素材库（11 篇）
│   ├── 30-questions.html             ❓ 港险投保 30 问
│   ├── irr-calculator.html           📊 IRR 计算器
│   ├── needs-assessment.html         🩺 家庭需求评估
│   ├── dividend-rates.html           📈 分红实现率
│   │
│   └── operations/                   📋 运营中心（新）
│       ├── index.html                运营 Dashboard
│       ├── README.md                 使用说明
│       ├── strategy/                 战略文档（6 个文件）
│       ├── published/                成稿仓库（按渠道分类）
│       │   ├── wechat/  zhihu/  xhs/  pyq/
│       ├── assets/                   PDF / Excel 资源
│       ├── tools/                    转换脚本 + 说明
│       └── reference/                早期素材
│
├── 其他项目文件夹（投资分析、Telegram 项目等，不属于保险站）
│   ├── investment_tracker/
│   ├── tg-club/
│   ├── tg-subscription/
│   ├── docs/
│   └── ...
│
└── INSURANCE_HUB.md                  ← 本文件（整站总览）
```

## 📊 内容数量

| 区域 | 数量 |
|------|------|
| 专业文章（articles） | 103 篇 HTML |
| 公众号成稿（published） | 3 篇可发 |
| 公众号旧素材（wechat-copy） | 30 篇 |
| 知乎成稿 | 2 篇可发 |
| 知乎旧素材 | 11 篇 |
| 小红书成稿 | 2 包多条 |
| 小红书旧素材 | 12 篇 |
| 战略文档 | 6 份 |
| 资源文件（PDF/Excel） | 4 个 |
| 转换工具 | 2 个 |

## 🛠️ 日常工作流

### 场景 1：发布一篇新文章

```bash
# 1. 选文章
ls insurance-guide/articles/cpa-*.html

# 2. 转换成公众号 + 知乎双版本
python insurance-guide/operations/tools/convert_single.py \
    "insurance-guide/articles/cpa-02-fulfillment-ratio.html" \
    "港险分红实现率拆解"

# 3. 归档到 published/
mv 公众号_*.html 公众号_*.md insurance-guide/operations/published/wechat/
mv 知乎_*.md insurance-guide/operations/published/zhihu/

# 4. 公众号：浏览器打开 HTML → 全选复制 → 粘贴
# 5. 知乎：编辑器打开 MD → 复制内容 → 粘贴到知乎"写文章"
```

### 场景 2：查看运营战略

直接打开：
- `insurance-guide/operations/strategy/战略手册.md`（最完整）
- `insurance-guide/operations/strategy/公众号6个月内容矩阵.md`
- `insurance-guide/operations/strategy/知乎6个月日历.md`

### 场景 3：给客户发资料

- 港险投保 30 问：`insurance-guide/operations/assets/港险投保30问_网页版.pdf`
- 家庭财务自查表：`insurance-guide/operations/assets/互联网中层家庭财务自查表.xlsx`

## 🎨 入口预览

打开 `insurance-guide/index.html` 后，你会看到：

- 蓝色渐变 Hero 顶部（含统计数字：103+ 文章、4 渠道、50+ 运营资料）
- 4 大模块卡片网格：
  - 📚 核心知识库（6 张卡片，主推「保险全指南」是大卡片）
  - ✍️ 内容工厂（4 张渠道卡片）
  - 📋 运营战略（4 张战略卡片）
  - 🛠️ 工具与资源（3 张卡片）
- 底部 Footer 含快速导航链接

点击「✍️ 内容工厂 → 运营中心」会跳到紫色调的 `operations/index.html`，里面有更细的成稿列表和工作流说明。

## 🔄 维护建议

- **新增文章**：在 `articles/` 加新 HTML，回到 dashboard 不用改（文章库统一从 `v22-xhs-hub.html` 入口）
- **新增公众号/知乎成稿**：放到 `operations/published/{渠道}/`，命名格式 `公众号_<主题>.html` 或 `知乎_<主题>.md`
- **新增战略文档**：放到 `operations/strategy/`，会自动出现在运营中心的"战略地图"区
- **改样式**：编辑 `operations/tools/convert_single.py` 顶部的 `WECHAT_CSS`
- **改 Dashboard 布局**：编辑 `insurance-guide/index.html`（或 `operations/index.html`）

## 📝 历史变更

- **v3.0** (2026-05) — 综合站架构完成，新增 Dashboard 入口 + 运营中心
- v2.2 — 文章库扩充到 103 篇
- v1.0 — 单页指南（现归档为 `guide.html`）
