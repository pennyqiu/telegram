#!/usr/bin/env python3
"""
重建金渐成文章导航页 (public/index.html)
- 从 URL 解析真实发布日期 (articles/jinjiancheng/YYYY-MM-DD)
- 按日期升序排序（最早在上，方便从上往下顺序阅读）
- 不需要重新爬取
"""

import json
import os
import re
from datetime import datetime
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(ROOT, "jinjiancheng_archive", "metadata.json")
OUT = os.path.join(ROOT, "jinjiancheng_archive", "public", "index.html")

TOPICS = {
    "美股":     {"slug": "us-stocks",      "icon": "📈", "description": "美股投资、科技股、纳指与标普配置"},
    "港股":     {"slug": "hk-stocks",      "icon": "🇭🇰", "description": "港股、腾讯及相关仓位调整"},
    "比特币":   {"slug": "crypto-bitcoin", "icon": "₿",  "description": "比特币、加密货币与链上资产"},
    "黄金":     {"slug": "gold",           "icon": "🥇", "description": "黄金、贵金属和防守型配置"},
    "房地产":   {"slug": "real-estate",    "icon": "🏢", "description": "房地产、楼市、房企与救市政策"},
    "债务":     {"slug": "debt-crisis",    "icon": "📉", "description": "债务、暴雷、违约与信用风险"},
    "职场":     {"slug": "workplace",      "icon": "💼", "description": "裁员、欠薪、职场与就业"},
    "A股":      {"slug": "a-shares",       "icon": "📊", "description": "A股、消费股与国内权益市场"},
}

DATE_FROM_URL = re.compile(r"/articles/jinjiancheng/(\d{4}-\d{2}-\d{2})")


def extract_date(url: str) -> str:
    """从 URL 提取真实发布日期 (最可靠的来源)"""
    m = DATE_FROM_URL.search(url or "")
    return m.group(1) if m else ""


def parse_date(s: str):
    """安全解析日期，失败返回 datetime.min（排到最前）"""
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return datetime.min


def main():
    print(f"[1/3] 读取元数据: {META}")
    with open(META, encoding="utf-8") as f:
        articles = json.load(f)
    print(f"      共 {len(articles)} 篇")

    print("[2/3] 从 URL 重新解析发布日期 + 按主题分组 + 升序排序")
    by_topic = defaultdict(list)
    fixed_count = 0
    for a in articles:
        real_date = extract_date(a.get("url", ""))
        if real_date and real_date != a.get("date"):
            fixed_count += 1
        a["date"] = real_date or a.get("date", "")
        topic = a.get("topic", "其他")
        by_topic[topic].append(a)

    for topic in by_topic:
        by_topic[topic].sort(key=lambda x: parse_date(x["date"]))

    print(f"      修正了 {fixed_count} 篇文章的日期")

    print(f"[3/3] 生成导航页: {OUT}")
    total = sum(len(v) for v in by_topic.values())

    html_parts = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>金渐成投资方法论专题 · 学习导航</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
    line-height: 1.7; color: #1f2937; background: #f9fafb; padding: 20px;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
.header {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 60px 40px; border-radius: 20px;
    margin-bottom: 32px; box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3);
}}
.header h1 {{ font-size: 42px; margin-bottom: 16px; font-weight: 700; }}
.header p {{ font-size: 15px; opacity: .95; line-height: 1.8; }}
.disclaimer {{
    background: #fef3c7; border-left: 4px solid #f59e0b;
    padding: 20px 24px; border-radius: 12px; margin-bottom: 32px;
    font-size: 14px;
}}
.topic-nav {{
    display: flex; flex-wrap: wrap; gap: 10px;
    background: #fff; padding: 18px 22px; border-radius: 14px;
    margin-bottom: 30px; box-shadow: 0 2px 12px rgba(0,0,0,.04);
}}
.topic-nav a {{
    padding: 8px 16px; border-radius: 99px; text-decoration: none;
    background: #f3f4f6; color: #374151; font-size: 13px; font-weight: 600;
    transition: all .15s;
}}
.topic-nav a:hover {{ background: #667eea; color: #fff; }}
.topic-section {{
    background: white; padding: 36px 40px; border-radius: 16px;
    margin-bottom: 30px; box-shadow: 0 2px 20px rgba(0,0,0,0.06);
    scroll-margin-top: 20px;
}}
.topic-header {{
    display: flex; align-items: center; margin-bottom: 8px;
}}
.topic-icon {{ font-size: 32px; margin-right: 14px; }}
.topic-title {{ font-size: 26px; font-weight: 700; }}
.topic-desc {{
    color: #6b7280; font-size: 14px; margin-bottom: 18px;
    padding-left: 46px;
}}
.topic-meta {{
    padding-left: 46px; font-size: 12px; color: #9ca3af;
    margin-bottom: 24px; padding-bottom: 16px;
    border-bottom: 2px solid #e5e7eb;
}}
.reading-hint {{
    background: #eff6ff; border-left: 3px solid #3b82f6;
    padding: 12px 16px; border-radius: 0 8px 8px 0;
    margin-bottom: 20px; font-size: 13px; color: #1e40af;
}}
.year-divider {{
    font-size: 13px; font-weight: 800; color: #9ca3af;
    letter-spacing: .08em; margin: 24px 0 12px;
    padding-bottom: 6px; border-bottom: 1px dashed #e5e7eb;
}}
.year-divider:first-child {{ margin-top: 8px; }}
.article-item {{
    padding: 16px 20px; border-radius: 10px;
    margin-bottom: 10px; background: #f9fafb;
    border: 1px solid #e5e7eb; transition: all .2s;
    display: flex; align-items: flex-start; gap: 16px;
}}
.article-item:hover {{
    background: #f3f4f6; border-color: #667eea; transform: translateX(3px);
}}
.article-date {{
    flex-shrink: 0; width: 90px; font-family: ui-monospace, monospace;
    font-size: 12px; color: #6b7280; font-weight: 600;
    padding-top: 2px;
}}
.article-main {{ flex: 1; min-width: 0; }}
.article-title a {{
    color: #1f2937; text-decoration: none;
    font-size: 15px; font-weight: 600; line-height: 1.5;
}}
.article-title a:hover {{ color: #667eea; text-decoration: underline; }}
.article-link-icon {{ font-size: 12px; opacity: .5; margin-left: 4px; }}
.footer {{ text-align: center; padding: 32px; color: #9ca3af; font-size: 13px; }}
.footer a {{ color: #667eea; }}
.stats {{ display: flex; gap: 20px; margin-top: 20px; flex-wrap: wrap; }}
.stat-item {{
    background: rgba(255,255,255,0.15); padding: 10px 20px;
    border-radius: 10px; backdrop-filter: blur(10px);
}}
.stat-num {{ font-size: 24px; font-weight: 700; display: block; }}
.stat-label {{ font-size: 12px; opacity: .9; margin-top: 2px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📚 金渐成投资方法论专题</h1>
    <p>个人学习资料导航 · 按时间正序排列，可从最早一篇向下顺序阅读，体会投资思路的演进</p>
    <div class="stats">
      <div class="stat-item">
        <span class="stat-num">{total}</span>
        <span class="stat-label">篇文章</span>
      </div>
      <div class="stat-item">
        <span class="stat-num">{len([k for k in TOPICS if by_topic.get(k)])}</span>
        <span class="stat-label">个主题</span>
      </div>
      <div class="stat-item">
        <span class="stat-num">2022 → 2026</span>
        <span class="stat-label">时间跨度</span>
      </div>
    </div>
  </div>

  <div class="disclaimer">
    <strong>⚖️ 版权声明</strong>　
    本页面所列文章版权归原作者 <strong>金渐成</strong> 所有。本导航仅做学习引用，
    不转载正文，所有链接指向原网站 <a href="https://jinjiancheng.com" target="_blank" style="color:#d97706;text-decoration:underline;">jinjiancheng.com</a>。
  </div>

  <div class="topic-nav">
    <strong style="font-size:13px;color:#6b7280;padding:8px 0">快速跳转：</strong>
"""]

    for topic_name in TOPICS:
        if by_topic.get(topic_name):
            slug = TOPICS[topic_name]["slug"]
            icon = TOPICS[topic_name]["icon"]
            cnt = len(by_topic[topic_name])
            html_parts.append(
                f'    <a href="#{slug}">{icon} {topic_name} ({cnt})</a>\n'
            )

    html_parts.append("  </div>\n")

    for topic_name, topic_info in TOPICS.items():
        topic_articles = by_topic.get(topic_name, [])
        if not topic_articles:
            continue

        slug = topic_info["slug"]
        icon = topic_info["icon"]
        first_date = topic_articles[0]["date"] or "?"
        last_date = topic_articles[-1]["date"] or "?"

        html_parts.append(f"""
  <div class="topic-section" id="{slug}">
    <div class="topic-header">
      <span class="topic-icon">{icon}</span>
      <h2 class="topic-title">{topic_name}</h2>
    </div>
    <p class="topic-desc">{topic_info['description']}</p>
    <div class="topic-meta">
      共 <strong>{len(topic_articles)}</strong> 篇 · 时间跨度 {first_date} → {last_date}
    </div>
    <div class="reading-hint">
      📖 建议从最早一篇（{first_date}）开始顺序往下读，可看出仓位、心态、配置框架的完整演进过程
    </div>
""")

        current_year = None
        for a in topic_articles:
            date = a["date"] or "—"
            year = date[:4] if date != "—" else "未知"
            if year != current_year:
                html_parts.append(f'    <div class="year-divider">📅 {year} 年</div>\n')
                current_year = year

            title = a.get("title", "无标题")
            url = a.get("url", "#")
            html_parts.append(f"""    <div class="article-item">
      <div class="article-date">{date}</div>
      <div class="article-main">
        <div class="article-title">
          <a href="{url}" target="_blank" rel="noopener">{title}<span class="article-link-icon">🔗</span></a>
        </div>
      </div>
    </div>
""")

        html_parts.append("  </div>\n")

    html_parts.append(f"""
  <div class="footer">
    <p>生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 共 {total} 篇</p>
    <p style="margin-top:6px">原始数据来源 <a href="https://jinjiancheng.com/topics" target="_blank">jinjiancheng.com/topics</a></p>
  </div>
</div>
</body>
</html>
""")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("".join(html_parts))

    print(f"\n✅ 完成!")
    print(f"   文件: {OUT}")
    print(f"   大小: {os.path.getsize(OUT) // 1024} KB")
    print(f"\n📊 各主题文章数（按时间升序）:")
    for topic in TOPICS:
        items = by_topic.get(topic, [])
        if items:
            print(f"   {TOPICS[topic]['icon']} {topic:<6} {len(items):>3} 篇 · {items[0]['date']} → {items[-1]['date']}")


if __name__ == "__main__":
    main()
