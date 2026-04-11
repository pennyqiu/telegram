#!/usr/bin/env python3
"""
保险资讯周报 - 数据源配置
"""

# ============================================================
# RSS/API 数据源配置
# ============================================================

# 监管机构官方公告
REGULATORY_SOURCES = {
    "hk_ia": {
        "name": "香港保险业监管局",
        "url": "https://www.ia.org.hk/tc/infocenter/press_releases.html",
        "type": "html_scraper",  # 需要爬虫
        "priority": "high"
    },
    # 更多来源可以逐步添加
}

# 行业新闻媒体
NEWS_SOURCES = {
    "insurance_times": {
        "name": "保险时报",
        "rss": "https://www.insurancetimes.com.hk/feed",  # 示例
        "type": "rss",
        "priority": "medium"
    },
    # 可添加更多 RSS 源
}

# 社交媒体与内容平台
SOCIAL_SOURCES = {
    "zhihu_insurance": {
        "name": "知乎保险话题",
        "url": "https://www.zhihu.com/topic/19551824/hot",
        "type": "api",  # 需要知乎 API 或爬虫
        "keywords": ["香港保险", "储蓄险", "重疾险", "医疗险"],
        "priority": "medium"
    },
    "wechat_articles": {
        "name": "微信公众号精选",
        "type": "manual_curate",  # 手动收集优质账号的文章链接
        "accounts": [
            "精算师八卦",
            "保险岛",
            # 添加您关注的优质账号
        ],
        "priority": "high"
    }
}

# 数据与报告
DATA_SOURCES = {
    "hkfi": {
        "name": "香港金融研究院保险报告",
        "url": "https://www.hkfi.org.hk/publications",
        "type": "html_scraper",
        "frequency": "monthly",
        "priority": "medium"
    }
}

# ============================================================
# 关键词配置（用于内容过滤和分类）
# ============================================================

KEYWORDS = {
    "监管政策": ["监管", "政策", "合规", "牌照", "处罚"],
    "产品动态": ["新产品", "停售", "分红", "费率", "保费"],
    "市场数据": ["保费收入", "市场份额", "增长率", "理赔率"],
    "行业趋势": ["数字化", "科技保险", "ESG", "可持续"],
    "理赔案例": ["理赔", "拒赔", "争议", "判决", "诉讼"],
    "跨境保险": ["内地客户", "换汇", "传承", "信托", "税务"],
}

# ============================================================
# 爬虫配置
# ============================================================

CRAWLER_CONFIG = {
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "timeout": 10,
    "max_retries": 3,
    "rate_limit": 2,  # 每个请求间隔秒数
    "headers": {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
}

# ============================================================
# 简报生成配置
# ============================================================

BRIEFING_CONFIG = {
    "weekly": {
        "sections": [
            "监管政策速递",
            "产品与费率动态", 
            "市场数据洞察",
            "优质内容精选",
            "理赔案例分析",
        ],
        "items_per_section": 5,
    }
}
