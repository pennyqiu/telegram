#!/usr/bin/env python3
"""
金渐成文章爬虫 v2.0 - 使用 Playwright 处理动态加载
用途：个人学习存档 + 生成公开引用页面

⚖️ 法律声明：
- 本脚本下载的内容仅供个人学习研究使用
- 不得用于商业用途或公开传播
- 所有内容版权归原作者金渐成所有
- 请在获得授权后再进行大规模爬取
"""

import asyncio
import os
import json
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ==================== 配置 ====================
BASE_URL = "https://jinjiancheng.com"
OUT_DIR = os.path.join(os.path.dirname(__file__), "jinjiancheng_archive")
PRIVATE_DIR = os.path.join(OUT_DIR, "private")
PUBLIC_DIR = os.path.join(OUT_DIR, "public")
METADATA_FILE = os.path.join(OUT_DIR, "metadata.json")

# 礼貌爬取配置
DELAY = 3.0  # 每次请求间隔3秒
MAX_ARTICLES_PER_TOPIC = 100  # 每个主题最多爬取100篇（完整模式）

# 主题配置
TOPICS = {
    "美股": {
        "url": f"{BASE_URL}/topics/us-stocks",
        "slug": "us-stocks",
        "icon": "📈",
        "description": "美股投资、科技股、纳指与标普配置"
    },
    "港股": {
        "url": f"{BASE_URL}/topics/hk-stocks",
        "slug": "hk-stocks",
        "icon": "🇭🇰",
        "description": "港股、腾讯及相关仓位调整"
    },
    "比特币": {
        "url": f"{BASE_URL}/topics/crypto-bitcoin",
        "slug": "crypto-bitcoin",
        "icon": "₿",
        "description": "比特币、加密货币与链上资产"
    },
    "黄金": {
        "url": f"{BASE_URL}/topics/gold",
        "slug": "gold",
        "icon": "🥇",
        "description": "黄金、贵金属和防守型配置"
    },
    "房地产": {
        "url": f"{BASE_URL}/topics/real-estate",
        "slug": "real-estate",
        "icon": "🏢",
        "description": "房地产、楼市、房企与救市政策"
    },
    "债务": {
        "url": f"{BASE_URL}/topics/debt-crisis",
        "slug": "debt-crisis",
        "icon": "📉",
        "description": "债务、暴雷、违约与信用风险"
    },
    "职场": {
        "url": f"{BASE_URL}/topics/workplace",
        "slug": "workplace",
        "icon": "💼",
        "description": "裁员、欠薪、职场与就业"
    },
    "A股": {
        "url": f"{BASE_URL}/topics/a-shares",
        "slug": "a-shares",
        "icon": "📊",
        "description": "A股、消费股与国内权益市场"
    }
}


def ensure_dirs():
    """创建必要的目录结构"""
    os.makedirs(PRIVATE_DIR, exist_ok=True)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    for topic_info in TOPICS.values():
        os.makedirs(os.path.join(PRIVATE_DIR, topic_info["slug"]), exist_ok=True)


async def extract_articles_from_topic(page, topic_name, topic_info):
    """从主题页面提取文章列表"""
    print(f"\n{'='*60}")
    print(f"🔍 正在爬取: {topic_info['icon']} {topic_name}")
    print(f"{'='*60}")
    
    url = topic_info['url']
    print(f"访问: {url}")
    
    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)  # 等待动态内容加载
        
        # 提取文章链接（金渐成网站使用 /articles/jinjiancheng/ 格式）
        articles = await page.evaluate("""
            () => {
                const articles = [];
                const seen = new Set();
                
                // 查找所有包含 /articles/jinjiancheng/ 的链接
                const links = document.querySelectorAll('a[href*="/articles/jinjiancheng/"]');
                
                links.forEach(link => {
                    const href = link.href;
                    const title = link.textContent.trim();
                    
                    // 过滤掉日期链接（只有日期没有标题的）
                    if (href && title && title.length > 5 && !title.match(/^\d{2}-\d{2}$/) && !seen.has(href)) {
                        seen.add(href);
                        articles.push({
                            url: href,
                            title: title.substring(0, 200)
                        });
                    }
                });
                
                return articles;
            }
        """)
        
        print(f"✓ 找到 {len(articles)} 篇文章")
        
        # 限制数量
        if len(articles) > MAX_ARTICLES_PER_TOPIC:
            print(f"⚠️  限制为前 {MAX_ARTICLES_PER_TOPIC} 篇（可在配置中调整）")
            articles = articles[:MAX_ARTICLES_PER_TOPIC]
        
        return articles
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        return []


async def download_article(page, article_url, topic_slug):
    """下载单篇文章内容"""
    print(f"\n  → 下载: {article_url}")
    
    try:
        await page.goto(article_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1)
        
        # 提取文章内容
        article_data = await page.evaluate("""
            () => {
                const data = {
                    url: window.location.href,
                    title: '',
                    date: '',
                    content: '',
                    excerpt: ''
                };
                
                // 提取标题
                const titleEl = document.querySelector('h1') || document.querySelector('title');
                if (titleEl) {
                    data.title = titleEl.textContent.trim();
                }
                
                // 提取日期
                const dateEl = document.querySelector('time') || 
                              document.querySelector('.date') ||
                              document.querySelector('[datetime]');
                if (dateEl) {
                    data.date = dateEl.textContent.trim() || dateEl.getAttribute('datetime') || '';
                }
                
                // 提取正文
                const contentEl = document.querySelector('article') ||
                                 document.querySelector('.content') ||
                                 document.querySelector('.post-content') ||
                                 document.querySelector('main');
                if (contentEl) {
                    data.content = contentEl.textContent.trim();
                    // 生成摘要（前300字）
                    data.excerpt = data.content.substring(0, 300) + '...';
                }
                
                return data;
            }
        """)
        
        if article_data['title']:
            # 保存为 markdown（私人存档）
            safe_title = "".join(c for c in article_data['title'][:50] if c.isalnum() or c in (' ', '-', '_')).strip()
            filename = f"{safe_title}.md".replace(' ', '_')
            filepath = os.path.join(PRIVATE_DIR, topic_slug, filename)
            
            md_content = f"""# {article_data['title']}

> 原文链接: {article_data['url']}  
> 发布日期: {article_data.get('date', '未知')}  
> 作者: 金渐成  
> 存档时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{article_data['content']}

---

**⚖️ 版权声明**: 本文内容版权归原作者金渐成所有。本地存档仅供个人学习研究使用，不得用于商业用途或公开传播。
"""
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            print(f"  ✓ 已保存: {filename}")
            
            # 等待，避免请求过快
            await asyncio.sleep(DELAY)
            
            return article_data
        
    except Exception as e:
        print(f"  ✗ 错误: {e}")
    
    return None


async def main():
    """主流程"""
    print("\n" + "="*60)
    print("📚 金渐成文章爬虫 v2.0")
    print("="*60)
    print("\n⚖️  法律声明:")
    print("   本工具仅供个人学习研究使用")
    print("   所有内容版权归原作者所有")
    print("   请勿用于商业用途或公开传播\n")
    
    # 用户确认
    print("⚠️  注意事项:")
    print(f"   - 每个主题最多爬取 {MAX_ARTICLES_PER_TOPIC} 篇文章")
    print(f"   - 请求间隔 {DELAY} 秒，避免给服务器造成压力")
    print(f"   - 预计总耗时: 约 {len(TOPICS) * MAX_ARTICLES_PER_TOPIC * DELAY / 60:.0f} 分钟\n")
    
    response = input("是否继续？(y/n): ")
    if response.lower() != 'y':
        print("已取消")
        return
    
    ensure_dirs()
    all_articles = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 爬取各主题
        for topic_name, topic_info in TOPICS.items():
            articles_list = await extract_articles_from_topic(page, topic_name, topic_info)
            
            # 下载每篇文章
            for article in articles_list:
                article_data = await download_article(page, article['url'], topic_info['slug'])
                if article_data:
                    article_data['topic'] = topic_name
                    article_data['topic_icon'] = topic_info['icon']
                    all_articles.append(article_data)
        
        await browser.close()
    
    # 保存元数据
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 爬取完成! 共 {len(all_articles)} 篇文章")
    print(f"✓ 元数据已保存: {METADATA_FILE}")
    
    # 生成公开引用页面
    generate_public_page(all_articles)


def generate_public_page(all_articles):
    """生成公开引用页面（仅链接，不含全文）"""
    print(f"\n{'='*60}")
    print("📝 生成公开引用页面...")
    print(f"{'='*60}")
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>金渐成投资方法论专题 · 学习导航</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
    line-height: 1.7;
    color: #1f2937;
    background: #f9fafb;
    padding: 20px;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
.header {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 60px 40px;
    border-radius: 20px;
    margin-bottom: 40px;
    box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3);
}}
.header h1 {{ font-size: 42px; margin-bottom: 16px; font-weight: 700; }}
.disclaimer {{
    background: #fef3c7;
    border-left: 4px solid #f59e0b;
    padding: 20px 24px;
    border-radius: 12px;
    margin-bottom: 40px;
}}
.topic-section {{
    background: white;
    padding: 40px;
    border-radius: 16px;
    margin-bottom: 30px;
    box-shadow: 0 2px 20px rgba(0,0,0,0.06);
}}
.topic-header {{
    display: flex;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 2px solid #e5e7eb;
}}
.topic-icon {{ font-size: 36px; margin-right: 16px; }}
.topic-title {{ font-size: 28px; font-weight: 700; }}
.article-item {{
    padding: 20px;
    border-radius: 12px;
    margin-bottom: 12px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    transition: all 0.2s;
}}
.article-item:hover {{
    background: #f3f4f6;
    border-color: #667eea;
    transform: translateX(4px);
}}
.article-title a {{
    color: #667eea;
    text-decoration: none;
    font-size: 17px;
    font-weight: 600;
}}
.article-title a:hover {{ text-decoration: underline; }}
.article-meta {{ font-size: 13px; color: #9ca3af; margin-top: 8px; }}
.footer {{ text-align: center; padding: 40px; color: #9ca3af; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📚 金渐成投资方法论专题</h1>
    <p>个人学习资料导航 · 共收录 {len(all_articles)} 篇文章</p>
  </div>
  
  <div class="disclaimer">
    <strong>⚖️ 版权声明</strong><br>
    本页面所列文章版权归原作者<strong>金渐成</strong>所有。所有内容通过链接引用至原网站，
    未进行转载。本导航仅供个人学习研究使用。
    <br><br>
    原网站: <a href="https://jinjiancheng.com" target="_blank" style="color:#d97706;text-decoration:underline;">jinjiancheng.com</a>
  </div>
"""
    
    # 按主题组织
    for topic_name, topic_info in TOPICS.items():
        topic_articles = [a for a in all_articles if a.get('topic') == topic_name]
        
        if not topic_articles:
            continue
        
        html += f"""
  <div class="topic-section">
    <div class="topic-header">
      <span class="topic-icon">{topic_info['icon']}</span>
      <h2 class="topic-title">{topic_name} ({len(topic_articles)}篇)</h2>
    </div>
    <ul style="list-style:none;">
"""
        
        for article in topic_articles:
            html += f"""
      <li class="article-item">
        <div class="article-title">
          <a href="{article['url']}" target="_blank" rel="noopener">
            {article.get('title', '无标题')} 🔗
          </a>
        </div>
        <div class="article-meta">
          {article.get('date', '未知日期')} · 
          <a href="{article['url']}" target="_blank" style="color:#667eea;">阅读原文</a>
        </div>
      </li>
"""
        
        html += "    </ul>\n  </div>\n"
    
    html += f"""
  <div class="footer">
    <p>生成于 {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
    <p style="margin-top:8px;">数据来源: <a href="https://jinjiancheng.com/topics" target="_blank" style="color:#667eea;">jinjiancheng.com/topics</a></p>
  </div>
</div>
</body>
</html>
"""
    
    output_path = os.path.join(PUBLIC_DIR, "index.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✓ 公开引用页面: {output_path}")
    print(f"✓ 私人存档目录: {PRIVATE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
