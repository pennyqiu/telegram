#!/usr/bin/env python3
"""
内容分析与分类模块
- 基于关键词匹配进行分类
- 提取摘要
- 计算内容相关度
"""

from typing import List, Dict
import re
from collections import Counter

from config import KEYWORDS
from crawler import Article


class ContentAnalyzer:
    """内容分析器"""
    
    def __init__(self):
        self.keywords = KEYWORDS
    
    def categorize(self, article: Article) -> str:
        """根据标题和摘要自动分类"""
        text = f"{article.title} {article.summary}".lower()
        
        scores = {}
        for category, keywords in self.keywords.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[category] = score
        
        if scores:
            return max(scores, key=scores.get)
        return "行业动态"
    
    def extract_keywords(self, article: Article, top_n: int = 5) -> List[str]:
        """提取关键词"""
        text = f"{article.title} {article.summary}"
        
        # 匹配所有已知关键词
        found = []
        for category_keywords in self.keywords.values():
            for kw in category_keywords:
                if kw in text:
                    found.append(kw)
        
        # 统计频次
        counter = Counter(found)
        return [kw for kw, _ in counter.most_common(top_n)]
    
    def calculate_relevance(self, article: Article, user_interests: List[str] = None) -> float:
        """计算文章相关度（0-1）"""
        if not user_interests:
            return 0.5
        
        text = f"{article.title} {article.summary}".lower()
        matches = sum(1 for interest in user_interests if interest.lower() in text)
        
        return min(matches / len(user_interests), 1.0)
    
    def analyze_batch(self, articles: List[Article]) -> List[Article]:
        """批量分析文章"""
        for article in articles:
            if not article.category or article.category == "未分类":
                article.category = self.categorize(article)
            
            if not article.keywords:
                article.keywords = self.extract_keywords(article)
        
        return articles
    
    def filter_by_relevance(self, articles: List[Article], 
                           threshold: float = 0.3,
                           user_interests: List[str] = None) -> List[Article]:
        """按相关度过滤"""
        filtered = []
        for article in articles:
            relevance = self.calculate_relevance(article, user_interests)
            if relevance >= threshold:
                filtered.append(article)
        
        return filtered
    
    def deduplicate(self, articles: List[Article]) -> List[Article]:
        """去重（基于标题相似度）"""
        seen_titles = set()
        unique = []
        
        for article in articles:
            # 简单去重：标题完全相同
            title_normalized = re.sub(r'\s+', '', article.title.lower())
            
            if title_normalized not in seen_titles:
                seen_titles.add(title_normalized)
                unique.append(article)
        
        return unique


def analyze_articles(articles: Dict[str, List[Article]], 
                    user_interests: List[str] = None) -> List[Article]:
    """分析并处理所有文章"""
    analyzer = ContentAnalyzer()
    
    # 合并所有来源
    all_articles = []
    for source_articles in articles.values():
        all_articles.extend(source_articles)
    
    print(f"📊 开始分析 {len(all_articles)} 篇文章...")
    
    # 去重
    all_articles = analyzer.deduplicate(all_articles)
    print(f"  → 去重后：{len(all_articles)} 篇")
    
    # 分类和提取关键词
    all_articles = analyzer.analyze_batch(all_articles)
    
    # 按相关度过滤（如果指定了兴趣）
    if user_interests:
        all_articles = analyzer.filter_by_relevance(all_articles, user_interests=user_interests)
        print(f"  → 相关度过滤后：{len(all_articles)} 篇")
    
    # 按发布时间排序
    all_articles.sort(key=lambda a: a.published, reverse=True)
    
    print(f"✅ 分析完成\n")
    
    return all_articles


if __name__ == "__main__":
    # 测试代码
    import json
    from datetime import datetime
    
    # 创建测试文章
    test_article = Article(
        title="香港保监局发布新规：强化储蓄险监管",
        url="https://example.com/news/1",
        source="测试来源",
        published=datetime.now(),
        summary="保监局今日宣布将加强对储蓄类保险产品的监管，要求保险公司提高信息披露透明度..."
    )
    
    analyzer = ContentAnalyzer()
    
    print("原始分类:", test_article.category)
    category = analyzer.categorize(test_article)
    print("自动分类:", category)
    
    keywords = analyzer.extract_keywords(test_article)
    print("关键词:", keywords)
    
    relevance = analyzer.calculate_relevance(test_article, ["监管", "储蓄险"])
    print("相关度:", relevance)
