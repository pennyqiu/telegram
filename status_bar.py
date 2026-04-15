#!/usr/bin/env python3
"""
上下文模式状态栏显示工具
可集成到终端 prompt 或 IDE 状态栏
"""

import os
import sys
from pathlib import Path

# 导入上下文切换逻辑
sys.path.append(str(Path(__file__).parent))
from context_switch import get_current_mode, CONTEXT_MODES

def get_mode_emoji():
    """获取当前模式的 emoji 标识"""
    current = get_current_mode()
    
    mode_emojis = {
        'subscription': '📱',
        'club': '⚽', 
        'insurance': '🏥',
        'investment': '💰',
        'all': '🌍',
        'unknown': '❓'
    }
    
    return mode_emojis.get(current, '❓')

def get_mode_short_name():
    """获取当前模式的短名称"""
    current = get_current_mode()
    
    short_names = {
        'subscription': 'SUB',
        'club': 'CLUB',
        'insurance': 'INS', 
        'investment': 'INV',
        'all': 'ALL',
        'unknown': '???'
    }
    
    return short_names.get(current, '???')

def get_status_line():
    """获取完整状态行"""
    current = get_current_mode()
    emoji = get_mode_emoji()
    short = get_mode_short_name()
    
    if current in CONTEXT_MODES:
        name = CONTEXT_MODES[current]['name'].replace('🎯 ', '').replace('📱 ', '').replace('⚽ ', '').replace('🏥 ', '').replace('💰 ', '').replace('🌍 ', '')
        return f"{emoji} {short} | {name}"
    else:
        return f"{emoji} {short} | 未知模式"

def main():
    """根据参数输出不同格式"""
    if len(sys.argv) < 2:
        print(get_status_line())
        return
        
    format_type = sys.argv[1].lower()
    
    if format_type == 'emoji':
        print(get_mode_emoji())
    elif format_type == 'short':
        print(get_mode_short_name()) 
    elif format_type == 'full':
        print(get_status_line())
    else:
        print(get_status_line())

if __name__ == '__main__':
    main()