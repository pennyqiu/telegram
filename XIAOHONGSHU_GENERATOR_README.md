# 小红书风格图片生成器 使用说明

## 📋 功能简介

这个Python脚本可以自动生成类似小红书的网格编号图片，支持自定义高亮、标题、副标题等。

## 🎨 效果展示

生成的图片包含：
- ✅ 39个网格方块（13列 x 3行）
- ✅ 粉色高亮效果
- ✅ 圆角卡片设计
- ✅ 自定义标题和副标题
- ✅ 右上角链接文字

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install Pillow
```

### 2. 基础用法

```python
from xiaohongshu_generator import XiaohongshuGenerator

# 创建生成器实例
generator = XiaohongshuGenerator()

# 生成图片（高亮第1个）
generator.generate(
    highlight_items=[1],
    title="小红书 39 篇",
    subtitle="一研客副发布信（每篇 1000 字内）",
    output_path="output.png"
)
```

### 3. 运行示例

```bash
python xiaohongshu_generator.py
```

这将生成3个示例图片：
- `xiaohongshu_01.png` - 高亮第1个
- `xiaohongshu_multiple.png` - 高亮多个（1, 5, 10, 15, 20）
- `xiaohongshu_custom.png` - 自定义标题

## 🎯 进阶用法

### 高亮多个项目

```python
generator.generate(
    highlight_items=[1, 5, 10, 15, 20, 25, 30],
    title="小红书 39 篇",
    subtitle="已完成 7 篇",
    output_path="progress.png"
)
```

### 自定义颜色和尺寸

```python
# 创建生成器
generator = XiaohongshuGenerator()

# 修改配置
generator.highlight_color = '#FF69B4'  # 修改高亮颜色
generator.card_width = 100            # 修改卡片宽度
generator.card_height = 100           # 修改卡片高度

# 生成图片
generator.generate(
    highlight_items=[1, 2, 3],
    output_path="custom_style.png"
)
```

### 显示不同进度

```python
# 本周进度
generator.generate(
    highlight_items=[1, 2, 3, 4, 5],
    title="小红书内容计划",
    subtitle="本周完成：5/39",
    output_path="weekly_progress.png"
)

# 月度进度
generator.generate(
    highlight_items=list(range(1, 16)),  # 1-15
    title="小红书内容计划",
    subtitle="本月完成：15/39",
    output_path="monthly_progress.png"
)
```

## 📊 参数说明

### `generate()` 方法参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `highlight_items` | list[int] | `[1]` | 要高亮的编号列表（1-39） |
| `title` | str | `"小红书 39 篇"` | 标题文字 |
| `subtitle` | str | `"一研客副发布信..."` | 副标题文字 |
| `output_path` | str | `"xiaohongshu_grid.png"` | 输出文件路径 |

### 可自定义的属性

```python
# 画布尺寸
generator.width = 1400
generator.height = 600

# 颜色配置
generator.bg_color = '#FEFEFE'        # 背景色
generator.card_color = '#FFFFFF'      # 卡片背景色
generator.card_border = '#E8E8E8'     # 卡片边框
generator.highlight_color = '#FF3A8C' # 粉色高亮
generator.text_color = '#333333'      # 文字颜色

# 网格配置
generator.cols = 13                   # 列数
generator.rows = 3                    # 行数
generator.card_width = 90             # 卡片宽度
generator.card_height = 90            # 卡片高度
generator.gap_x = 15                  # 水平间距
generator.gap_y = 15                  # 垂直间距
```

## 💡 实际应用场景

### 1. 内容创作进度追踪

```python
# 显示当前创作进度
completed = [1, 2, 3, 4, 5, 6, 7]  # 已完成的文章编号
generator.generate(
    highlight_items=completed,
    title="小红书创作计划",
    subtitle=f"已完成 {len(completed)}/39",
    output_path="progress_tracker.png"
)
```

### 2. 内容发布计划

```python
# 本周计划发布
this_week = [8, 9, 10, 11, 12]
generator.generate(
    highlight_items=this_week,
    title="小红书发布计划",
    subtitle="本周计划（第2周）",
    output_path="weekly_plan.png"
)
```

### 3. 选题投票

```python
# 用户投票最多的选题
top_voted = [5, 12, 18, 23, 30]
generator.generate(
    highlight_items=top_voted,
    title="热门选题投票",
    subtitle="最受欢迎的5个选题",
    output_path="voting_result.png"
)
```

## 🔧 集成到Telegram Bot

```python
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from xiaohongshu_generator import XiaohongshuGenerator

async def generate_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """生成进度图片命令"""
    # 获取用户的进度数据（从数据库）
    completed_items = get_user_progress(update.effective_user.id)
    
    # 生成图片
    generator = XiaohongshuGenerator()
    output_path = f"temp_{update.effective_user.id}.png"
    generator.generate(
        highlight_items=completed_items,
        title="我的创作进度",
        subtitle=f"已完成 {len(completed_items)}/39",
        output_path=output_path
    )
    
    # 发送图片
    await update.message.reply_photo(photo=open(output_path, 'rb'))
    
    # 清理临时文件
    os.remove(output_path)

# 注册命令
app.add_handler(CommandHandler("progress", generate_progress))
```

## 🎨 自定义颜色方案

### 不同主题色

```python
# 蓝色主题
generator.highlight_color = '#4A90E2'

# 绿色主题
generator.highlight_color = '#52C41A'

# 紫色主题
generator.highlight_color = '#9C27B0'

# 橙色主题
generator.highlight_color = '#FF9800'
```

## 📝 注意事项

1. **字体支持**：脚本会自动查找Windows系统中的中文字体（微软雅黑、黑体、宋体等）
2. **编号范围**：支持1-39的编号，超出范围会被忽略
3. **输出格式**：默认输出PNG格式，质量为95
4. **文件路径**：支持相对路径和绝对路径

## 🐛 常见问题

### Q: 中文显示乱码？
A: 确保系统中安装了中文字体，脚本会自动尝试多个字体。

### Q: 如何修改网格数量？
A: 修改 `generator.cols`、`generator.rows` 和 `generator.total_items`

### Q: 图片太大/太小？
A: 调整 `generator.width` 和 `generator.height`

### Q: 如何批量生成？
```python
# 批量生成不同进度的图片
for i in range(1, 40):
    generator.generate(
        highlight_items=list(range(1, i+1)),
        title="小红书创作进度",
        subtitle=f"第 {i} 天",
        output_path=f"day_{i:02d}.png"
    )
```

## 📦 依赖版本

- Python >= 3.7
- Pillow >= 8.0.0

## 📄 License

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
