#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给所有关键 index.html 注入防浏览器缓存的 meta 标签 + 在 footer 加版本时间戳"""
import os, sys, io, datetime, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
META_BLOCK = (
    '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n'
    '<meta http-equiv="Pragma" content="no-cache">\n'
    '<meta http-equiv="Expires" content="0">\n'
    f'<meta name="generator" content="v3.2 · {NOW}">\n'
)

TARGETS = [
    'insurance-guide/index.html',
    'insurance-guide/operations/index.html',
    'insurance-guide/operations/dashboard.html',
    'insurance-guide/operations/published/wechat/index.html',
    'insurance-guide/operations/published/zhihu/index.html',
    'insurance-guide/operations/published/xhs/index.html',
    'insurance-guide/operations/published/xhs-units/index.html',
    'insurance-guide/operations/published/pyq/index.html',
    'insurance-guide/operations/published/units/index.html',
]

for p in TARGETS:
    if not os.path.exists(p):
        print(f'[SKIP] {p} 不存在')
        continue
    with open(p, 'r', encoding='utf-8') as f:
        c = f.read()
    
    # 1) 清理旧的 cache-control / generator meta（避免重复）
    c = re.sub(r'<meta http-equiv="Cache-Control"[^>]*>\s*\n?', '', c)
    c = re.sub(r'<meta http-equiv="Pragma"[^>]*>\s*\n?', '', c)
    c = re.sub(r'<meta http-equiv="Expires"[^>]*>\s*\n?', '', c)
    c = re.sub(r'<meta name="generator"[^>]*>\s*\n?', '', c)
    
    # 2) 在 <meta charset=...> 之后注入新的 4 行 meta
    if 'http-equiv="Cache-Control"' not in c:
        c = re.sub(
            r'(<meta charset="UTF-8">\s*\n)',
            r'\1' + META_BLOCK,
            c,
            count=1
        )
    
    # 3) 在 footer 里追加版本时间戳（只在还没有的情况下）
    # 找 "v3.1" 或 "v3.2" 替换为带时间的版本
    version_tag = f'v3.2 · {NOW}'
    c = re.sub(r'v3\.\d+(?!\s*·\s*\d)', version_tag, c)
    
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print(f'[OK] {p}')

print(f'\n版本时间戳：{version_tag}')
print('刷新页面后，看 footer 应该显示这个版本')
