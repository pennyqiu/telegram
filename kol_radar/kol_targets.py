#!/usr/bin/env python3
"""
KOL 目标清单（从用户提供的 targetKOLs.ts 移植）

每个 KOL 用 dataclass 表示，handle 已去除 '@'，方便拼接 URL / 调用 API。
新增 / 删除关注对象，只需修改下方 TARGET_KOLS 列表。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KOLProfile:
    name: str                  # 显示名
    handle: str                # X 用户名（不含 @）
    category: str              # 分类
    focus: str                 # 关注领域
    newsletter: str = ""       # 官方 newsletter / 博客名（无则留空）
    newsletter_rss: str = ""   # newsletter RSS 地址（免费全文源，无则留空）
    skip_tweets: bool = False  # True 则跳过 X 抓取（daily_cron / backfill 都不再调用 API），
                                # 用于确认该账号在 X 上没有原创内容、只值得走 newsletter 的情况
    skip_newsletter: bool = False  # True 则跳过 newsletter 抓取，用于确认其 newsletter 全是付费墙、
                                    # RSS 只给几十字摘要、拉下来没有分析价值的情况


# 与 KOLProfile.category 对应的中文标签（用于 HTML 分组展示）
CATEGORY_LABELS = {
    "Hardware & Semiconductor": "半导体与硬核硬件",
    "Software & Cloud": "AI 软件与云基础设施",
    "Macro & Applied Tech": "宏观与应用科技",
    "OSINT & Hyperscalers": "开源情报与超大规模厂商",
}


TARGET_KOLS = [
    # --- 1. 半导体与硬核硬件 ---
    KOLProfile(
        name="Dylan Patel",
        # 官方账号带下划线，不是 @SemiAnalysis（那个 handle 解析不到，会导致 x_api 报错）
        handle="SemiAnalysis_",
        category="Hardware & Semiconductor",
        focus="AI算力底层架构、先进封装(CoWoS)、超大规模计算中心CapEx跟踪",
        newsletter="SemiAnalysis",
        newsletter_rss="https://www.semianalysis.com/feed",
    ),
    KOLProfile(
        name="Fabricated Knowledge",
        # Doug O'Laughlin 的真实 X handle 是 @FoolAllTheTime（匿名推特），不是 @PhabulousFab；
        # handle 本身没问题（能正常解析用户），但实测无论最近推文还是半年历史回溯都是 0 条原创内容
        # （他基本只转发自己 newsletter 链接），X track 无增量价值，故关闭，只保留免费的 newsletter
        handle="FoolAllTheTime",
        category="Hardware & Semiconductor",
        focus="晶圆代工(TSMC/特种代工)、半导体设备(ASML/AMAT)财务模型与估值水位",
        newsletter="Fabricated Knowledge",
        newsletter_rss="https://www.fabricatedknowledge.com/feed",
        skip_tweets=True,
    ),
    KOLProfile(
        name="Serenity",
        handle="aleabitoreddit",
        category="Hardware & Semiconductor",
        focus="AI/半导体供应链「瓶颈理论」(Bottleneck Theory)：挖掘被忽视的上游关键供应商",
        # 前 Reddit WSB 交易者，本人声明「仅用 X 发布，谨防仿号」，无公开 newsletter
        newsletter="",
        newsletter_rss="",
    ),

    # --- 2. AI 软件、云基础设施与大盘科技 ---
    KOLProfile(
        name="Beth Kindig",
        handle="Beth_Kindig",
        category="Software & Cloud",
        focus="AI软件变现模型、大盘科技股买入区间(Buy Zones)测算",
        newsletter="I/O Fund",
        # 注：I/O Fund 2026-02 将关闭 Substack 迁回 io-fund.com，届时改这里
        newsletter_rss="https://iofund.substack.com/feed",
    ),
    KOLProfile(
        name="Jamin Ball",
        handle="jaminball",
        category="Software & Cloud",
        focus="SaaS估值倍数(EV/Forward Revenue)、云基础设施景气度",
        newsletter="Clouded Judgement",
        newsletter_rss="https://cloudedjudgement.substack.com/feed",
    ),

    # --- 3. 跨硬件/软件的综合科技投研 ---
    KOLProfile(
        name="Matthew Ball",
        handle="ballmatthew",
        category="Macro & Applied Tech",
        focus="3D引擎(Unreal/Unity)、空间计算、AI具身智能宏观推演",
        newsletter="MatthewBall.co Essays",
        # RSS 只给标题+十几个字的摘要（实测全是付费墙），拉下来的 excerpt 没有分析价值，
        # 故关闭 newsletter 抓取，只保留 X 实时推文这一路
        newsletter_rss="https://www.matthewball.co/all?format=rss",
        skip_newsletter=True,
    ),
    KOLProfile(
        name="itsone",
        handle="itsone",
        category="OSINT & Hyperscalers",
        focus="顶级对冲基金资金流向、大厂数据中心前沿开源情报(OSINT)",
        # OSINT 账号，无公开 newsletter；仅能走 X / 历史推文归档
        newsletter="",
        newsletter_rss="",
    ),
]
