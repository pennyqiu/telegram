#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 PIL 生成公众号/知乎封面图。
策略：以 @2x 高分辨率画图，最后 LANCZOS 缩放到目标尺寸，字体抗锯齿锐利。
"""
import os
import sys
import io
from PIL import Image, ImageDraw, ImageFont

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============== 字体路径 ==============
FONT_BOLD = r'C:\Windows\Fonts\msyhbd.ttc'   # 雅黑加粗
FONT_REG = r'C:\Windows\Fonts\msyh.ttc'      # 雅黑常规
FONT_MONO = r'C:\Windows\Fonts\consola.ttf'  # Consolas 等宽


def get_font(path, size, index=0):
    """加载 TTF/TTC 字体，TTC 默认 index=0。"""
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        # 回退到雅黑常规
        return ImageFont.truetype(FONT_REG, size, index=0)


def gradient_bg(w, h, color_a, color_b):
    """生成左上 → 右下的对角线渐变。"""
    img = Image.new('RGB', (w, h), color_a)
    draw = ImageDraw.Draw(img)
    # 对角线渐变（用 max(x+y) 归一化）
    max_d = w + h
    # 为了速度：按行画，每行颜色按对角线位置取
    for y in range(h):
        for x in range(0, w, 4):  # 每 4 像素一次（后续 LANCZOS 平滑）
            t = (x + y) / max_d
            r = int(color_a[0] + (color_b[0] - color_a[0]) * t)
            g = int(color_a[1] + (color_b[1] - color_a[1]) * t)
            b = int(color_a[2] + (color_b[2] - color_a[2]) * t)
            draw.rectangle([x, y, x + 3, y], fill=(r, g, b))
    return img


def gradient_bg_fast(w, h, color_a, color_b):
    """更快的渐变：按行渐变（左→右），对角线效果可后续叠加圆形高光。"""
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img)
    for x in range(w):
        t = x / w
        r = int(color_a[0] + (color_b[0] - color_a[0]) * t)
        g = int(color_a[1] + (color_b[1] - color_a[1]) * t)
        b = int(color_a[2] + (color_b[2] - color_a[2]) * t)
        draw.line([(x, 0), (x, h)], fill=(r, g, b))
    return img


def draw_radial_overlay(img, cx, cy, radius, alpha):
    """在 img 上叠加一个圆形高光（白色，外部透明）。"""
    w, h = img.size
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    # 简化：画一个半透明白色椭圆
    odraw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(255, 255, 255, alpha),
    )
    # 模糊
    from PIL import ImageFilter
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius // 3))
    img = Image.alpha_composite(img.convert('RGBA'), overlay)
    return img.convert('RGB')


def measure_text(draw, text, font):
    """返回 (w, h)。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_pill(draw, x, y, text, font, padding_x=20, padding_y=10,
              bg_color=(255, 255, 255, 38), text_color=(255, 255, 255),
              border_color=None, border_width=1, radius=24):
    """画一个圆角"药丸"标签，返回 (right_x, bottom_y)。"""
    tw, th = measure_text(draw, text, font)
    box = [x, y, x + tw + padding_x * 2, y + th + padding_y * 2]
    # 圆角矩形
    if isinstance(bg_color, tuple) and len(bg_color) == 4:
        # 半透明：需要单独 layer
        pass
    draw.rounded_rectangle(box, radius=radius, fill=bg_color, outline=border_color, width=border_width)
    # 文字基线偏移调整
    text_y = y + padding_y - (th // 6)  # 视觉居中
    draw.text((x + padding_x, text_y), text, fill=text_color, font=font)
    return box[2], box[3]


# ============== 主绘制 ==============
def render_cover(spec, out_path, target_w=900, target_h=500, scale=2):
    """
    spec 字段：
      number_str:    '02'
      tag_label:     '⭐ CPA 旗舰研报'
      tag_num:       '#02'
      tag_extra:     '深度长文 · 5000 字'
      title_accent:  '5000 字读懂'   (金色)
      title_main:    '分红实现率'    (白色)
      subtitle:      '8 家公司横评 · 历史数据 · CPA 视角'
      pills:         ['📊 数据驱动', '🔍 拆解假设', '💼 选公司必读']
      author_name:   'CPA · 香港保险从业者'
      author_sub:    '8 年迅雷总账 → AXA 安盛'
      brand:         'HK INSURANCE HUB'
      brand_ver:     '// v3.1'
      color_a/b:     渐变背景颜色 RGB tuple
    """
    W = target_w * scale
    H = target_h * scale
    s = scale

    # 1. 渐变背景
    bg = gradient_bg_fast(W, H, spec['color_a'], spec['color_b'])

    # 2. 右上角圆形高光
    bg = draw_radial_overlay(bg, cx=W - 100 * s, cy=-80 * s,
                             radius=350 * s, alpha=30)

    # 3. 顶部金色装饰横线
    draw = ImageDraw.Draw(bg)
    # 金色 → 蓝色渐变横线（高度 6）
    for x in range(W):
        t = x / W
        # #fbbf24 → #1e40af
        r = int(0xfb + (0x1e - 0xfb) * t)
        g = int(0xbf + (0x40 - 0xbf) * t)
        b = int(0x24 + (0xaf - 0x24) * t)
        draw.line([(x, 0), (x, 6 * s)], fill=(r, g, b))

    # 4. 右侧巨大水印数字（垂直居中偏右，作为视觉锚点）
    num_font = get_font(FONT_BOLD, 460 * s, index=0)
    num = spec['number_str']
    num_w, num_h = measure_text(draw, num, num_font)
    num_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    nd = ImageDraw.Draw(num_layer)
    num_x = W - num_w - 30 * s
    num_y = (H - num_h) // 2 - 20 * s
    nd.text((num_x, num_y), num,
            font=num_font, fill=(255, 255, 255, 22))
    bg = Image.alpha_composite(bg.convert('RGBA'), num_layer).convert('RGB')
    draw = ImageDraw.Draw(bg)

    # ===== 顶部标签行 =====
    pad_x = 70 * s
    pad_y = 60 * s
    tag_font = get_font(FONT_BOLD, 22 * s, index=0)

    # 标签 1: 金色 CPA 旗舰研报
    gold_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gold_layer)
    # 自己实现金色渐变药丸
    tw1, th1 = measure_text(gd, spec['tag_label'], tag_font)
    pill1_box = [pad_x, pad_y, pad_x + tw1 + 32 * s, pad_y + th1 + 18 * s]
    # 金色 → 橙色 渐变
    pill_w = pill1_box[2] - pill1_box[0]
    pill_h = pill1_box[3] - pill1_box[1]
    pill_grad = Image.new('RGB', (pill_w, pill_h))
    pgd = ImageDraw.Draw(pill_grad)
    for x in range(pill_w):
        t = x / pill_w
        r = int(0xfb + (0xf5 - 0xfb) * t)
        g = int(0xbf + (0x9e - 0xbf) * t)
        b = int(0x24 + (0x0b - 0x24) * t)
        pgd.line([(x, 0), (x, pill_h)], fill=(r, g, b))
    # 圆角 mask
    mask = Image.new('L', (pill_w, pill_h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, pill_w, pill_h], radius=24 * s, fill=255)
    gold_layer.paste(pill_grad, (pill1_box[0], pill1_box[1]), mask)
    # 文字（深棕）
    gdt = ImageDraw.Draw(gold_layer)
    gdt.text((pill1_box[0] + 16 * s, pill1_box[1] + 9 * s - th1 // 8),
             spec['tag_label'], font=tag_font, fill=(124, 45, 18))
    bg = Image.alpha_composite(bg.convert('RGBA'), gold_layer).convert('RGB')
    draw = ImageDraw.Draw(bg)

    # 标签 2: 白底 #02
    x2 = pill1_box[2] + 14 * s
    num_tag_font = get_font(FONT_BOLD, 20 * s, index=0)
    tw2, th2 = measure_text(draw, spec['tag_num'], num_tag_font)
    pill2_box = [x2, pad_y, x2 + tw2 + 32 * s, pad_y + th1 + 18 * s]
    draw.rounded_rectangle(pill2_box, radius=24 * s, fill=(255, 255, 255))
    draw.text((pill2_box[0] + 16 * s, pill2_box[1] + 9 * s - th2 // 8),
              spec['tag_num'], font=num_tag_font, fill=spec['color_a'])

    # 标签 3: 半透明白底 深度长文 5000 字
    x3 = pill2_box[2] + 14 * s
    extra_font = get_font(FONT_REG, 20 * s, index=0)
    tw3, th3 = measure_text(draw, spec['tag_extra'], extra_font)
    pill3_box = [x3, pad_y, x3 + tw3 + 32 * s, pad_y + th1 + 18 * s]
    ext_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ed = ImageDraw.Draw(ext_layer)
    ed.rounded_rectangle(pill3_box, radius=24 * s,
                         fill=(255, 255, 255, 38),
                         outline=(255, 255, 255, 80), width=s)
    ed.text((pill3_box[0] + 16 * s, pill3_box[1] + 9 * s - th3 // 8),
            spec['tag_extra'], font=extra_font, fill=(255, 255, 255))
    bg = Image.alpha_composite(bg.convert('RGBA'), ext_layer).convert('RGB')
    draw = ImageDraw.Draw(bg)

    # ===== 主标题区 =====
    title_y = 150 * s
    title_font = get_font(FONT_BOLD, 60 * s, index=0)

    # accent（金色） 行
    accent_w, accent_h = measure_text(draw, spec['title_accent'], title_font)
    draw.text((pad_x + 3 * s, title_y + 3 * s),
              spec['title_accent'], font=title_font, fill=(0, 0, 0, 100))
    draw.text((pad_x, title_y), spec['title_accent'],
              font=title_font, fill=(251, 191, 36))  # gold

    # main（白色）行
    main_y = title_y + accent_h + 8 * s
    draw.text((pad_x + 3 * s, main_y + 3 * s),
              spec['title_main'], font=title_font, fill=(0, 0, 0, 100))
    draw.text((pad_x, main_y), spec['title_main'],
              font=title_font, fill=(255, 255, 255))

    # 副标题
    sub_y = main_y + accent_h + 20 * s
    sub_font = get_font(FONT_REG, 22 * s, index=0)
    draw.text((pad_x, sub_y), spec['subtitle'],
              font=sub_font, fill=(230, 230, 230))

    # ===== 底部信息（先画底部，留出 Pills 空间）=====
    bot_pad = 50 * s
    # 左：作者
    author_font = get_font(FONT_BOLD, 17 * s, index=0)
    author_sub_font = get_font(FONT_REG, 13 * s, index=0)
    a_name_w, a_name_h = measure_text(draw, spec['author_name'], author_font)
    a_sub_w, a_sub_h = measure_text(draw, spec['author_sub'], author_sub_font)
    bottom_y = H - bot_pad - a_name_h - a_sub_h - 4 * s
    draw.text((pad_x, bottom_y), spec['author_name'],
              font=author_font, fill=(255, 255, 255))
    draw.text((pad_x, bottom_y + a_name_h + 4 * s), spec['author_sub'],
              font=author_sub_font, fill=(220, 220, 220))

    # Pills 行（放在副标题和底部之间）
    pills_y = bottom_y - 50 * s
    px = pad_x
    pill_font = get_font(FONT_REG, 17 * s, index=0)
    pills_layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pld = ImageDraw.Draw(pills_layer)
    for p in spec['pills']:
        pw, ph = measure_text(pld, p, pill_font)
        pb = [px, pills_y, px + pw + 26 * s, pills_y + ph + 12 * s]
        pld.rounded_rectangle(pb, radius=18 * s,
                              fill=(255, 255, 255, 32),
                              outline=(255, 255, 255, 60), width=s)
        pld.text((pb[0] + 13 * s, pb[1] + 6 * s - ph // 8),
                 p, font=pill_font, fill=(255, 255, 255))
        px = pb[2] + 10 * s
    bg = Image.alpha_composite(bg.convert('RGBA'), pills_layer).convert('RGB')
    draw = ImageDraw.Draw(bg)

    # 右：品牌
    brand_font = get_font(FONT_BOLD, 15 * s, index=0)
    brand_ver_font = get_font(FONT_MONO, 12 * s, index=0)
    b_w, b_h = measure_text(draw, spec['brand'], brand_font)
    bv_w, bv_h = measure_text(draw, spec['brand_ver'], brand_ver_font)
    brand_x = W - pad_x - b_w
    brand_y = H - bot_pad - b_h - bv_h - 4 * s
    draw.text((brand_x, brand_y), spec['brand'],
              font=brand_font, fill=(255, 255, 255))
    draw.text((W - pad_x - bv_w, brand_y + b_h + 4 * s),
              spec['brand_ver'], font=brand_ver_font, fill=(180, 180, 180))

    # ===== 缩放到目标尺寸（抗锯齿）=====
    final = bg.resize((target_w, target_h), Image.LANCZOS)
    final.save(out_path, 'PNG', optimize=True)
    size_kb = os.path.getsize(out_path) / 1024
    print(f'[OK] {out_path}  ({target_w}x{target_h}, {size_kb:.1f} KB)')


# ============== CPA-02 封面 ==============
SPEC_CPA02_WECHAT = {
    'number_str':   '02',
    'tag_label':    'CPA 旗舰研报',
    'tag_num':      '#02',
    'tag_extra':    '深度长文 · 5000 字',
    'title_accent': '5000 字读懂',
    'title_main':   '分红实现率',
    'subtitle':     '8 家公司横评 · 历史数据 · CPA 视角',
    'pills':        ['数据驱动', '拆解假设', '选公司必读'],
    'author_name':  'CPA · 香港保险从业者',
    'author_sub':   '8 年迅雷总账 → AXA 安盛',
    'brand':        'HK INSURANCE HUB',
    'brand_ver':    '// v3.1',
    'color_a':      (30, 58, 138),    # #1e3a8a
    'color_b':      (59, 130, 246),   # #3b82f6
}

# 知乎封面：标题不变，比例改 16:9（1280x720）
SPEC_CPA02_ZHIHU = dict(SPEC_CPA02_WECHAT)


def main():
    out_dir = 'insurance-guide/operations/published/wechat/covers'
    os.makedirs(out_dir, exist_ok=True)
    out_dir_zh = 'insurance-guide/operations/published/zhihu/covers'
    os.makedirs(out_dir_zh, exist_ok=True)

    # 公众号头图：900x500
    render_cover(SPEC_CPA02_WECHAT,
                 os.path.join(out_dir, 'cpa02-fulfillment-ratio_900x500.png'),
                 target_w=900, target_h=500, scale=2)

    # 知乎封面：1280x720
    render_cover(SPEC_CPA02_ZHIHU,
                 os.path.join(out_dir_zh, 'cpa02-fulfillment-ratio_1280x720.png'),
                 target_w=1280, target_h=720, scale=2)

    # 同时再做一张方形 800x800（朋友圈/小红书通用）
    out_dir_sq = 'insurance-guide/operations/published/promotional/covers'
    os.makedirs(out_dir_sq, exist_ok=True)
    render_cover(SPEC_CPA02_WECHAT,
                 os.path.join(out_dir_sq, 'cpa02-fulfillment-ratio_800x800.png'),
                 target_w=800, target_h=800, scale=2)


if __name__ == '__main__':
    main()
