#!/usr/bin/env python3
"""
保险资讯爬虫模块
支持 RSS、HTML 解析、API 调用等多种方式
"""

import time
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

try:
    import requests
    import feedparser
    from bs4 import BeautifulSoup
except ImportError:
    print("请先安装依赖：pip install requests feedparser beautifulsoup4 lxml")
    exit(1)

from config import CRAWLER_CONFIG


class Article:
    """文章数据结构"""
    def __init__(self, title: str, url: str, source: str, 
                 published: datetime, summary: str = "", 
                 category: str = "未分类", keywords: List[str] = None):
        self.title = title
        self.url = url
        self.source = source
        self.published = published
        self.summary = summary
        self.category = category
        self.keywords = keywords or []
        self.id = self._generate_id()
    
    def _generate_id(self) -> str:
        """基于 URL 生成唯一 ID"""
        return hashlib.md5(self.url.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published": self.published.isoformat(),
            "summary": self.summary,
            "category": self.category,
            "keywords": self.keywords,
        }


class BaseCrawler:
    """爬虫基类"""
    def __init__(self, name: str):
        self.name = name
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": CRAWLER_CONFIG["user_agent"],
            **CRAWLER_CONFIG["headers"]
        })
    
    def fetch(self, url: str, method: str = "GET", **kwargs) -> requests.Response:
        """发起 HTTP 请求，带重试机制"""
        for attempt in range(CRAWLER_CONFIG["max_retries"]):
            try:
                resp = self.session.request(
                    method, url, 
                    timeout=CRAWLER_CONFIG["timeout"],
                    **kwargs
                )
                resp.raise_for_status()
                time.sleep(CRAWLER_CONFIG["rate_limit"])
                return resp
            except Exception as e:
                if attempt == CRAWLER_CONFIG["max_retries"] - 1:
                    print(f"❌ [{self.name}] 请求失败: {url} - {e}")
                    raise
                time.sleep(2 ** attempt)
        
    def crawl(self, days: int = 7) -> List[Article]:
        """子类实现具体爬取逻辑"""
        raise NotImplementedError


class RSSCrawler(BaseCrawler):
    """RSS 订阅爬虫"""
    def __init__(self, name: str, rss_url: str):
        super().__init__(name)
        self.rss_url = rss_url
    
    def crawl(self, days: int = 7) -> List[Article]:
        """解析 RSS 订阅"""
        try:
            feed = feedparser.parse(self.rss_url)
            articles = []
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for entry in feed.entries:
                # 解析发布时间
                published = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else datetime.now()
                
                if published < cutoff_date:
                    continue
                
                article = Article(
                    title=entry.title,
                    url=entry.link,
                    source=self.name,
                    published=published,
                    summary=entry.get('summary', '')[:200],
                )
                articles.append(article)
            
            print(f"  ✓ [{self.name}] 获取到 {len(articles)} 篇文章")
            return articles
        
        except Exception as e:
            print(f"  ✗ [{self.name}] RSS 解析失败: {e}")
            return []


class HKIACrawler(BaseCrawler):
    """香港保监局新闻爬虫"""
    def __init__(self):
        super().__init__("香港保监局")
        self.base_url = "https://www.ia.org.hk"
    
    def crawl(self, days: int = 7) -> List[Article]:
        """爬取保监局新闻"""
        try:
            url = f"{self.base_url}/tc/infocenter/press_releases.html"
            resp = self.fetch(url)
            soup = BeautifulSoup(resp.content, 'lxml')
            
            articles = []
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 这里需要根据实际页面结构调整选择器
            news_items = soup.select(".news-item")  # 示例选择器
            
            for item in news_items[:10]:  # 只取最新 10 条
                try:
                    title_elem = item.select_one(".title")
                    date_elem = item.select_one(".date")
                    link_elem = item.select_one("a")
                    
                    if not all([title_elem, date_elem, link_elem]):
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    date_str = date_elem.get_text(strip=True)
                    link = link_elem['href']
                    
                    # 处理相对链接
                    if link.startswith('/'):
                        link = self.base_url + link
                    
                    # 解析日期（根据实际格式调整）
                    published = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if published < cutoff_date:
                        continue
                    
                    article = Article(
                        title=title,
                        url=link,
                        source=self.name,
                        published=published,
                        category="监管政策"
                    )
                    articles.append(article)
                
                except Exception as e:
                    print(f"  ⚠ 解析单条新闻失败: {e}")
                    continue
            
            print(f"  ✓ [{self.name}] 获取到 {len(articles)} 篇新闻")
            return articles
        
        except Exception as e:
            print(f"  ✗ [{self.name}] 爬取失败: {e}")
            return []


class ZhihuCrawler(BaseCrawler):
    """知乎热门话题爬虫（示例，需要实际 API 或登录）"""
    def __init__(self):
        super().__init__("知乎保险话题")
        # 注意：知乎有反爬机制，建议使用官方 API 或人工精选
    
    def crawl(self, days: int = 7) -> List[Article]:
        """获取知乎热门回答"""
        # 这里是伪代码示例
        # 实际使用中可能需要：
        # 1. 登录态 cookies
        # 2. 调用知乎 API
        # 3. 或者手动收集链接后解析
        
        print(f"  ⚠ [{self.name}] 暂不支持自动爬取，建议手动精选内容")
        return []


def crawl_all_sources(days: int = 7) -> Dict[str, List[Article]]:
    """爬取所有配置的数据源"""
    print(f"\n📡 开始爬取保险资讯（最近 {days} 天）...\n")
    
    results = {}
    
    # RSS 源爬取
    # results['rss'] = RSSCrawler("保险时报", "https://example.com/feed").crawl(days)
    
    # 监管机构
    results['hkia'] = HKIACrawler().crawl(days)
    
    # 社交媒体（需要特殊处理）
    # results['zhihu'] = ZhihuCrawler().crawl(days)
    
    # 统计总数
    total = sum(len(articles) for articles in results.values())
    print(f"\n✅ 爬取完成，共获取 {total} 篇文章\n")
    
    return results


if __name__ == "__main__":
    # 测试运行
    articles = crawl_all_sources(days=7)
    
    # 保存到 JSON
    output = {}
    for source, article_list in articles.items():
        output[source] = [a.to_dict() for a in article_list]
    
    with open("articles_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print("✅ 数据已保存到 articles_raw.json")
