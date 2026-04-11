#!/usr/bin/env python3
"""
保险资讯周报 - 数据源配置
"""

# ============================================================
# RSS/API 数据源配置
# ============================================================

# 启用的 RSS 数据源（真实可用）
ENABLED_RSS_SOURCES = {
    # 财经新闻 - 保险相关
    "caixin_insurance": {
        "name": "财新网-保险",
        "rss": "https://www.caixin.com/rss/insurance.xml",
        "type": "rss",
        "priority": "high",
        "keywords": ["保险", "保监会", "保费", "理赔"]
    },
    
    "sina_finance": {
        "name": "新浪财经-保险",
        "rss": "http://finance.sina.com.cn/roll/index.d.html?cid=56588",
        "type": "rss",
        "priority": "medium",
        "keywords": ["保险", "监管", "产品"]
    },
    
    # 如果上述 RSS 不可用，可以使用这些备用源
    "finance_163": {
        "name": "网易财经-保险",
        "rss": "http://money.163.com/special/00251LQH/rss_bx.xml",
        "type": "rss",
        "priority": "medium",
        "enabled": False  # 默认禁用，可手动启用
    },
}

# 监管机构官方公告（需要 HTML 爬虫）
REGULATORY_SOURCES = {
    "hk_ia": {
        "name": "香港保险业监管局",
        "url": "https://www.ia.org.hk/tc/infocenter/press_releases.html",
        "type": "html_scraper",
        "priority": "high",
        "enabled": False  # 默认禁用，需要完善爬虫逻辑
    },
}

# 社交媒体与内容平台（需要 API 或特殊处理）
SOCIAL_SOURCES = {
    "zhihu_insurance": {
        "name": "知乎保险话题",
        "url": "https://www.zhihu.com/topic/19551824/hot",
        "type": "api",
        "keywords": ["香港保险", "储蓄险", "重疾险", "医疗险"],
        "priority": "medium",
        "enabled": False  # 需要登录或 API
    },
}

# 手动添加的文章（通过 manual_curator.py）
MANUAL_ARTICLES_FILE = "manual_articles.json"

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
