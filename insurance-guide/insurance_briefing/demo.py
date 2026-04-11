#!/usr/bin/env python3
"""
修复 demo.py，使其支持命令行参数
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import List

# 导入必要的模块（不依赖外部库，避免安装失败）
try:
    from crawler import Article
    from briefing_generator import BriefingGenerator
except ImportError:
    # 如果导入失败，定义简单版本
    from datetime import datetime
    
    class Article:
        def __init__(self, title, url, source, published, summary="", category="未分类", keywords=None):
            self.title = title
            self.url = url
            self.source = source
            self.published = published
            self.summary = summary
            self.category = category
            self.keywords = keywords or []


def create_sample_articles():
    """创建示例文章数据"""
    
    base_date = datetime.now()
    
    articles = [
        # 监管政策（使用真实可访问的链接）
        Article(
            title="香港保监局发布2026年新规：强化储蓄险监管",
            url="https://www.ia.org.hk/tc/index.html",
            source="香港保险业监管局",
            published=base_date - timedelta(days=1),
            summary="保监局今日宣布将加强对储蓄类保险产品的监管，要求保险公司提高信息披露透明度，特别是分红实现率和历史业绩数据。新规将于2026年7月1日起实施。",
            category="监管政策速递",
            keywords=["监管", "储蓄险", "分红", "信息披露"]
        ),
        
        Article(
            title="内地银保监会：跨境保险需加强反洗钱审查",
            url="https://www.cbirc.gov.cn/cn/view/pages/index/index.html",
            source="财新网",
            published=base_date - timedelta(days=2),
            summary="监管部门要求各保险公司加强对跨境保单的客户身份识别和资金来源审查，防范洗钱风险。",
            category="监管政策速递",
            keywords=["跨境保险", "反洗钱", "合规"]
        ),
        
        # 产品动态（使用真实可访问的链接）
        Article(
            title="友邦推出新医疗险「智选健康保」，首年保费8折优惠",
            url="https://www.aia.com.hk/zh-hk.html",
            source="友邦香港",
            published=base_date - timedelta(days=3),
            summary="友邦推出全新医疗保险产品，涵盖门诊、住院、手术等全方位保障，支持全球理赔网络。首年保费8折，限时推广至5月底。",
            category="产品与费率动态",
            keywords=["医疗险", "新产品", "友邦", "优惠"]
        ),
        
        Article(
            title="保诚「隽富」系列分红实现率公布：2025年达106%",
            url="https://www.prudential.com.hk/tc/",
            source="保诚香港",
            published=base_date - timedelta(days=4),
            summary="保诚公布旗下储蓄险产品隽富系列2025年度分红实现率为106%，超出演示利率，连续5年达标。",
            category="产品与费率动态",
            keywords=["分红", "储蓄险", "保诚", "分红实现率"]
        ),
        
        # 市场数据（使用真实可访问的链接）
        Article(
            title="2025年香港保费收入同比增长12%，内地客户占比25%",
            url="https://www.hkfi.org.hk/",
            source="香港保险业联会",
            published=base_date - timedelta(days=2),
            summary="根据最新统计，2025年全年香港保险业保费收入达5800亿港元，其中内地客户贡献约1450亿港元，占比25%。储蓄险和医疗险增长最为强劲。",
            category="市场数据洞察",
            keywords=["保费收入", "市场份额", "内地客户", "增长"]
        ),
        
        # 优质内容（使用真实可访问的链接）
        Article(
            title="精算师深度解析：储蓄险的「保证」与「非保证」收益",
            url="https://www.zhihu.com/topic/19551824/hot",
            source="微信公众号·精算师八卦",
            published=base_date - timedelta(days=5),
            summary="本文从精算角度详细解释储蓄险产品说明书中的保证收益和非保证收益的区别，以及如何理性看待分红演示。建议客户重点关注保证部分和历史分红实现率。",
            category="优质内容精选",
            keywords=["储蓄险", "精算", "分红", "保证收益"]
        ),
        
        Article(
            title="会计师谈保险：如何用财务思维配置家庭保障",
            url="https://www.zhihu.com/topic/19551824/hot",
            source="知乎·保险话题",
            published=base_date - timedelta(days=6),
            summary="作为会计师，我从资产配置的角度分析家庭保险需求。保险的本质是风险管理工具，而非投资工具。建议优先配置重疾险和医疗险，再考虑储蓄险。",
            category="优质内容精选",
            keywords=["资产配置", "会计师", "家庭保障", "风险管理"]
        ),
        
        # 理赔案例（使用真实可访问的链接）
        Article(
            title="案例分析：重疾险理赔争议 - 「原位癌」是否赔付",
            url="https://www.ia.org.hk/tc/consumer_corner/index.html",
            source="保险纠纷案例库",
            published=base_date - timedelta(days=3),
            summary="客户购买重疾险后确诊甲状腺原位癌，保险公司以「不属于重疾定义」为由拒赔。法院最终判决：需根据保单条款中对「癌症」的明确定义判断，提醒消费者购买前仔细阅读条款。",
            category="理赔案例分析",
            keywords=["理赔", "重疾险", "原位癌", "拒赔", "案例"]
        ),
        
        Article(
            title="跨境医疗理赔成功案例：香港保单在内地就医获全额赔付",
            url="https://www.ia.org.hk/tc/consumer_corner/index.html",
            source="保险经纪人分享",
            published=base_date - timedelta(days=7),
            summary="客户在内地三甲医院就医，凭借完整的医疗报告和发票，成功获得香港医疗保单全额理赔。分享理赔流程和注意事项。",
            category="理赔案例分析",
            keywords=["跨境理赔", "医疗险", "理赔", "案例"]
        ),
    ]
    
    return articles


def main():
    """生成示例简报"""
    parser = argparse.ArgumentParser(description="生成保险简报演示")
    parser.add_argument("--output", type=str, default="./demo_output", help="输出目录")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("   生成示例简报（使用模拟数据）")
    print("=" * 60 + "\n")
    
    # 创建示例数据
    articles = create_sample_articles()
    print(f"✅ 创建了 {len(articles)} 篇示例文章\n")
    
    # 生成简报
    try:
        from briefing_generator import BriefingGenerator
        generator = BriefingGenerator(output_dir=args.output)
        html = generator.generate_weekly(articles)
        filepath = generator.save_briefing(html, filename="demo_weekly.html")
        
        print(f"✅ 示例简报已生成：{filepath}\n")
        print("提示：用浏览器打开查看效果\n")
    except Exception as e:
        print(f"⚠️  生成失败：{e}")
        print("请确保已安装依赖：pip3 install -r requirements.txt")
        sys.exit(1)
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
