"""
保险资讯周报系统

模块说明：
- config.py: 数据源和关键词配置
- crawler.py: 网络爬虫（RSS、HTML）
- analyzer.py: 内容分析与分类
- briefing_generator.py: 简报生成（主程序）
- manual_curator.py: 手动添加优质文章
- demo.py: 快速演示（使用模拟数据）
"""

__version__ = "1.0.0"
__author__ = "Your Name"

from .crawler import Article, crawl_all_sources
from .analyzer import analyze_articles
from .briefing_generator import BriefingGenerator

__all__ = [
    "Article",
    "crawl_all_sources",
    "analyze_articles",
    "BriefingGenerator",
]
