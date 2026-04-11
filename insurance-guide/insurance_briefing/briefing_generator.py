#!/usr/bin/env python3
"""
保险资讯周报生成器
参考 investment_tracker 的架构，生成 HTML 简报
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict
from collections import defaultdict

from config import BRIEFING_CONFIG
from crawler import Article, crawl_all_sources
from analyzer import analyze_articles


class BriefingGenerator:
    """简报生成器"""
    
    def __init__(self, output_dir: str = "."):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_weekly(self, articles: List[Article]) -> str:
        """生成每周简报 HTML"""
        
        # 按分类分组
        by_category = defaultdict(list)
        for article in articles:
            by_category[article.category].append(article)
        
        # 生成 HTML
        html = self._generate_html_header("保险资讯周报")
        
        # 摘要统计
        html += f"""
        <div class="summary-stats">
            <div class="stat-card">
                <h3>{len(articles)}</h3>
                <p>本周资讯</p>
            </div>
            <div class="stat-card">
                <h3>{len(by_category)}</h3>
                <p>覆盖分类</p>
            </div>
            <div class="stat-card">
                <h3>{len(set(a.source for a in articles))}</h3>
                <p>数据源</p>
            </div>
        </div>
        """
        
        # 按配置的章节顺序生成内容
        sections = BRIEFING_CONFIG['weekly']['sections']
        items_per_section = BRIEFING_CONFIG['weekly']['items_per_section']
        
        for section_title in sections:
            articles_in_section = by_category.get(section_title, [])[:items_per_section]
            
            if articles_in_section:
                html += self._generate_section(section_title, articles_in_section)
        
        # 其他未分类内容
        other_categories = set(by_category.keys()) - set(sections)
        for category in sorted(other_categories):
            articles_in_section = by_category[category][:items_per_section]
            html += self._generate_section(category, articles_in_section)
        
        html += self._generate_html_footer()
        
        return html
    
    def _generate_html_header(self, title: str) -> str:
        """生成 HTML 头部"""
        week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = datetime.now().strftime("%Y-%m-%d")
        
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | {week_start} 至 {week_end}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }}
        
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header .date-range {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .summary-stats {{
            display: flex;
            justify-content: space-around;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .stat-card {{
            text-align: center;
        }}
        
        .stat-card h3 {{
            font-size: 2.5em;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stat-card p {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            margin-bottom: 50px;
        }}
        
        .section-title {{
            font-size: 1.8em;
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        
        .article {{
            margin-bottom: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            transition: all 0.3s ease;
        }}
        
        .article:hover {{
            background: #e9ecef;
            transform: translateX(5px);
        }}
        
        .article-title {{
            font-size: 1.3em;
            font-weight: 600;
            margin-bottom: 10px;
        }}
        
        .article-title a {{
            color: #333;
            text-decoration: none;
        }}
        
        .article-title a:hover {{
            color: #667eea;
        }}
        
        .article-meta {{
            font-size: 0.9em;
            color: #6c757d;
            margin-bottom: 10px;
        }}
        
        .article-meta span {{
            margin-right: 15px;
        }}
        
        .article-summary {{
            color: #495057;
            line-height: 1.8;
        }}
        
        .keywords {{
            margin-top: 10px;
        }}
        
        .keyword {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            margin-right: 8px;
            margin-top: 5px;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 30px;
            text-align: center;
            color: #6c757d;
            border-top: 1px solid #e9ecef;
        }}
        
        @media (max-width: 768px) {{
            .summary-stats {{
                flex-direction: column;
                gap: 20px;
            }}
            
            .content {{
                padding: 20px;
            }}
            
            .header h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 {title}</h1>
            <div class="date-range">{week_start} 至 {week_end}</div>
        </div>
"""
    
    def _generate_section(self, title: str, articles: List[Article]) -> str:
        """生成一个章节"""
        html = f"""
        <div class="section">
            <h2 class="section-title">{title}</h2>
"""
        
        for article in articles:
            published_str = article.published.strftime("%Y-%m-%d")
            
            keywords_html = "".join(
                f'<span class="keyword">{kw}</span>' 
                for kw in article.keywords[:5]
            )
            
            html += f"""
            <div class="article">
                <div class="article-title">
                    <a href="{article.url}" target="_blank">{article.title}</a>
                </div>
                <div class="article-meta">
                    <span>📅 {published_str}</span>
                    <span>📰 {article.source}</span>
                </div>
                <div class="article-summary">
                    {article.summary or '点击查看详情'}
                </div>
                <div class="keywords">
                    {keywords_html}
                </div>
            </div>
"""
        
        html += """
        </div>
"""
        return html
    
    def _generate_html_footer(self) -> str:
        """生成 HTML 尾部"""
        return f"""
        </div>
        <div class="footer">
            <p>本简报由自动化系统生成</p>
            <p>生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
    </div>
</body>
</html>
"""
    
    def save_briefing(self, html: str, filename: str = "weekly.html") -> str:
        """保存简报到文件"""
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # 同时保存历史快照
        date_str = datetime.now().strftime("%Y%m%d")
        snapshot_filename = f"briefing_weekly_{date_str}.html"
        snapshot_path = os.path.join(self.output_dir, snapshot_filename)
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return filepath


def main():
    """主流程"""
    import argparse
    
    parser = argparse.ArgumentParser(description="保险资讯周报生成器")
    parser.add_argument("--days", type=int, default=7, help="爬取最近几天的资讯")
    parser.add_argument("--output", type=str, default="./output", help="输出目录")
    parser.add_argument("--interests", nargs="+", help="用户兴趣关键词（可选）")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("   保险资讯周报自动化系统")
    print("=" * 60)
    print()
    
    # 1. 爬取数据
    raw_articles = crawl_all_sources(days=args.days)
    
    # 2. 分析内容
    analyzed_articles = analyze_articles(raw_articles, user_interests=args.interests)
    
    if not analyzed_articles:
        print("⚠️  没有爬取到任何资讯，请检查数据源配置")
        sys.exit(1)
    
    # 3. 生成简报
    print(f"📝 生成简报...")
    generator = BriefingGenerator(output_dir=args.output)
    html = generator.generate_weekly(analyzed_articles)
    filepath = generator.save_briefing(html)
    
    date_str = datetime.now().strftime("%Y%m%d")
    snapshot_file = f"briefing_weekly_{date_str}.html"
    
    print(f"\n✅ 简报已生成：{filepath}")
    print(f"   历史快照：{os.path.join(args.output, snapshot_file)}")
    
    # 4. 生成索引页（方便浏览历史）
    generate_index(args.output)
    print(f"   索引页面：{os.path.join(args.output, 'index.html')}")
    
    print("\n" + "=" * 60)


def generate_index(output_dir: str):
    """生成历史简报索引页"""
    import glob
    
    # 找到所有历史简报文件
    pattern = os.path.join(output_dir, "briefing_weekly_*.html")
    files = sorted(glob.glob(pattern), reverse=True)
    
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>保险资讯周报 - 历史归档</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #667eea;
            text-align: center;
        }
        .latest {
            background: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .latest a {
            display: block;
            font-size: 1.5em;
            color: #667eea;
            text-decoration: none;
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .latest a:hover {
            background: #e9ecef;
        }
        .archive {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .archive h2 {
            color: #495057;
            margin-bottom: 20px;
        }
        .archive ul {
            list-style: none;
        }
        .archive li {
            padding: 10px 0;
            border-bottom: 1px solid #e9ecef;
        }
        .archive li:last-child {
            border-bottom: none;
        }
        .archive a {
            color: #333;
            text-decoration: none;
        }
        .archive a:hover {
            color: #667eea;
        }
    </style>
</head>
<body>
    <h1>🏥 保险资讯周报</h1>
    
    <div class="latest">
        <a href="weekly.html">📊 查看最新一期周报</a>
    </div>
    
    <div class="archive">
        <h2>📁 历史归档</h2>
        <ul>
"""
    
    for file in files:
        basename = os.path.basename(file)
        # 从文件名提取日期：briefing_weekly_20260411.html
        date_str = basename.replace("briefing_weekly_", "").replace(".html", "")
        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            display_date = date_obj.strftime("%Y年%m月%d日")
        except:
            display_date = date_str
        
        html += f'            <li><a href="{basename}">📄 {display_date} 周报</a></li>\n'
    
    html += """
        </ul>
    </div>
</body>
</html>
"""
    
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)


if __name__ == "__main__":
    main()
