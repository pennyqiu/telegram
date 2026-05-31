# 小红书网格图片生成器 - 快速开始

## 🎯 已生成文件

1. **xiaohongshu_generator.py** - 核心生成器类
2. **xiaohongshu_cli.py** - 命令行工具
3. **XIAOHONGSHU_GENERATOR_README.md** - 详细使用文档

## 🚀 快速使用

### 方法一：运行示例脚本（最快）

```bash
python xiaohongshu_generator.py
```

这将生成3个示例图片：
- xiaohongshu_01.png
- xiaohongshu_multiple.png
- xiaohongshu_custom.png

### 方法二：使用命令行工具（最灵活）

```bash
# 基础用法
python xiaohongshu_cli.py -o 我的图片.png

# 高亮1-10
python xiaohongshu_cli.py -i "1-10" -o output.png

# 高亮指定项
python xiaohongshu_cli.py -i "1,5,10,15,20" -o output.png

# 自定义标题
python xiaohongshu_cli.py -i "1-5" -t "我的进度" -s "本周: 5/39" -o progress.png

# 修改颜色
python xiaohongshu_cli.py -i "1,2,3" --color "#FF69B4" -o pink.png
```

### 方法三：在代码中使用（最强大）

```python
from xiaohongshu_generator import XiaohongshuGenerator

# 创建生成器
generator = XiaohongshuGenerator()

# 生成图片
generator.generate(
    highlight_items=[1, 2, 3, 4, 5],
    title="我的创作计划",
    subtitle="本周进度: 5/39",
    output_path="my_progress.png"
)
```

## 📊 命令行参数说明

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| --items | -i | 高亮项目 | "1,5,10" 或 "1-10" |
| --title | -t | 标题 | "我的进度" |
| --subtitle | -s | 副标题 | "本周: 5/39" |
| --output | -o | 输出路径 | "output.png" |
| --color | - | 高亮颜色 | "#FF69B4" |
| --width | - | 图片宽度 | 1400 |
| --height | - | 图片高度 | 600 |

## 💡 常用场景示例

### 1. 显示本周进度

```bash
python xiaohongshu_cli.py -i "1-7" -t "本周创作" -s "完成: 7/39" -o weekly.png
```

### 2. 显示已完成项目

```bash
python xiaohongshu_cli.py -i "1,3,5,7,9,11,13,15" -t "已发布文章" -s "共8篇" -o published.png
```

### 3. 显示计划中项目

```bash
python xiaohongshu_cli.py -i "20-25" -t "下周计划" -s "待创作: 6篇" -o planned.png
```

### 4. 使用不同颜色

```bash
# 蓝色
python xiaohongshu_cli.py -i "1-5" --color "#4A90E2" -o blue.png

# 绿色
python xiaohongshu_cli.py -i "1-5" --color "#52C41A" -o green.png

# 紫色
python xiaohongshu_cli.py -i "1-5" --color "#9C27B0" -o purple.png
```

## 🔧 集成到你的项目

### 集成到Telegram Bot

```python
from xiaohongshu_generator import XiaohongshuGenerator

async def show_progress(update, context):
    # 生成图片
    generator = XiaohongshuGenerator()
    generator.generate(
        highlight_items=[1, 2, 3],
        title="你的进度",
        output_path="temp.png"
    )
    
    # 发送图片
    await update.message.reply_photo(photo=open("temp.png", "rb"))
```

### 批量生成

```python
from xiaohongshu_generator import XiaohongshuGenerator

generator = XiaohongshuGenerator()

# 生成1-39天的进度图
for day in range(1, 40):
    generator.generate(
        highlight_items=list(range(1, day + 1)),
        title=f"第 {day} 天",
        subtitle=f"累计完成: {day}/39",
        output_path=f"day_{day:02d}.png"
    )
```

## 📝 自定义配置示例

```python
from xiaohongshu_generator import XiaohongshuGenerator

generator = XiaohongshuGenerator()

# 修改颜色方案
generator.bg_color = '#F5F5F5'           # 背景色
generator.highlight_color = '#FF69B4'    # 高亮色
generator.text_color = '#000000'         # 文字色

# 修改尺寸
generator.width = 1600
generator.height = 800
generator.card_width = 100
generator.card_height = 100

# 生成图片
generator.generate(
    highlight_items=[1, 2, 3],
    output_path="custom.png"
)
```

## 🎨 颜色预设

```python
# 小红书官方粉
"#FF3A8C"

# 活力橙
"#FF9800"

# 清新绿
"#52C41A"

# 天空蓝
"#4A90E2"

# 优雅紫
"#9C27B0"

# 暖阳黄
"#FFD700"
```

## 📦 文件结构

```
.
├── xiaohongshu_generator.py          # 核心生成器
├── xiaohongshu_cli.py               # 命令行工具
├── XIAOHONGSHU_GENERATOR_README.md  # 详细文档
├── QUICKSTART.md                    # 本文件
└── 生成的图片/
    ├── xiaohongshu_01.png
    ├── xiaohongshu_multiple.png
    └── xiaohongshu_custom.png
```

## ❓ 遇到问题？

1. **中文乱码**：确保系统安装了中文字体
2. **模块未找到**：运行 `pip install Pillow`
3. **权限错误**：检查输出目录的写入权限

查看完整文档：`XIAOHONGSHU_GENERATOR_README.md`

## 🎉 更多示例

查看已生成的示例图片：
- `xiaohongshu_01.png` - 单个高亮
- `xiaohongshu_multiple.png` - 多个高亮
- `xiaohongshu_custom.png` - 自定义标题
- `test_cli.png` - CLI工具生成

---

**开始创作你的小红书内容计划吧！** 🚀
