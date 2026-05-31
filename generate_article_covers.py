"""
为小红书文章生成封面图
根据文章标题和内容生成视觉吸引力强的封面图
"""

from PIL import Image, ImageDraw, ImageFont
import os


class ArticleCoverGenerator:
    """文章封面生成器"""
    
    def __init__(self):
        self.width = 1080
        self.height = 1440
        self.bg_colors = {
            'blue': ['#1e3a5f', '#1a56db'],
            'green': ['#10b981', '#059669'],
            'purple': ['#8b5cf6', '#7c3aed'],
            'orange': ['#f97316', '#ea580c'],
        }
    
    def hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def get_font(self, size, bold=False):
        """获取字体"""
        font_paths = [
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ]
        
        if bold:
            font_paths = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"] + font_paths
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except:
                continue
        
        return ImageFont.load_default()
    
    def create_gradient_background(self, color_scheme='blue'):
        """创建渐变背景"""
        img = Image.new('RGB', (self.width, self.height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        colors = self.bg_colors.get(color_scheme, self.bg_colors['blue'])
        start_color = self.hex_to_rgb(colors[0])
        end_color = self.hex_to_rgb(colors[1])
        
        for y in range(self.height):
            ratio = y / self.height
            r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
            g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
            b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
            draw.rectangle([(0, y), (self.width, y + 1)], fill=(r, g, b))
        
        return img
    
    def wrap_text(self, text, font, max_width):
        """文本换行"""
        lines = []
        words = list(text)
        current_line = ""
        
        draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        
        for char in words:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def draw_text_with_shadow(self, draw, text, position, font, fill=(255, 255, 255), shadow_offset=3):
        """绘制带阴影的文字"""
        x, y = position
        shadow_color = (0, 0, 0, 128)
        draw.text((x + shadow_offset, y + shadow_offset), text, fill=shadow_color, font=font)
        draw.text((x, y), text, fill=fill, font=font)
    
    def generate_cover(self, article_number, title, subtitle="", 
                      output_path="cover.png", color_scheme='blue',
                      category_tag="基础通识"):
        """
        生成文章封面
        
        Args:
            article_number: 文章编号，如 "#4"
            title: 主标题
            subtitle: 副标题
            output_path: 输出路径
            color_scheme: 配色方案 (blue/green/purple/orange)
            category_tag: 分类标签
        """
        img = self.create_gradient_background(color_scheme)
        draw = ImageDraw.Draw(img)
        
        # 绘制编号标签
        tag_font = self.get_font(48, bold=True)
        tag_text = article_number
        draw.text((60, 80), tag_text, fill=(255, 255, 255), font=tag_font)
        
        # 绘制分类标签
        category_font = self.get_font(32)
        draw.text((60, 150), f"[{category_tag}]", fill=(255, 255, 200), font=category_font)
        
        # 绘制主标题
        title_font = self.get_font(72, bold=True)
        max_title_width = self.width - 120
        title_lines = self.wrap_text(title, title_font, max_title_width)
        
        y_offset = 280
        for line in title_lines:
            self.draw_text_with_shadow(draw, line, (60, y_offset), title_font, fill=(255, 255, 255))
            y_offset += 90
        
        # 绘制副标题
        if subtitle:
            subtitle_font = self.get_font(40)
            subtitle_lines = self.wrap_text(subtitle, subtitle_font, max_title_width)
            y_offset += 40
            for line in subtitle_lines:
                draw.text((60, y_offset), line, fill=(220, 240, 255), font=subtitle_font)
                y_offset += 60
        
        # 绘制装饰元素 - 圆形
        for i in range(3):
            x = self.width - 200 + i * 30
            y = self.height - 200 - i * 30
            radius = 100 - i * 20
            draw.ellipse([x, y, x + radius, y + radius], 
                        fill=None, 
                        outline=(255, 255, 255, 100), 
                        width=3)
        
        # 绘制底部标签
        bottom_font = self.get_font(32)
        draw.text((60, self.height - 120), "HKIA License · China CPA", 
                 fill=(255, 255, 255, 200), font=bottom_font)
        
        # 保存图片
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        img.save(output_path, quality=95)
        print(f"[OK] Generated: {output_path}")
        return output_path


def main():
    """批量生成文章封面"""
    generator = ArticleCoverGenerator()
    
    # 文章信息
    articles = [
        {
            'number': '#4',
            'title': '首次赴港投保全流程图解',
            'subtitle': '签证→约访→体检→付款→冷静期',
            'category': '基础通识',
            'color': 'blue',
            'filename': 'xhs-04-hongkong-insurance-process.png'
        },
        {
            'number': '#5',
            'title': '一次讲清：5类港险',
            'subtitle': '储蓄/重疾/医疗/年金/万用寿险',
            'category': '基础通识',
            'color': 'blue',
            'filename': 'xhs-05-five-insurance-types.png'
        },
        {
            'number': '#6',
            'title': '互联网中层家庭财务自查',
            'subtitle': '5题测试（你撑得住吗？）',
            'category': '推荐切入',
            'color': 'green',
            'filename': 'xhs-06-family-finance-check.png'
        },
        {
            'number': '#7',
            'title': '90%资产绑自家股票',
            'subtitle': '到底意味着什么？（CPA视角）',
            'category': '推荐切入',
            'color': 'green',
            'filename': 'xhs-07-stock-concentration-risk.png'
        },
        {
            'number': '#8',
            'title': '互联网大厂35岁被裁',
            'subtitle': '如何用N+1买断后半生现金流？',
            'category': '推荐切入',
            'color': 'green',
            'filename': 'xhs-08-severance-package-planning.png'
        },
        {
            'number': '#9',
            'title': '港险只能用港币买吗？',
            'subtitle': '美元保单的3个真相',
            'category': '基础通识',
            'color': 'blue',
            'filename': 'xhs-09-usd-vs-hkd-policy.png'
        },
        {
            'number': '#10',
            'title': '港险「分红实现率」',
            'subtitle': '是什么？为什么比预期收益率重要',
            'category': '基础通识',
            'color': 'blue',
            'filename': 'xhs-10-dividend-fulfillment-ratio.png'
        },
        {
            'number': '#11',
            'title': '重疾发生在你身上',
            'subtitle': '互联网家庭撑得住几个月？',
            'category': '推荐切入',
            'color': 'green',
            'filename': 'xhs-11-critical-illness-finance.png'
        },
        {
            'number': '#12',
            'title': '跨境家庭的「应急金」',
            'subtitle': '放哪个银行最好？4种方案横评',
            'category': '跨境场景',
            'color': 'purple',
            'filename': 'xhs-12-emergency-fund-banks.png'
        },
    ]
    
    # 生成所有封面
    output_dir = 'insurance-guide/articles/xhs-publish/generated-images'
    
    for article in articles:
        output_path = os.path.join(output_dir, article['filename'])
        generator.generate_cover(
            article_number=article['number'],
            title=article['title'],
            subtitle=article['subtitle'],
            output_path=output_path,
            color_scheme=article['color'],
            category_tag=article['category']
        )
    
    print(f"\n[SUCCESS] Generated {len(articles)} cover images!")
    print(f"[INFO] Output directory: {output_dir}")


if __name__ == "__main__":
    main()
