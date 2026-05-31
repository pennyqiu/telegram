"""
生成小红书文章的完整9张图片系列
每篇文章包含: 1张封面 + 7张内容图 + 1张CTA图
"""

from PIL import Image, ImageDraw, ImageFont
import os


class XHSSeriesGenerator:
    """小红书系列图片生成器"""
    
    def __init__(self):
        self.width = 1080
        self.height = 1440
        
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
        ]
        
        if bold:
            font_paths = ["C:/Windows/Fonts/msyhbd.ttc"] + font_paths
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except:
                continue
        
        return ImageFont.load_default()
    
    def create_gradient_bg(self, colors):
        """创建渐变背景"""
        img = Image.new('RGB', (self.width, self.height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        start_color = self.hex_to_rgb(colors[0])
        end_color = self.hex_to_rgb(colors[1])
        
        for y in range(self.height):
            ratio = y / self.height
            r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
            g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
            b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
            draw.rectangle([(0, y), (self.width, y + 1)], fill=(r, g, b))
        
        return img, draw
    
    def wrap_text(self, text, font, max_width):
        """文本换行"""
        lines = []
        current_line = ""
        
        draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        
        for char in text:
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
    
    def draw_text_lines(self, draw, lines, x, y, font, color, line_spacing=20):
        """绘制多行文本"""
        current_y = y
        for line in lines:
            draw.text((x, current_y), line, fill=color, font=font)
            bbox = draw.textbbox((x, current_y), line, font=font)
            current_y += (bbox[3] - bbox[1]) + line_spacing
        return current_y
    
    def generate_cover(self, title, subtitle, output_path):
        """
        生成封面图 (图1)
        深蓝渐变 + 流程图剪影
        """
        img, draw = self.create_gradient_bg(['#1e3a5f', '#1a56db'])
        
        # 主标题
        title_font = self.get_font(88, bold=True)
        title_lines = self.wrap_text(title, title_font, self.width - 120)
        y = 300
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y), line, fill=(255, 255, 255), font=title_font)
            y += 110
        
        # 副标题
        subtitle_font = self.get_font(52, bold=True)
        y += 40
        bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, y), subtitle, fill=(200, 230, 255), font=subtitle_font)
        
        # 流程图示意 - 6个圆点连线
        y += 120
        circle_y = y
        spacing = 120
        start_x = 150
        
        for i in range(6):
            cx = start_x + i * spacing
            # 绘制圆圈
            draw.ellipse([cx-30, circle_y-30, cx+30, circle_y+30], 
                        fill=(255, 255, 255, 200), 
                        outline=(255, 255, 255), 
                        width=3)
            # 绘制编号
            num_font = self.get_font(32, bold=True)
            num_text = str(i+1)
            bbox = draw.textbbox((0, 0), num_text, font=num_font)
            num_width = bbox[2] - bbox[0]
            draw.text((cx - num_width//2, circle_y - 20), num_text, 
                     fill=(30, 58, 95), font=num_font)
            
            # 绘制连接线
            if i < 5:
                draw.line([cx+30, circle_y, cx+spacing-30, circle_y], 
                         fill=(255, 255, 255), width=4)
        
        # 底部标识
        bottom_font = self.get_font(36)
        bottom_text = "HKIA License | China CPA"
        bbox = draw.textbbox((0, 0), bottom_text, font=bottom_font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, self.height - 120), bottom_text, 
                 fill=(200, 230, 255), font=bottom_font)
        
        # 保存建议标签
        tag_font = self.get_font(32)
        draw.text((60, 100), "[Recommended Save]", fill=(255, 220, 100), font=tag_font)
        
        img.save(output_path, quality=95)
        print(f"[OK] Generated: {output_path}")
    
    def generate_overview(self, title, items, output_path):
        """
        生成总览图 (图2)
        列出所有节点
        """
        img, draw = self.create_gradient_bg(['#f8fafc', '#e2e8f0'])
        
        # 标题
        title_font = self.get_font(72, bold=True)
        draw.text((60, 100), title, fill=(30, 58, 95), font=title_font)
        
        # 分隔线
        draw.rectangle([60, 200, self.width-60, 205], fill=(100, 150, 200))
        
        # 列出所有节点
        y = 260
        item_font = self.get_font(48, bold=True)
        
        for i, item in enumerate(items):
            # 圆形编号背景
            cx, cy = 110, y + 30
            draw.ellipse([cx-35, cy-35, cx+35, cy+35], 
                        fill=(30, 58, 95))
            
            # 编号文字
            num_font = self.get_font(36, bold=True)
            num_text = str(i+1)
            bbox = draw.textbbox((0, 0), num_text, font=num_font)
            num_width = bbox[2] - bbox[0]
            draw.text((cx - num_width//2, cy - 20), num_text, 
                     fill=(255, 255, 255), font=num_font)
            
            # 节点文字
            lines = self.wrap_text(item, item_font, self.width - 220)
            self.draw_text_lines(draw, lines, 180, y, item_font, 
                               (30, 58, 95), line_spacing=15)
            
            y += 140
        
        img.save(output_path, quality=95)
        print(f"[OK] Generated: {output_path}")
    
    def generate_detail_card(self, node_num, node_title, content_lines, 
                            output_path, highlight_color='#10b981'):
        """
        生成详细内容卡片 (图3-8)
        白色背景 + 结构化内容
        """
        img = Image.new('RGB', (self.width, self.height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # 顶部色条
        draw.rectangle([0, 0, self.width, 20], fill=self.hex_to_rgb(highlight_color))
        
        # 节点标题区域
        title_bg_color = self.hex_to_rgb(highlight_color)
        draw.rectangle([0, 60, self.width, 220], fill=title_bg_color)
        
        # 节点编号
        num_font = self.get_font(64, bold=True)
        draw.text((60, 80), node_num, fill=(255, 255, 255), font=num_font)
        
        # 节点标题
        title_font = self.get_font(56, bold=True)
        draw.text((60, 155), node_title, fill=(255, 255, 255), font=title_font)
        
        # 内容区域
        y = 280
        content_font = self.get_font(44)
        
        for line in content_lines:
            if line.startswith('[CHECK]'):
                # 正确标记
                draw.text((80, y), "✓", fill=(16, 185, 129), font=self.get_font(50))
                text = line.replace('[CHECK]', '').strip()
                draw.text((150, y), text, fill=(30, 58, 95), font=content_font)
            elif line.startswith('[CROSS]'):
                # 错误标记
                draw.text((80, y), "×", fill=(239, 68, 68), font=self.get_font(50))
                text = line.replace('[CROSS]', '').strip()
                draw.text((150, y), text, fill=(30, 58, 95), font=content_font)
            elif line.startswith('[ARROW]'):
                # 箭头
                draw.text((80, y), "→", fill=(100, 116, 139), font=self.get_font(50))
                text = line.replace('[ARROW]', '').strip()
                draw.text((150, y), text, fill=(30, 58, 95), font=content_font)
            elif line.startswith('[TITLE]'):
                # 小标题
                text = line.replace('[TITLE]', '').strip()
                title_font_small = self.get_font(50, bold=True)
                draw.text((60, y), text, fill=(30, 58, 95), font=title_font_small)
                y += 10
            elif line.strip() == '':
                y += 20
            else:
                # 普通文字
                lines = self.wrap_text(line, content_font, self.width - 140)
                for text_line in lines:
                    draw.text((80, y), text_line, fill=(30, 58, 95), font=content_font)
                    y += 60
                continue
            
            y += 65
        
        img.save(output_path, quality=95)
        print(f"[OK] Generated: {output_path}")
    
    def generate_cta_card(self, title, subtitle, cta_text, output_path):
        """
        生成CTA引导图 (图9)
        """
        img, draw = self.create_gradient_bg(['#eff6ff', '#dbeafe'])
        
        # 大图标 - 礼物盒
        icon_size = 200
        icon_x = (self.width - icon_size) // 2
        icon_y = 250
        draw.rectangle([icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
                      fill=(59, 130, 246), outline=None)
        
        # 标题
        title_font = self.get_font(68, bold=True)
        title_lines = self.wrap_text(title, title_font, self.width - 120)
        y = icon_y + icon_size + 80
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y), line, fill=(30, 58, 95), font=title_font)
            y += 85
        
        # 副标题
        y += 40
        subtitle_font = self.get_font(40)
        subtitle_lines = self.wrap_text(subtitle, subtitle_font, self.width - 120)
        for line in subtitle_lines:
            bbox = draw.textbbox((0, 0), line, font=subtitle_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y), line, fill=(100, 116, 139), font=subtitle_font)
            y += 55
        
        # CTA按钮
        y += 60
        button_width = 600
        button_height = 100
        button_x = (self.width - button_width) // 2
        button_y = y
        
        # 绘制按钮
        draw.rounded_rectangle(
            [button_x, button_y, button_x + button_width, button_y + button_height],
            radius=50,
            fill=(59, 130, 246)
        )
        
        # 按钮文字
        cta_font = self.get_font(48, bold=True)
        bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
        text_width = bbox[2] - bbox[0]
        text_x = button_x + (button_width - text_width) // 2
        text_y = button_y + 25
        draw.text((text_x, text_y), cta_text, fill=(255, 255, 255), font=cta_font)
        
        img.save(output_path, quality=95)
        print(f"[OK] Generated: {output_path}")


def generate_article_04():
    """生成第4篇文章的完整9张图"""
    generator = XHSSeriesGenerator()
    output_dir = 'insurance-guide/articles/xhs-publish/generated-images/article-04'
    os.makedirs(output_dir, exist_ok=True)
    
    # 图1 - 封面
    generator.generate_cover(
        title="首次赴港投保",
        subtitle="6 大节点 · 全流程",
        output_path=f"{output_dir}/01-cover.png"
    )
    
    # 图2 - 总览
    generator.generate_overview(
        title="6 大节点全流程",
        items=[
            "节点 1 · 签证 / 通行证",
            "节点 2 · 健康问询 + 预核保",
            "节点 3 · 约访 + 准备资料",
            "节点 4 · 赴港签单",
            "节点 5 · 体检 + 付款",
            "节点 6 · 冷静期 + 保单生效"
        ],
        output_path=f"{output_dir}/02-overview.png"
    )
    
    # 图3 - 节点1: 签证
    generator.generate_detail_card(
        node_num="节点 1",
        node_title="签证 / 通行证",
        content_lines=[
            "[CHECK] 港澳通行证 + 个签 / 团签都可",
            "[CHECK] 没办过的 → 居住地公安出入境办",
            "",
            "[CROSS] 注意：商务签证不可投保",
            "",
            "[TITLE] 建议提前 14 天办理"
        ],
        output_path=f"{output_dir}/03-node1-visa.png",
        highlight_color='#3b82f6'
    )
    
    # 图4 - 节点2: 健康问询
    generator.generate_detail_card(
        node_num="节点 2",
        node_title="健康问询 + 预核保",
        content_lines=[
            "持牌人发健康问卷（约 30 题）",
            "",
            "[ARROW] 重大病史 → 预核保",
            "[ARROW] 健康体 → 直接预约",
            "",
            "[TITLE] 常见加费 / 拒保情况：",
            "· 甲状腺结节 / 乙肝",
            "· 高血压 / 糖尿病"
        ],
        output_path=f"{output_dir}/04-node2-health.png",
        highlight_color='#3b82f6'
    )
    
    # 图5 - 节点3: 约访资料
    generator.generate_detail_card(
        node_num="节点 3",
        node_title="约访 + 准备资料",
        content_lines=[
            "[TITLE] 需要准备：",
            "",
            "[CHECK] 港澳通行证原件",
            "[CHECK] 内地身份证原件",
            "[CHECK] 银行流水（保费证明）",
            "[CHECK] 地址证明（水电单 / 流水）",
            "[CHECK] 健康检查报告（如有）"
        ],
        output_path=f"{output_dir}/05-node3-materials.png",
        highlight_color='#3b82f6'
    )
    
    # 图6 - 节点4: 赴港签单
    generator.generate_detail_card(
        node_num="节点 4",
        node_title="赴港签单",
        content_lines=[
            "签约地必须是香港境内",
            "（保险公司 / 经纪行办公室）",
            "",
            "持牌人见证签字",
            "",
            "",
            "[CROSS] 任何『内地酒店签 / 视频签』",
            "    都属违规"
        ],
        output_path=f"{output_dir}/06-node4-signing.png",
        highlight_color='#ef4444'
    )
    
    # 图7 - 节点5: 体检付款
    generator.generate_detail_card(
        node_num="节点 5",
        node_title="体检 + 付款",
        content_lines=[
            "[TITLE] 体检：",
            "按预核保结果 → 指定医院体检",
            "",
            "[TITLE] 付款合规渠道：",
            "[CHECK] VISA / MasterCard 国际卡",
            "[CHECK] 香港本地卡 / 现金 / 支票",
            "[CHECK] 银联人民币卡（部分公司）",
            "",
            "[CROSS] 内地银行卡刷港币"
        ],
        output_path=f"{output_dir}/07-node5-payment.png",
        highlight_color='#10b981'
    )
    
    # 图8 - 节点6: 冷静期
    generator.generate_detail_card(
        node_num="节点 6",
        node_title="冷静期 + 保单生效",
        content_lines=[
            "首期保单 21 天冷静期",
            "期间无条件全额退保",
            "（免任何手续费）",
            "",
            "",
            "冷静期结束后",
            "保单正式生效"
        ],
        output_path=f"{output_dir}/08-node6-cooling.png",
        highlight_color='#10b981'
    )
    
    # 图9 - CTA
    generator.generate_cta_card(
        title="完整流程图 PDF",
        subtitle="首次赴港投保流程图 + 体检医院清单 PDF",
        cta_text="私信获取完整版",
        output_path=f"{output_dir}/09-cta.png"
    )
    
    print(f"\n[SUCCESS] Article 04 complete! Generated 9 images.")
    print(f"[INFO] Output directory: {output_dir}")


if __name__ == "__main__":
    generate_article_04()
