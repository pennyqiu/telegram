"""
小红书图片生成器 - 命令行工具
快速生成小红书风格的网格图片
"""

import argparse
import sys
from xiaohongshu_generator import XiaohongshuGenerator


def parse_highlight_items(items_str):
    """解析高亮项目字符串"""
    if not items_str:
        return [1]
    
    items = []
    for part in items_str.split(','):
        part = part.strip()
        if '-' in part:
            # 范围：1-5
            start, end = map(int, part.split('-'))
            items.extend(range(start, end + 1))
        else:
            # 单个数字：1
            items.append(int(part))
    
    return items


def main():
    parser = argparse.ArgumentParser(
        description='生成小红书风格的网格图片',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例用法:
  # 高亮第1个
  python xiaohongshu_cli.py -o output.png
  
  # 高亮多个
  python xiaohongshu_cli.py -i "1,5,10,15,20" -o output.png
  
  # 高亮范围
  python xiaohongshu_cli.py -i "1-10" -o output.png
  
  # 自定义标题
  python xiaohongshu_cli.py -i "1-5" -t "我的内容计划" -s "本周进度: 5/39" -o output.png
  
  # 修改颜色
  python xiaohongshu_cli.py -i "1,2,3" --color "#FF69B4" -o output.png
        '''
    )
    
    parser.add_argument('-i', '--items', 
                       type=str, 
                       default='1',
                       help='要高亮的项目编号，支持逗号分隔和范围（如：1,5,10 或 1-10）')
    
    parser.add_argument('-t', '--title', 
                       type=str, 
                       default='小红书 39 篇',
                       help='标题文字')
    
    parser.add_argument('-s', '--subtitle', 
                       type=str, 
                       default='一研客副发布信（每篇 1000 字内）',
                       help='副标题文字')
    
    parser.add_argument('-o', '--output', 
                       type=str, 
                       default='xiaohongshu_output.png',
                       help='输出文件路径')
    
    parser.add_argument('--color', 
                       type=str, 
                       default='#FF3A8C',
                       help='高亮颜色（十六进制格式，如 #FF3A8C）')
    
    parser.add_argument('--width', 
                       type=int, 
                       default=1400,
                       help='图片宽度')
    
    parser.add_argument('--height', 
                       type=int, 
                       default=600,
                       help='图片高度')
    
    args = parser.parse_args()
    
    # 解析高亮项目
    try:
        highlight_items = parse_highlight_items(args.items)
        print(f"[INFO] 高亮项目: {highlight_items}")
    except Exception as e:
        print(f"[ERROR] 解析高亮项目失败: {e}")
        sys.exit(1)
    
    # 创建生成器
    generator = XiaohongshuGenerator()
    generator.highlight_color = args.color
    generator.width = args.width
    generator.height = args.height
    
    # 生成图片
    try:
        output_path = generator.generate(
            highlight_items=highlight_items,
            title=args.title,
            subtitle=args.subtitle,
            output_path=args.output
        )
        print(f"[SUCCESS] 图片已生成: {output_path}")
    except Exception as e:
        print(f"[ERROR] 生成图片失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
