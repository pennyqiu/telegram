#!/usr/bin/env python3
"""
手动精选文章工具
适用于无法自动爬取的优质内容源（如微信公众号、需要登录的平台）
"""

import json
from datetime import datetime
from crawler import Article


def manual_add_article():
    """交互式添加文章"""
    print("\n" + "=" * 60)
    print("手动添加优质文章")
    print("=" * 60 + "\n")
    
    title = input("📝 标题: ").strip()
    url = input("🔗 链接: ").strip()
    source = input("📰 来源: ").strip()
    
    date_str = input("📅 发布日期 (YYYY-MM-DD, 留空为今天): ").strip()
    if date_str:
        try:
            published = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            print("  ⚠️  日期格式错误，使用今天")
            published = datetime.now()
    else:
        published = datetime.now()
    
    summary = input("💬 简介 (可选): ").strip()
    category = input("🏷️  分类 (可选): ").strip()
    keywords_input = input("🔖 关键词 (逗号分隔, 可选): ").strip()
    
    keywords = [k.strip() for k in keywords_input.split(",")] if keywords_input else []
    
    article = Article(
        title=title,
        url=url,
        source=source,
        published=published,
        summary=summary,
        category=category or "未分类",
        keywords=keywords
    )
    
    return article


def load_manual_articles(filepath: str = "manual_articles.json") -> list:
    """加载已保存的手动文章"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [
                Article(
                    title=item['title'],
                    url=item['url'],
                    source=item['source'],
                    published=datetime.fromisoformat(item['published']),
                    summary=item.get('summary', ''),
                    category=item.get('category', '未分类'),
                    keywords=item.get('keywords', [])
                )
                for item in data
            ]
    except FileNotFoundError:
        return []


def save_manual_articles(articles: list, filepath: str = "manual_articles.json"):
    """保存手动文章到 JSON"""
    data = [article.to_dict() for article in articles]
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    """主程序"""
    import os
    
    filepath = "manual_articles.json"
    articles = load_manual_articles(filepath)
    
    print(f"\n当前已保存 {len(articles)} 篇手动添加的文章\n")
    
    while True:
        choice = input("请选择操作：\n  1. 添加新文章\n  2. 查看已添加\n  3. 完成并保存\n\n输入选项: ").strip()
        
        if choice == "1":
            article = manual_add_article()
            articles.append(article)
            print(f"\n✅ 已添加：{article.title}\n")
        
        elif choice == "2":
            if not articles:
                print("\n  还没有添加任何文章\n")
            else:
                print("\n" + "=" * 60)
                for i, article in enumerate(articles, 1):
                    print(f"\n{i}. {article.title}")
                    print(f"   来源: {article.source}")
                    print(f"   链接: {article.url}")
                    print(f"   日期: {article.published.strftime('%Y-%m-%d')}")
                print("\n" + "=" * 60 + "\n")
        
        elif choice == "3":
            save_manual_articles(articles, filepath)
            print(f"\n✅ 已保存 {len(articles)} 篇文章到 {filepath}\n")
            print("提示：运行 briefing_generator.py 时会自动包含这些文章\n")
            break
        
        else:
            print("\n  ⚠️  无效选项\n")


if __name__ == "__main__":
    main()
