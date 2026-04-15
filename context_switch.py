#!/usr/bin/env python3
"""
Telegram 项目上下文自动切换工具
用法: python context_switch.py [模式]
"""

import os
import sys
import re
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent
CURSORIGNORE_PATH = ROOT_DIR / '.cursorignore'

# 上下文模式配置
CONTEXT_MODES = {
    'subscription': {
        'name': '📱 Telegram 订阅系统',
        'description': '专注 tg-subscription/ + docs/',
        'ignore_patterns': [
            'tg-club/',
            'insurance-guide/',
            'investment_tracker/',
            '*analysis.html',
            '*tracker.html', 
            '*calculator.html',
            '*learning.html',
            'value_investing_*.html',
            'scraped_articles.json'
        ]
    },
    'club': {
        'name': '⚽ Telegram 俱乐部系统', 
        'description': '专注 tg-club/ (保留订阅API依赖)',
        'ignore_patterns': [
            'insurance-guide/',
            'investment_tracker/',
            '*analysis.html',
            '*tracker.html',
            '*calculator.html', 
            '*learning.html',
            'value_investing_*.html',
            'scraped_articles.json'
        ]
    },
    'insurance': {
        'name': '🏥 保险指南系统',
        'description': '专注 insurance-guide/',
        'ignore_patterns': [
            'tg-club/',
            'tg-subscription/',
            'investment_tracker/',
            '*analysis.html',
            '*tracker.html',
            '*calculator.html',
            '*learning.html', 
            'value_investing_*.html',
            'docs/',
            'scraped_articles.json'
        ]
    },
    'investment': {
        'name': '💰 投资工具集',
        'description': '专注投资相关文件',
        'ignore_patterns': [
            'tg-club/',
            'tg-subscription/',
            'insurance-guide/',
            'docs/'
        ]
    },
    'all': {
        'name': '🌍 全部模块',
        'description': '显示所有文件 (仅保留通用忽略)',
        'ignore_patterns': []
    }
}

def read_cursorignore():
    """读取当前 .cursorignore 文件"""
    if not CURSORIGNORE_PATH.exists():
        return ""
    return CURSORIGNORE_PATH.read_text(encoding='utf-8')

def write_cursorignore(content):
    """写入 .cursorignore 文件"""
    CURSORIGNORE_PATH.write_text(content, encoding='utf-8')

def get_current_mode():
    """检测当前激活的模式"""
    content = read_cursorignore()
    
    for mode_key, config in CONTEXT_MODES.items():
        if mode_key == 'all':
            continue
            
        # 检查该模式的忽略模式是否都被激活（未注释）
        patterns = config['ignore_patterns']
        if not patterns:
            continue
            
        active_count = 0
        for pattern in patterns:
            # 查找未注释的模式行
            if re.search(f'^{re.escape(pattern)}$', content, re.MULTILINE):
                active_count += 1
                
        # 如果大部分模式都激活，认为是该模式
        if active_count >= len(patterns) * 0.7:  # 70%匹配度
            return mode_key
    
    return 'unknown'

def apply_mode(mode_key):
    """应用指定的上下文模式"""
    if mode_key not in CONTEXT_MODES:
        print(f"❌ 错误：未知模式 '{mode_key}'")
        print(f"可用模式: {', '.join(CONTEXT_MODES.keys())}")
        return False
        
    config = CONTEXT_MODES[mode_key]
    content = read_cursorignore()
    
    # 重置所有注释（在模式相关行前添加 #）
    for other_mode_config in CONTEXT_MODES.values():
        for pattern in other_mode_config['ignore_patterns']:
            # 确保行被注释
            content = re.sub(
                f'^{re.escape(pattern)}$',
                f'# {pattern}',
                content,
                flags=re.MULTILINE
            )
    
    # 激活当前模式（移除 # 注释）
    if mode_key != 'all':
        for pattern in config['ignore_patterns']:
            # 移除注释符号
            content = re.sub(
                f'^# {re.escape(pattern)}$',
                pattern,
                content,
                flags=re.MULTILINE
            )
    
    write_cursorignore(content)
    print(f"✅ 已切换到：{config['name']}")
    print(f"📝 {config['description']}")
    return True

def show_status():
    """显示当前状态"""
    current = get_current_mode()
    if current == 'unknown':
        print("❓ 当前模式：未知（可能是手动配置）")
    else:
        config = CONTEXT_MODES[current]
        print(f"🎯 当前模式：{config['name']}")
        print(f"📝 {config['description']}")

def show_help():
    """显示帮助信息"""
    print("🗺️  Telegram 项目上下文切换工具")
    print("=" * 50)
    print()
    print("用法:")
    print("  python context_switch.py <模式>     # 切换到指定模式")
    print("  python context_switch.py status     # 查看当前状态")
    print("  python context_switch.py help       # 显示此帮助")
    print()
    print("可用模式:")
    for key, config in CONTEXT_MODES.items():
        print(f"  {key:12} - {config['name']}")
        print(f"               {config['description']}")
    print()
    print("示例:")
    print("  python context_switch.py subscription")
    print("  python context_switch.py club")
    print("  python context_switch.py all")

def main():
    if len(sys.argv) < 2:
        show_status()
        print()
        print("💡 使用 'python context_switch.py help' 查看所有选项")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'help':
        show_help()
    elif command == 'status':
        show_status()
    elif command in CONTEXT_MODES:
        apply_mode(command)
    else:
        print(f"❌ 未知命令: {command}")
        show_help()

if __name__ == '__main__':
    main()