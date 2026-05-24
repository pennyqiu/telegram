# 转换工具使用说明

把 `insurance-guide/articles/` 下的 HTML 文章，一键转换成：
- **公众号 HTML**（带蓝色样式，浏览器打开后复制粘贴到公众号编辑器，格式全保留）
- **知乎 Markdown**（原生格式，知乎编辑器直接支持粘贴）

## 🚀 快速使用

### convert_single.py · 单篇通用版（推荐）

适用于 `insurance-guide/articles/` 下任意单篇 HTML 文章。

**用法**：

```bash
python insurance-guide/operations/tools/convert_single.py <源HTML路径> <输出文件主名>
```

**示例**：

```bash
# 转换分红险智商税那篇
python insurance-guide/operations/tools/convert_single.py "insurance-guide/articles/cpa-01-dividend-trap.html" "港险分红险智商税CPA拆解"

# 转换分红实现率那篇
python insurance-guide/operations/tools/convert_single.py "insurance-guide/articles/cpa-02-fulfillment-ratio.html" "港险分红实现率拆解"

# 转换美元 vs 人民币
python insurance-guide/operations/tools/convert_single.py "insurance-guide/articles/cpa-03-usd-vs-rmb.html" "美元保单vs人民币保单"
```

**输出**（生成在**项目根目录**）：
- `公众号_<主名>.html`
- `知乎_<主名>.md`

**建议工作流**：生成后，把这两个文件移入 `operations/published/wechat/` 和 `operations/published/zhihu/` 归档。

### convert_v2.py · 双版本专用版

适用于源 HTML 里同时包含【A】公众号版 + 【B】知乎版的文章（如 `v22-persona.html`）。

```bash
python insurance-guide/operations/tools/convert_v2.py
```

（这个脚本目前是硬编码处理 `v22-persona.html`，如需扩展可参考它的逻辑）

## 🎨 公众号 HTML 样式说明

生成的 HTML 包含以下样式块（在公众号编辑器粘贴后会保留）：

| 元素 | 样式 |
|------|------|
| h1 主标题 | 居中 + 蓝色下边框 |
| h2 章节 | 蓝色左侧竖条 + 主色调 |
| h3 小节 | 深蓝粗体 |
| **加粗** | 自动标蓝（视觉重点） |
| > 引用块 | 浅灰背景 + 蓝左边框 |
| 表格 | 蓝表头 + 斑马纹 |
| 列表 | 标准缩进 |
| 分割线 | 虚线柔和样式 |
| ⚠️ 警告块 | 黄色 callout |
| 💡 关键洞察 | 蓝色 callout |
| 公式块 | 等宽字体 + 虚线框 |

## 📋 复制粘贴流程

### 公众号
1. 浏览器双击 `公众号_*.html`
2. 页面上 `Ctrl + A` 全选
3. `Ctrl + C` 复制
4. 打开 [mp.weixin.qq.com](https://mp.weixin.qq.com) → 新建图文
5. 编辑器里 `Ctrl + V` 粘贴 → 所有样式保留 ✅

### 知乎
1. 用编辑器（Cursor / VSCode）打开 `知乎_*.md`
2. `Ctrl + A` 全选 → `Ctrl + C` 复制
3. 打开知乎 → 写文章 → 直接 `Ctrl + V` 粘贴
4. 知乎会自动识别 Markdown 语法 → 标题、加粗、列表、引用、表格全部正确转换 ✅

## ⚠️ 常见问题

**Q: 公众号粘贴后字体变了？**  
A: 公众号会用自己默认字体覆盖，这是正常的。**加粗、标题、引用块、列表**等结构性样式都会保留，颜色、对齐方式也保留。

**Q: 表格在公众号显示不全？**  
A: 公众号编辑器对表格宽度有限制，如果列数太多可能需要手动调整。建议把宽表格拆成"上下两段"或转成图片。

**Q: 知乎粘贴后没识别 Markdown？**  
A: 确认是在"写文章"（不是"写回答"），知乎专栏文章对 Markdown 支持更完整。

**Q: 我想自己改样式？**  
A: 编辑 `convert_single.py` 顶部的 `WECHAT_CSS` 变量，那是公众号 HTML 用的所有 CSS。

## 🔄 批量转换示例

如果你想一次转换多篇：

```bash
# Bash / Git Bash
for f in insurance-guide/articles/cpa-*.html; do
    name=$(basename "$f" .html)
    python insurance-guide/operations/tools/convert_single.py "$f" "$name"
done
```

```powershell
# PowerShell
Get-ChildItem insurance-guide/articles/cpa-*.html | ForEach-Object {
    $name = $_.BaseName
    python insurance-guide/operations/tools/convert_single.py $_.FullName $name
}
```
