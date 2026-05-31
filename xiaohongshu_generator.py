"""
小红书风格图片生成器
生成类似小红书的网格编号选择界面
"""

from PIL import Image, ImageDraw, ImageFont
import os


class XiaohongshuGenerator:
    """小红书风格图片生成器"""
    
    def __init__(self):
        # 画布尺寸
        self.width = 1400
        self.height = 600
        
        # 颜色配置
        self.bg_color = '#FEFEFE'  # 背景色
        self.card_color = '#FFFFFF'  # 卡片背景色
        self.card_border = '#E8E8E8'  # 卡片边框
        self.highlight_color = '#FF3A8C'  # 粉色高亮
        self.text_color = '#333333'  # 文字颜色
        self.text_highlight = '#FFFFFF'  # 高亮文字颜色
        self.subtitle_color = '#999999'  # 副标题颜色
        
        # 网格配置
        self.cols = 13  # 列数
        self.rows = 3   # 行数
        self.total_items = 39  # 总数
        
        # 间距配置
        self.grid_start_x = 50
        self.grid_start_y = 120
        self.card_width = 90
        self.card_height = 90
        self.gap_x = 15
        self.gap_y = 15
        
    def hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def create_rounded_rectangle(self, draw, position, radius=10, fill=None, outline=None, width=1):
        """绘制圆角矩形"""
        x1, y1, x2, y2 = position
        
        # 绘制四个圆角
        draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill, outline=outline, width=width)
        draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill, outline=outline, width=width)
        draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill, outline=outline, width=width)
        draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill, outline=outline, width=width)
        
        # 绘制四条边
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=outline, width=width)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=outline, width=width)
    
    def get_font(self, size, bold=False):
        """获取字体，尝试多个中文字体"""
        font_paths = [
            "C:/Windows/Fonts/msyhbd.ttc",  # 微软雅黑 Bold
            "C:/Windows/Fonts/msyh.ttc",    # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",  # 黑体
            "C:/Windows/Fonts/simsun.ttc",  # 宋体
        ]
        
        if bold:
            font_paths = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"] + font_paths
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except:
                continue
        
        # 如果都失败，使用默认字体
        return ImageFont.load_default()
    
    def generate(self, highlight_items=None, title="小红书 39 篇", 
                 subtitle="一研客副发布信（每篇 1000 字内）", 
                 output_path="xiaohongshu_grid.png"):
        """
        生成小红书风格网格图片
        
        Args:
            highlight_items: 高亮的编号列表，如 [1, 5, 10]
            title: 标题文本
            subtitle: 副标题文本
            output_path: 输出文件路径
        """
        if highlight_items is None:
            highlight_items = [1]
        
        # 创建画布
        img = Image.new('RGB', (self.width, self.height), self.hex_to_rgb(self.bg_color))
        draw = ImageDraw.Draw(img)
        
        # 绘制标题
        self._draw_header(draw, title, subtitle)
        
        # 绘制网格
        self._draw_grid(draw, highlight_items)
        
        # 绘制右上角链接
        self._draw_link(draw, "自动视频→")
        
        # 保存图片
        img.save(output_path, quality=95)
        print(f"[OK] 图片已生成: {output_path}")
        return output_path
    
    def _draw_header(self, draw, title, subtitle):
        """绘制标题区域"""
        # 绘制图标（粉色方块）
        icon_size = 20
        icon_x = 50
        icon_y = 40
        draw.rectangle(
            [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
            fill=self.hex_to_rgb(self.highlight_color)
        )
        
        # 绘制标题
        title_font = self.get_font(32, bold=True)
        title_x = icon_x + icon_size + 15
        title_y = 35
        draw.text((title_x, title_y), title, fill=self.hex_to_rgb(self.text_color), font=title_font)
        
        # 绘制副标题
        subtitle_font = self.get_font(18)
        subtitle_x = title_x + 200
        subtitle_y = 45
        draw.text((subtitle_x, subtitle_y), subtitle, fill=self.hex_to_rgb(self.subtitle_color), font=subtitle_font)
    
    def _draw_link(self, draw, text):
        """绘制右上角链接"""
        link_font = self.get_font(20)
        link_x = self.width - 150
        link_y = 45
        draw.text((link_x, link_y), text, fill=self.hex_to_rgb('#4A90E2'), font=link_font)
    
    def _draw_grid(self, draw, highlight_items):
        """绘制网格"""
        number_font = self.get_font(28, bold=True)
        
        for i in range(self.total_items):
            row = i // self.cols
            col = i % self.cols
            
            # 计算卡片位置
            x1 = self.grid_start_x + col * (self.card_width + self.gap_x)
            y1 = self.grid_start_y + row * (self.card_height + self.gap_y)
            x2 = x1 + self.card_width
            y2 = y1 + self.card_height
            
            # 判断是否高亮
            item_number = i + 1
            is_highlight = item_number in highlight_items
            
            # 绘制卡片
            if is_highlight:
                # 高亮卡片 - 粉色背景
                self.create_rounded_rectangle(
                    draw,
                    [x1, y1, x2, y2],
                    radius=8,
                    fill=self.hex_to_rgb(self.highlight_color),
                    outline=None
                )
                text_color = self.hex_to_rgb(self.text_highlight)
            else:
                # 普通卡片 - 白色背景，灰色边框
                self.create_rounded_rectangle(
                    draw,
                    [x1, y1, x2, y2],
                    radius=8,
                    fill=self.hex_to_rgb(self.card_color),
                    outline=self.hex_to_rgb(self.card_border),
                    width=1
                )
                text_color = self.hex_to_rgb(self.text_color)
            
            # 绘制编号文字（居中）
            number_text = f"{item_number:02d}"
            
            # 计算文字位置（居中）
            bbox = draw.textbbox((0, 0), number_text, font=number_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            text_x = x1 + (self.card_width - text_width) // 2
            text_y = y1 + (self.card_height - text_height) // 2 - 5
            
            draw.text((text_x, text_y), number_text, fill=text_color, font=number_font)


def main():
    """主函数 - 示例用法"""
    generator = XiaohongshuGenerator()
    
    # 示例1: 高亮第1个
    generator.generate(
        highlight_items=[1],
        title="小红书 39 篇",
        subtitle="一研客副发布信（每篇 1000 字内）",
        output_path="xiaohongshu_01.png"
    )
    
    # 示例2: 高亮多个
    generator.generate(
        highlight_items=[1, 5, 10, 15, 20],
        title="小红书 39 篇",
        subtitle="已完成 5 篇",
        output_path="xiaohongshu_multiple.png"
    )
    
    # 示例3: 自定义标题
    generator.generate(
        highlight_items=[1, 2, 3],
        title="内容计划 39 篇",
        subtitle="本周进度：3/39",
        output_path="xiaohongshu_custom.png"
    )
    
    print("\n[SUCCESS] 所有示例图片已生成完成！")


if __name__ == "__main__":
    main()
