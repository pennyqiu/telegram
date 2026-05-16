# -*- coding: utf-8 -*-
"""
更新 insurance-guide/index.html，把单篇『小红书首篇文案』链接升级为
『小红书 39 篇日历』hub 入口；并把发现页的小红书卡片也升级。
"""
import io
import re

INDEX = "insurance-guide/index.html"

with io.open(INDEX, encoding="utf-8") as f:
    content = f.read()

print("Original length:", len(content))

# 1. 替换侧边栏导航的『小红书首篇文案』链接
old_nav = '''<a class="nav-item" href="articles/v22-xhs01.html" style="color:#fbbf24;">
      <span class="num" style="background:rgba(251,191,36,0.25);color:#fde68a">X</span> 小红书首篇文案
    </a>'''

new_nav = '''<a class="nav-item" href="articles/v22-xhs-hub.html" style="color:#fbbf24;">
      <span class="num" style="background:rgba(251,191,36,0.25);color:#fde68a">X</span> 小红书 39 篇日历
    </a>'''

if old_nav in content:
    content = content.replace(old_nav, new_nav)
    print("✓ Sidebar nav updated")
else:
    print("✗ Sidebar nav not found")

# 2. 升级发现页的『首篇爆款图文』卡片为『6 个月 39 篇』
old_card = '''<a href="articles/v22-xhs01.html" style="background:#fff;border:1px solid #fbbf24;border-radius:10px;padding:14px 16px;text-decoration:none;color:#78350f;display:block">'''
new_card = '''<a href="articles/v22-xhs-hub.html" style="background:#fff;border:1px solid #fbbf24;border-radius:10px;padding:14px 16px;text-decoration:none;color:#78350f;display:block">'''

if old_card in content:
    content = content.replace(old_card, new_card)
    print("✓ Discovery card href updated")

# 3. 修改发现页卡片的标题
old_card_title = "首篇爆款图文"
new_card_title = "39 篇 · 6 个月日历"
if old_card_title in content:
    content = content.replace(old_card_title, new_card_title)
    print("✓ Discovery card title updated")

old_card_desc = "3 标题 + 9 图 + CTA + 标签"
new_card_desc = "双赛道平衡 · 每篇含 9 图 + 正文 + Q&A"
if old_card_desc in content:
    content = content.replace(old_card_desc, new_card_desc)
    print("✓ Discovery card description updated")

# 4. 把 hub-xhs-calendar 节里的『查看完整 39 篇日历』按钮升级为本地 hub 链接
old_hub_btn = '<a href="https://github.com/pennyqiu/telegram/blob/main/%E6%88%98%E7%95%A5%E6%89%8B%E5%86%8C.md#-%E5%B0%8F%E7%BA%A2%E4%B9%A6-6-%E4%B8%AA%E6%9C%88%E5%86%85%E5%AE%B9%E6%97%A5%E5%8E%8639-%E7%AF%87--%E5%8F%8C%E8%B5%9B%E9%81%93%E5%B9%B3%E8%A1%A1" target="_blank" style="display:inline-block;background:#1d4ed8;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">查看完整 39 篇日历（标题/类型/视觉建议/钩子）→</a>'
new_hub_btn = (
    '<div style="display:flex;gap:10px;flex-wrap:wrap">'
    '<a href="articles/v22-xhs-hub.html" style="display:inline-block;background:#1d4ed8;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">📖 进入完整 39 篇文章（站内）→</a>'
    '<a href="https://github.com/pennyqiu/telegram/blob/main/%E6%88%98%E7%95%A5%E6%89%8B%E5%86%8C.md#-%E5%B0%8F%E7%BA%A2%E4%B9%A6-6-%E4%B8%AA%E6%9C%88%E5%86%85%E5%AE%B9%E6%97%A5%E5%8E%8639-%E7%AF%87--%E5%8F%8C%E8%B5%9B%E9%81%93%E5%B9%B3%E8%A1%A1" target="_blank" style="display:inline-block;background:#fff;color:#1d4ed8;border:1px solid #1d4ed8;padding:10px 18px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">查看战略手册原文（GitHub）→</a>'
    '</div>'
)
if old_hub_btn in content:
    content = content.replace(old_hub_btn, new_hub_btn)
    print("✓ Hub button upgraded to local 39-article hub")
else:
    print("✗ Hub button not found (might already be updated)")

# 5. 在 hub-xhs-calendar 节信息提示框下方添加『39 篇全部已上线』徽标
old_info = '<div style="background:#fefce8;border:1px solid #fde68a;border-radius:10px;padding:12px 16px;font-size:12.5px;color:#78350f;margin:10px 0">'
new_info = '<div style="background:#dcfce7;border:1px solid #86efac;border-radius:10px;padding:10px 14px;font-size:12.5px;color:#14532d;margin:10px 0;display:flex;align-items:center;gap:8px"><span style="font-size:16px">✅</span><strong>39 篇内容已 100% 完成上线</strong>· 每篇含 3 候选标题 + 9 张图详细文案 + 正文 ≤ 1000 字 + Q&A 应答模板 + 12 话题标签 + 合规自检清单。点击下方按钮直接浏览。</div>\n    <div style="background:#fefce8;border:1px solid #fde68a;border-radius:10px;padding:12px 16px;font-size:12.5px;color:#78350f;margin:10px 0">'
# Only inject the badge once (look for a sentinel)
if "39 篇内容已 100% 完成上线" not in content:
    # find the very specific instance directly above hub button
    idx = content.find('<strong>必备前置物料（M1 启动前）：</strong>')
    if idx > 0:
        # find the preceding <div ...> to inject before
        start = content.rfind('<div style="background:#fefce8', 0, idx)
        if start > 0:
            content = content[:start] + new_info.replace(old_info, '') + old_info + content[start+len(old_info):]
            print("✓ '39 篇上线' badge injected")

print("New length:", len(content))

with io.open(INDEX, "w", encoding="utf-8") as f:
    f.write(content)

print("✓ index.html written")
