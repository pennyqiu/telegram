# 运营中心 · 使用说明

> 这里集中存放保险业务的所有运营资料：战略文档、各渠道成稿、转换工具、客户分发材料。

## 📁 目录结构

```
operations/
├── index.html                    ← 运营中心 Dashboard（浏览器打开看）
├── README.md                     ← 本文件
│
├── strategy/                     战略文档
│   ├── 战略手册.md                完整版（57KB · 最重要）
│   ├── 公众号6个月内容矩阵.md
│   ├── 知乎6个月日历.md
│   ├── 知乎发布SOP.md
│   └── 朋友圈长线运营矩阵.md
│
├── published/                    已生成的成稿（按渠道分类）
│   ├── wechat/   公众号 HTML + MD
│   ├── zhihu/    知乎 MD
│   ├── xhs/      小红书 MD
│   └── pyq/      朋友圈（待生成）
│
├── tools/                        转换工具
│   ├── convert_single.py         单篇文章 HTML → 公众号 + 知乎双格式
│   ├── convert_v2.py             双版本文章（A+B 同主题）的转换器
│   └── README.md                 工具详细说明
│
├── assets/                       客户分发资源
│   ├── 港险投保30问.pdf            打印版
│   ├── 港险投保30问_网页版.pdf       网页版
│   ├── 港险投保30问.md             原稿
│   └── 互联网中层家庭财务自查表.xlsx
│
└── reference/                    早期素材稿
    └── 人设奠基长文.md
```

## 🚀 快速开始

### 想发一篇文章到公众号 / 知乎？

1. 打开 `insurance-guide/articles/` 选一篇喜欢的文章 HTML
2. 在**项目根目录**运行：
   ```bash
   python insurance-guide/operations/tools/convert_single.py "insurance-guide/articles/cpa-02-fulfillment-ratio.html" "港险分红实现率"
   ```
3. 项目根目录会生成 `公众号_港险分红实现率.html` 和 `知乎_港险分红实现率.md`
4. 把它们移入 `operations/published/wechat/` 和 `operations/published/zhihu/`
5. **公众号**：浏览器双击 HTML → Ctrl+A → Ctrl+C → 粘贴到公众号编辑器（样式全保留）
6. **知乎**：直接打开 MD，复制内容粘贴到知乎"写文章"

### 想看运营战略？

直接打开 `strategy/战略手册.md` —— 这是最完整的核心文档。

### 想给客户发资料？

去 `assets/` 拿 PDF 和 Excel，直接发即可。

## 📊 内容数量统计

| 类型 | 数量 | 路径 |
|------|------|------|
| 战略文档 | 5 | `strategy/` |
| 公众号成稿 | 3+ | `published/wechat/` |
| 知乎成稿 | 2+ | `published/zhihu/` |
| 小红书成稿 | 2 包 | `published/xhs/` |
| 客户分发资料 | 4 | `assets/` |
| 转换工具 | 2 | `tools/` |

## 🔗 关联资源

- **保险综合站首页**：[../index.html](../index.html)
- **保险全指南**：[../guide.html](../guide.html)
- **专业文章库**：[../articles/v22-xhs-hub.html](../articles/v22-xhs-hub.html)（103 篇）
- **公众号文章模板库**：[../wechat-copy/](../wechat-copy/)（30 篇旧素材）
- **小红书模板库**：[../xhs-copy/](../xhs-copy/)（12 篇旧素材）
- **知乎模板库**：[../zhihu-md/](../zhihu-md/)（11 篇旧素材）
