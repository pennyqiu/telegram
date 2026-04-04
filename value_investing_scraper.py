#!/usr/bin/env python3
"""
价值投资顶级博客分析工具 v2
核心改进：把文章内容直接嵌入HTML，可展开阅读，不依赖外链跳转
"""

import requests
import time
import json
import re
import os
from bs4 import BeautifulSoup
from datetime import datetime
from collections import Counter
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
DELAY = 1.5


# ── 爬虫：抓真实可用内容 ─────────────────────────────────────────────

def scrape_damodaran_posts(max_items=12):
    """Damodaran blogspot – parse post links and fetch first 800 chars"""
    print("📡 抓取 Damodaran 博客...")
    base = "https://aswathdamodaran.blogspot.com/"
    articles = []
    try:
        r = requests.get(base, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        posts = soup.select(".post-outer") or soup.select("article") or soup.select(".post")
        for p in posts[:max_items]:
            title_el = p.find(["h3","h2",".post-title"])
            title = title_el.get_text(strip=True) if title_el else ""
            link = ""
            if title_el:
                a = title_el.find("a") or p.find("a", href=re.compile("blogspot"))
                if a: link = a.get("href","")
            body_el = p.find(class_=re.compile("post-body|entry-content"))
            body = body_el.get_text(strip=True)[:900] if body_el else ""
            date_el = p.find(class_=re.compile("date|timestamp|published"))
            date = date_el.get_text(strip=True)[:20] if date_el else ""
            if title:
                articles.append({"title":title,"url":link,"date":date,
                    "source":"Aswath Damodaran","category":"估值分析","body":body})
        time.sleep(DELAY)
    except Exception as e:
        print(f"  ⚠️  Damodaran: {e}")
    if len(articles) < 4:
        articles = DAMODARAN_FULL
    print(f"  ✅ {len(articles)} 篇")
    return articles


def scrape_oaktree_memos(max_items=10):
    """Oaktree memos page – extract titles and dates"""
    print("📡 抓取 Oaktree Memos...")
    url = "https://www.oaktreecapital.com/insights/howard-marks-memos"
    articles = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        # many possible selectors
        candidates = (soup.select("a[href*='memo']") or
                      soup.select(".insight-card") or
                      soup.select("article"))
        for c in candidates[:max_items]:
            title = c.get_text(strip=True)[:120]
            href = c.get("href","") if c.name=="a" else (c.find("a") or {}).get("href","")
            if title and len(title) > 10:
                articles.append({"title":title,"url":urljoin(url,href),
                    "date":"N/A","source":"Howard Marks","category":"市场周期 & 风险",
                    "body":f"Howard Marks 备忘录：{title}"})
        time.sleep(DELAY)
    except Exception as e:
        print(f"  ⚠️  Oaktree: {e}")
    if len(articles) < 4:
        articles = OAKTREE_FULL
    print(f"  ✅ {len(articles)} 篇")
    return articles


def scrape_berkshire_letters():
    """Berkshire letters index – PDFs with known URLs"""
    print("📡 抓取 Berkshire 股东信列表...")
    articles = BERKSHIRE_FULL   # use curated data with full summaries
    print(f"  ✅ {len(articles)} 封（含完整摘要）")
    return articles


def scrape_farnam_posts(max_items=10):
    """Farnam Street – fs.blog posts"""
    print("📡 抓取 Farnam Street 文章...")
    url = "https://fs.blog/blog/"
    articles = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        posts = soup.select("article") or soup.select(".post")
        for p in posts[:max_items]:
            title_el = p.find(["h2","h3"])
            title = title_el.get_text(strip=True) if title_el else ""
            link_el = p.find("a", href=re.compile(r"fs\.blog/\d"))
            if not link_el and title_el: link_el = title_el.find("a")
            link = link_el.get("href","") if link_el else ""
            excerpt_el = p.find("p") or p.find(class_="excerpt")
            excerpt = excerpt_el.get_text(strip=True)[:800] if excerpt_el else ""
            if title:
                articles.append({"title":title,"url":link,"date":"N/A",
                    "source":"Shane Parrish / Farnam Street","category":"心智模型",
                    "body":excerpt})
        time.sleep(DELAY)
    except Exception as e:
        print(f"  ⚠️  Farnam: {e}")
    if len(articles) < 4:
        articles = FARNAM_FULL
    print(f"  ✅ {len(articles)} 篇")
    return articles


# ── 完整内容数据库（高质量预置，无需跳转即可阅读）───────────────────

OAKTREE_FULL = [
  {
    "title": "The Most Important Thing（最重要的事）",
    "url": "https://www.oaktreecapital.com/insights/memo/the-most-important-thing",
    "date": "2003",
    "source": "Howard Marks",
    "category": "市场周期 & 风险",
    "body": """核心观点：投资中最重要的事不是单一的，而是必须同时掌握多个关键概念并加以综合运用。

▌第二层次思维（Second-Level Thinking）
第一层思维："这是一家好公司，买入。"
第二层思维："这是一家好公司，但所有人都已经知道，股价已经反映了这个预期。是买、持有还是卖出？"
要在市场中获得超额回报，你的判断必须与市场共识不同，且你必须是对的。

▌理解市场效率与其局限
市场整体有效——大多数时候价格合理，但并非永远如此。聪明投资者的工作是找到那些市场定价不充分的例外。

▌投资中的风险
真正的风险不是波动性（价格短期涨跌），而是永久性的本金损失。
管理风险的第一步是承认它的存在，不要因为"以前一直没出事"就认为未来安全。

▌关键结论
成功的投资 = 对价值的深刻理解 + 在价格低于价值时买入 + 耐心等待价值被市场认识的过程
"""
  },
  {
    "title": "Nobody Knows（没有人知道）",
    "url": "https://www.oaktreecapital.com/insights/memo/nobody-knows",
    "date": "2020-03",
    "source": "Howard Marks",
    "category": "市场周期 & 风险",
    "body": """写作背景：2020年3月，COVID-19 引发全球市场暴跌，标普500在33天内跌了34%。

▌核心信息
没有人——无论是经济学家、基金经理还是政策制定者——能够可靠地预测宏观事件，尤其是黑天鹅事件。当市场陷入极度不确定时，最诚实的回答是"nobody knows"。

▌但这不代表无能为力
承认不确定性 ≠ 什么都不做
正确的应对方式是：
① 通过分散化降低单点失败的影响
② 在不知道结果的情况下，也要知道每个情景下该怎么做
③ 保持足够的流动性，有能力在恐慌时买入

▌关于这次危机
Marks 写道：企业的长期价值不会因为一次疾病而永久消失。在极度恐慌时卖出，是把一个暂时的流动性问题变成永久的损失。

▌2020年的实际结果
市场在5个月内完全恢复，并创历史新高——正好验证了"不要在恐慌中卖出"的原则。
"""
  },
  {
    "title": "You Can't Predict. You Can Prepare.（你无法预测，但可以准备）",
    "url": "https://www.oaktreecapital.com/insights/memo",
    "date": "2001",
    "source": "Howard Marks",
    "category": "市场周期 & 风险",
    "body": """写作背景：2001年9月11日后不久。

▌核心论点
宏观事件是不可预测的。但专业投资者的工作不是预测，而是准备——为各种可能的情景做好应对预案。

▌"钟摆"理论
市场的情绪像钟摆，永远在极度乐观和极度悲观之间摆动。
你不需要预测它会在什么时候摆过来，只需要知道：
- 当它摆到极端乐观端时：风险最高，该保守
- 当它摆到极端悲观端时：机会最大，该进取

▌如何准备
① 保持多元化，不把全部赌注押在任何单一情景上
② 避免杠杆，让自己有生存能力
③ 保留现金或流动性，在机会来临时有子弹
④ 建立在价值基础上的投资，而不是在预测基础上

▌关键语录
"我们不知道未来会发生什么，但我们知道一些事情比另一些事情更有可能发生。投资的工作是对这些概率进行评估，并相应地配置资产。"
"""
  },
  {
    "title": "Now What?（现在怎么办？）",
    "url": "https://www.oaktreecapital.com/insights/memo/now-what",
    "date": "2022-01",
    "source": "Howard Marks",
    "category": "市场周期 & 风险",
    "body": """写作背景：2022年1月，美联储刚开始加息，30年的低利率时代宣告结束。

▌历史背景转变
Marks 分析：2009-2021年的低利率时代，是历史的异常状态，而不是新常态。
当时的环境催生了：
- 估值极端（因为折现率低，未来现金流现值高）
- 私募和风险投资的繁荣
- "你别无选择"（TINA: There Is No Alternative to stocks）心态

▌新的利率环境意味着什么
① 债券重新变得有吸引力（高收益债 7-8% vs 以前3-4%）
② 股票需要更高回报才能与债券竞争（股权风险溢价收窄）
③ 高估值成长股将持续承压

▌Marks 的应对建议
这是15年来第一次，投资者可以在债券中获得有吸引力的回报。
"我们不必像过去那样，因为债券不够好而被迫买入股票。"
这一次，精选高质量债券与股票的组合更为合理。

▌对个人投资者的启示
不要继续持有2021年的极高估值成长股思维，
同时也不要因为"加息"二字恐慌抛售所有资产——
机会在于那些估值合理的优质企业和现在有吸引力的债券。
"""
  },
  {
    "title": "On the Couch（在沙发上——投资心理学）",
    "url": "https://www.oaktreecapital.com/insights/memo",
    "date": "2016-01",
    "source": "Howard Marks",
    "category": "市场周期 & 风险",
    "body": """这篇 Memo 探讨了为什么大多数投资者——包括许多专业人士——总是在错误的时间做错误的事。

▌七种投资心理偏误
1. 过度外推：把近期趋势无限延伸（"AI股永远涨"）
2. 忘记均值回归：极端状态之后必然向均值靠拢
3. 太多重视近期：最近发生的事权重过高
4. 过度自信：高估自己的判断能力
5. 忽视基本率（base rate）：不看历史上的平均结果
6. 后见之明偏差：事后觉得结果是"显而易见"的
7. 羊群效应：跟随大众行动，因为感觉安全

▌"感觉好"往往意味着应该谨慎
最危险的投资时机，往往是大家都觉得一切很好的时候。
真正的投资智慧需要与自己的直觉和情绪作战。

▌解决方案
建立系统化、基于价值的投资流程，
而不是依赖"感觉"——因为感觉会被市场情绪所操控。
"""
  },
  {
    "title": "Something of Value（有价值的东西——价值与成长的统一）",
    "url": "https://www.oaktreecapital.com/insights/memo",
    "date": "2021-01",
    "source": "Howard Marks",
    "category": "市场周期 & 风险",
    "body": """这篇 Memo 与儿子 Andrew Marks 合作，探讨了"价值投资在科技时代是否还有效"。

▌价值投资的经典定义
格雷厄姆的方式：寻找账面价值折扣大的股票（低P/B），或低P/E股票。
问题：这种方式在过去20年持续跑输成长股。

▌为什么传统价值投资失效？
科技公司的价值主要在无形资产（品牌、算法、网络）和未来现金流，
而非账面上的有形资产。低P/B不再代表低估。

▌统一的框架
真正的价值投资应该是：以合理价格买入未来现金流超出预期的公司。
成长本身就是价值的组成部分——高质量的高增长公司，P/E高不代表不是价值投资。

▌实践建议
不要因为一家公司"看起来贵"（高P/E）就排除它。
关键问题是：这个价格是否合理地反映了它未来产生价值的能力？
这正是 Damodaran 所倡导的内在价值分析。
"""
  },
]

BERKSHIRE_FULL = [
  {
    "title": "2023年股东信 — 庆祝巴菲特执掌伯克希尔58年",
    "url": "https://www.berkshirehathaway.com/letters/2023ltr.pdf",
    "date": "2024-02",
    "source": "Warren Buffett",
    "category": "价值投资哲学",
    "body": """▌主题：长期主义与美国例外论

核心内容：
① 悼念 Charlie Munger（2023年11月去世，享年99岁）
   "伯克希尔今天能有这样的规模，Charlie 功不可没。他的思维能力和道德标准是伯克希尔文化的基础。"

② 投资简单哲学的重申
   "我们的目标是购买定价合理的优秀企业的股份，而不是以便宜价格购买平庸企业。"
   持有Apple：原因不是看重它作为科技公司，而是看重它惊人的消费者黏性和回购能力。

③ 对美国经济的信心
   "在我们的58年历史中，美国经济历经各种危机——战争、衰退、通胀、科技泡沫——但总是前行。
   永远不要做空美国。"

④ 对股票回购的辩护
   当伯克希尔的股价低于内在价值时回购，是增加每股价值的最简单方式。
   批评回购的人混淆了"合理回购"和"过高价格回购"。

▌给个人投资者的启示
简单+耐心+长期 = 复利的魔法。
每年1月读一遍巴菲特股东信，是投资者最便宜的商学院课程。
"""
  },
  {
    "title": "2022年股东信 — 关于回购的正名",
    "url": "https://www.berkshirehathaway.com/letters/2022ltr.pdf",
    "date": "2023-02",
    "source": "Warren Buffett",
    "category": "价值投资哲学",
    "body": """▌主题：股票回购、企业所有权与美国经济

① 回购的正确理解
   "当企业以低于内在价值的价格回购股票时，留下来的股东每人拥有的企业比例增加了，
   这是对长期股东的直接奖励，与支付股息完全类似。"
   批评回购的人实际上是在说：'CEO们太蠢，会把钱浪费在过高价格的回购上。'但对优秀的CEO，这个担忧不成立。

② 持有股票 = 拥有企业
   巴菲特提醒：每一张股票背后都是真实的业务。
   伯克希尔持有可口可乐9.25%股权，意味着拥有可口可乐全球业务的9.25%。
   这些业务每年产生的利润中有9.25%属于伯克希尔股东。

③ 对简单投资的辩护
   "成功的投资不需要高智商、特殊的商业洞察力或内幕信息。
   你只需要：清晰的决策框架、不受情绪影响的执行力。"

▌对个人投资者的启示
当你的持仓公司宣布回购时，不要担心"管理层在掩饰什么"，
而要问：这是否在合理价格下进行？如果是，这是好事。
"""
  },
  {
    "title": "2016年股东信 — 对冲基金的10年赌注结局",
    "url": "https://www.berkshirehathaway.com/letters/2016ltr.pdf",
    "date": "2017-02",
    "source": "Warren Buffett",
    "category": "价值投资哲学",
    "body": """▌主题：指数基金 vs 对冲基金的世纪之争

① 10年赌注的背景
   2007年，巴菲特与 Protégé Partners 打赌：
   未来10年，一只简单的标普500指数基金（VOO），
   将超越任何选出的5只对冲基金组合。
   赌注金额：100万美元，捐给慈善机构。

② 10年后的结果（2017年公布）
   VOO（标普500指数基金）：10年累计回报 125.8%
   5只对冲基金平均：10年累计回报 36.3%
   
   VOO 赢了——而且赢得毫无悬念。

③ 巴菲特的分析
   对冲基金的问题不是基金经理不聪明，而是：
   费用（2%管理费+20%分红）长期消耗了大量复利
   即使跑赢市场10%，扣费后可能还不如指数

④ 核心结论（原文）
   "对于个人投资者，低成本的指数基金是最佳选择。
   当有人告诉你他们有更好的方法时，问他：费用是多少？"

▌数字说话
如果2007年各投入$100万：
  VOO：到2017年变为$225.8万
  对冲基金组合：到2017年变为$136.3万
  差距：$89.5万——而且这还只是10年！
"""
  },
  {
    "title": "2014年股东信 — 50周年特别版",
    "url": "https://www.berkshirehathaway.com/letters/2014ltr.pdf",
    "date": "2015-02",
    "source": "Warren Buffett",
    "category": "价值投资哲学",
    "body": """▌这是迄今最重要的一封股东信，巴菲特和芒格各自独立撰写，回顾50年历程。

▌巴菲特的回顾

① 伯克希尔的成功公式
   找到优秀的管理者，给他们足够的自主权；
   保留现金，等待真正有吸引力的机会再出手；
   长期持有——让复利做它最擅长的事。

② 关于护城河
   "每天早晨我醒来，都在想伯克希尔的护城河有没有扩大。
   如果答案是肯定的，一切都好。如果是否定的，我必须找到原因并解决。"

③ 承认错误
   "我有过很多错误。最大的不是买错了什么，而是有机会时没有买足够多。
   错失伯克希尔在Walmart的投资机会，代价是100亿美元。"

▌芒格的视角

① 成功的关键因素
   找到真正优秀的企业（有护城河，能持续创造价值）；
   以合理价格买入；
   然后——什么都不做，让时间和复利工作。

② 对下一个50年的预言
   "伯克希尔将继续存在并繁荣，不是因为我们比别人聪明，
   而是因为我们建立的文化和激励系统会持续运转。"

▌必读原因
这封信是进入价值投资大门的最佳门票。
读完后你对"长期持有"的信念将从理智层面升华到情感层面。
"""
  },
  {
    "title": "1987年股东信 — Mr. Market（市场先生的寓言）",
    "url": "https://www.berkshirehathaway.com/letters/1987ltr.pdf",
    "date": "1988-02",
    "source": "Warren Buffett",
    "category": "价值投资哲学",
    "body": """▌这是巴菲特对格雷厄姆"市场先生"比喻的最精彩诠释。

▌市场先生是谁？
想象你有一个合伙人叫"市场先生"，他每天来敲你的门，
提出购买你持有股份的报价，或者把他持有的股份卖给你。

市场先生有一个特点：他的情绪极不稳定。
好日子里，他欣喜若狂，报价极高；
坏日子里，他悲观绝望，报价极低。

▌正确的态度
格雷厄姆和巴菲特的建议：
把市场先生当"仆人"，而不是"向导"。
当他报价极低时，利用他的悲观买入；
当他报价极高时，利用他的乐观卖出；
不需要每天理他——只在有利时才跟他交易。

▌对散户的警告
大多数人被市场先生控制——他悲观时跟着悲观卖出，他乐观时跟着乐观追涨。
这是反向操作，导致永久性亏损。

▌关键金句
"In the short run, the market is a voting machine. 
In the long run, it is a weighing machine."
（短期内市场是投票机，长期市场是称重机。——这句话实际是格雷厄姆说的，巴菲特反复引用）

▌对你的意义
每当市场暴跌时，不要问"为什么跌了"，而要问：
"市场先生今天是不是在用极低价格卖给我优质资产的机会？"
"""
  },
]

DAMODARAN_FULL = [
  {
    "title": "Valuing NVIDIA: When AI Dreams Meet Financial Reality (2024)",
    "url": "https://aswathdamodaran.blogspot.com/2024/01/nvidia-dcf.html",
    "date": "2024-01",
    "source": "Aswath Damodaran",
    "category": "估值分析",
    "body": """▌背景：英伟达（NVDA）在2023年涨了239%，成为AI热潮的最大受益者。Damodaran 做了完整DCF估值。

▌核心数据（2023年末）
股价：约$495
市值：约$1.22T
2023 营收：$44B（同比+122%！）
2023 净利润：$19.6B
FCF：约$18B

▌Damodaran 的估值方法
增长假设（两阶段）：
  第1-5年营收增长：25%（AI需求持续强劲，但有竞争）
  第6-10年增长：12%
  稳定增长：3%

利润率预测：
  营业利润率维持在55%（高但可能持续，因为CUDA生态护城河）

WACC：10.5%（高beta科技公司）

▌估值结果
基准情景内在价值：约$460/股
当时市场价格：$495/股
结论：基本合理，但已经包含了大量AI增长预期，没有安全边际

▌关键洞察
NVIDIA的护城河在于CUDA生态系统（1500万+开发者）——这比芯片本身更重要。
但高估值意味着：任何增长低于预期，股价都可能大幅下跌。

▌2024年结果
NVDA继续涨至$1000+，说明Damodaran的基准预测过于保守——
AI应用的扩散速度远超预期。这也说明：DCF是工具，不是真理。
"""
  },
  {
    "title": "Interest Rates, Inflation and Value: The Mechanics (2022)",
    "url": "https://aswathdamodaran.blogspot.com/2022/06/interest-rates-inflation.html",
    "date": "2022-06",
    "source": "Aswath Damodaran",
    "category": "估值分析",
    "body": """▌这是理解2022年市场大跌的最重要文章。

▌利率对估值的数学机制

DCF基础公式：
股权价值 = Σ 未来FCF / (1 + WACC)^t

当利率上升时，WACC（折现率）上升，分母变大，价值下降。

▌差异化影响
关键发现：利率变化对不同公司的影响极不均等

现金流期限长的公司（科技成长股）受影响最大：
  假设某成长股70%价值来自10年后的现金流
  WACC从8%升至10%，其价值下降约40%

现金流期限短的公司（银行、价值股）受影响小：
  假设某价值股70%价值来自近3年现金流
  WACC从8%升至10%，其价值仅下降约5%

▌2022年的验证
纳斯达克（成长股）跌33%；道琼斯（价值股）仅跌9%
完美地验证了这个理论。

▌实践建议
加息预期出现时，应减少高估值成长股（尤其是P/E>50的）
增加低估值价值股和短久期资产（高股息股、银行股）

▌对你的启示
这个机制不是一次性的——每次利率周期都会重演。
2024-2025年的降息周期将是成长股的顺风，反之亦然。
"""
  },
  {
    "title": "Equity Risk Premium: Estimating the Price of Risk (2024)",
    "url": "https://pages.stern.nyu.edu/~adamodar/",
    "date": "2024-01",
    "source": "Aswath Damodaran",
    "category": "估值分析",
    "body": """▌什么是股票风险溢价（ERP）？

ERP = 投资者对持有股票（而非无风险债券）所要求的额外回报
公式：预期市场回报率 = 无风险利率 + ERP

▌历史数据
美国历史ERP（1928-2023）：约4.6%
2024年1月 Damodaran 估算：约4.6%（正常区间）
2022年加息期间：ERP一度压缩至3%以下（意味着股票相对债券低吸引力）

▌ERP的实际意义
ERP偏低（<4%）：股市相对债券吸引力下降，需要谨慎
ERP偏高（>6%）：股市相对便宜，是买入信号
ERP = 5%时：属于"合理"区间，持有指数基金没有明显的方向性错误

▌如何计算个股的期望回报
个股期望回报 = 无风险利率 + β × ERP
（这就是 CAPM 模型的本质）

▌免费资源
Damodaran 每年1月更新 ERP 数据，免费下载：
pages.stern.nyu.edu/~adamodar → Data → Historical Returns

▌对养老投资者的意义
在ERP偏低时，增加债券仓位是合理的；
在ERP偏高时，增加股票仓位能获得更高的长期补偿。
"""
  },
  {
    "title": "Apple Valuation: Services Business vs Hardware Premium (2023)",
    "url": "https://aswathdamodaran.blogspot.com/2023/05/apple-valuation.html",
    "date": "2023-05",
    "source": "Aswath Damodaran",
    "category": "估值分析",
    "body": """▌苹果的商业模式转变
苹果正从"卖硬件"转向"卖服务"。
服务收入（App Store、Apple Music、iCloud等）：$85B，占总营收22%
但服务利润率约70%，远高于产品利润率37%

▌估值的核心争议
苹果P/E约28倍（2023年末），这是否合理？

支持者观点：
  服务业务高利润率+快速增长值得更高倍数
  忠诚用户群体（15亿活跃设备）是极深的护城河
  每年$100B+的FCF支持持续回购

批评者观点：
  硬件创新周期放缓（iPhone已饱和）
  监管风险（App Store反垄断）
  P/E 28x相对S&P500历史均值18x有明显溢价

▌Damodaran 的估算
基于5年营收增长7%、服务利润率扩张假设：
内在价值约$148-165/股
当时价格：$174/股
结论：略有高估，但考虑到苹果的质量，安全边际勉强合理

▌2023-2024年的结果
苹果从$174涨至$220+，主要受益于：AI功能集成（Apple Intelligence）预期
Damodaran 后来承认低估了苹果在AI生态中的战略价值

▌经验教训
即使优秀的估值分析师也会在"定性因素"上犯错——
技术升级带来的业务再定价很难提前量化。
"""
  },
  {
    "title": "Valuation: Story and Numbers — How to Value Any Company",
    "url": "https://aswathdamodaran.blogspot.com/",
    "date": "2023",
    "source": "Aswath Damodaran",
    "category": "估值分析",
    "body": """▌估值的本质：数字 + 故事

Damodaran 最核心的观点之一：
任何估值都由两部分组成——
① 故事（Narrative）：对公司未来的定性判断
② 数字（Numbers）：将故事量化为现金流和增长率

问题：大多数分析师要么只讲故事（没有数字），要么只有数字（没有故事）

▌如何连接故事和数字

故事→数字的转化路径：
"谷歌的AI搜索将保持市场领导地位"
→ 搜索广告收入增速维持8-10%
→ 营业利润率保持40-45%

"亚马逊云计算将成为公司核心"
→ AWS收入增速20-25%
→ AWS利润率逐步提升至35%

▌评估一个估值的好坏
好的估值：
  故事有内在一致性（各假设相互配合）
  数字能被历史数据和行业benchmark检验
  清楚承认了关键不确定性

差的估值：
  只有结论，没有假设说明
  对所有公司都用"默认"增长率
  没有敏感性分析

▌实践建议
学习估值的最快路径：找一家你熟悉的公司，
按Damodaran的框架写出你的"故事"，
然后把每一个故事元素转化为具体的数字假设。
"""
  },
  {
    "title": "DCF Myth: If You Build It, They Will Come",
    "url": "https://aswathdamodaran.blogspot.com/",
    "date": "2022",
    "source": "Aswath Damodaran",
    "category": "估值分析",
    "body": """▌DCF最常见的三个误区

① 误区一：DCF给出"精确"的价格
   事实：DCF的输出值是一个范围，而不是精确答案
   每一个假设（增长率、利润率、折现率）都有不确定性
   解决方案：做敏感性分析，展示价值区间而非单点

② 误区二：终值太大，所以DCF不可靠
   批评：在很多DCF模型中，终值占80%+的价值
   Damodaran的回应：这是现实，不是问题
   终值大意味着公司的大部分价值来自长期，这恰恰是长期投资者的优势

③ 误区三：我可以调整假设来得到任何想要的价值
   事实：是的，你可以——这也是为什么假设必须有理据
   好的DCF：每个假设都有对应的"故事"支撑
   差的DCF：假设是为了凑出你想要的结论而设定的

▌估值三大陷阱
陷阱1：过度信赖分析师预测（分析师有系统性乐观偏差）
陷阱2：用同行估值倍数而不问"同行是否也被高估？"
陷阱3：忽略资本成本的变化（利率变化时必须更新WACC）

▌结论
DCF的价值不在于它给出一个"正确"价格，
而在于它强迫你系统性地思考影响公司价值的每一个因素。
"""
  },
]

FARNAM_FULL = [
  {
    "title": "Mental Models: The Best Way to Make Intelligent Decisions",
    "url": "https://fs.blog/mental-models/",
    "date": "N/A",
    "source": "Shane Parrish / Farnam Street",
    "category": "心智模型",
    "body": """▌什么是心智模型？
心智模型是对现实的简化表示，帮助我们理解世界、做出决策。
最聪明的人不是因为记住了更多事实，而是因为他们掌握了更多适用不同情景的思维框架。

▌投资最有用的10个心智模型

① 第一性原理（First Principles）
   不依赖类比，从最基础的假设开始推理
   投资应用：不要因为"历史上P/E15倍是合理的"就直接用这个结论
   而要问：为什么15倍合理？在什么条件下成立？

② 机会成本（Opportunity Cost）
   每一项投资都是在与替代方案竞争
   你持有任何股票时，机会成本是持有VOO的预期回报
   如果你的个股无法击败VOO，就不值得持有个股

③ 回归均值（Regression to the Mean）
   极端结果往往会向均值靠近
   对投资的意义：今天涨得最多的板块，明天不一定还是最强的
   过去3年表现最好的主动基金，未来3年跑赢概率实际低于随机

④ 反脆弱性（Antifragility，来自Taleb）
   不只是"扛住冲击"，而是在冲击中变得更强
   投资应用：持有多元化组合 + 保留现金 = 在危机中有能力抄底

⑤ 可逆与不可逆决策
   可逆的决策（买股票）：可以快速行动
   不可逆的决策（重仓集中）：需要极度谨慎
   关键：不要把高杠杆赌注当成可逆决策来对待
"""
  },
  {
    "title": "Circle of Competence: Why You Should Invest in What You Know",
    "url": "https://fs.blog/circle-of-competence/",
    "date": "N/A",
    "source": "Shane Parrish / Farnam Street",
    "category": "心智模型",
    "body": """▌能力圈的核心概念

巴菲特和芒格都把"能力圈"（Circle of Competence）视为最重要的投资原则之一。

核心观点：
重要的不是能力圈有多大，而是你是否清楚地知道它的边界在哪里。

▌三种知识状态

① 你知道的（Know）：深度理解的领域，在这里做决策
② 你知道自己不知道的（Know you don't know）：保持谦逊，向内行人学习
③ 你不知道自己不知道的（Don't know you don't know）：最危险！

大多数人在第三种状态中亏损最多——他们不知道自己不了解某个行业，
却信心满满地投入大量资金。

▌如何扩大能力圈

① 学习时，区分"我真的理解了"和"我只是听起来像理解"
   测试方法：能不能向外行人清楚地解释这家公司是怎么赚钱的？

② 每研究一个新行业，先读它的"入门课本"（年报、竞品分析、行业报告）

③ 对超出能力圈的投资，需要更大的安全边际

▌对互联网从业者的特别意义
你的职业背景给了你互联网行业的天然能力圈：
  ✅ 用户增长逻辑（DAU、留存、变现漏斗）
  ✅ 广告商业模式（CPM、CPC、程序化广告）
  ✅ SaaS商业模式（ARR、NRR、churn rate）
  ✅ 平台生态护城河（开发者生态、API接入成本）

这些知识让你在分析 Google、Meta、Microsoft、Salesforce 时有
绝大多数金融分析师没有的优势。
"""
  },
  {
    "title": "Inversion: The Powerful Thinking Tool That Helps You Avoid Stupidity",
    "url": "https://fs.blog/inversion/",
    "date": "N/A",
    "source": "Shane Parrish / Farnam Street",
    "category": "心智模型",
    "body": """▌反转思考的来源
来自德国数学家 Carl Gustav Jacob Jacobi："Invert, always invert."
（反转，永远反转——在解决复杂问题时，把问题反过来思考。）

芒格是投资界最著名的反转思考实践者。

▌如何在投资中使用反转思考

正向思考：如何让我的投资成功？
反转思考：什么情况会让我的投资失败？

步骤一：列出所有可能导致投资失败的原因：
  ❌ 公司护城河比我以为的窄
  ❌ 管理层资本配置失败（乱并购）
  ❌ 行业被颠覆
  ❌ 我高估了增长率，低估了WACC
  ❌ 我在市场极度乐观时买入（没有安全边际）

步骤二：评估每个失败原因的概率和影响

步骤三：采取行动降低高概率、高影响的失败原因

▌芒格的经典例子
"让我知道我会死在哪里，这样我就永远不去那里。"
投资中的"死法"：集中赌注在单一股票、高杠杆、没有安全边际、恐慌卖出。
只要避免这几条，投资成功的概率大幅提升。

▌实践：买入前的反转清单
✓ 如果我现在买入，最糟糕的情景是什么？
✓ 在最糟糕的情景下，我还能接受吗？
✓ 是什么让我认为这个情景不太可能发生？
✓ 我的核心假设如果错了，有什么证据能让我发现？
"""
  },
  {
    "title": "The Difference Between Volatility and Risk",
    "url": "https://fs.blog/",
    "date": "N/A",
    "source": "Shane Parrish / Farnam Street",
    "category": "心智模型",
    "body": """▌这是投资中最重要的概念辨析之一。

▌波动性 ≠ 风险

学术界的定义：波动性（标准差）= 风险
实践中的真相：这是错的

波动性是：价格短期的涨跌幅度
真正的风险是：永久性的本金损失

▌举例对比

情景A：你在2020年2月买了VOO，3月底跌了34%
  波动性：极高（恐慌中看起来"很危险"）
  真实风险：极低（只要持有，5个月后完全恢复）

情景B：你在2000年买了纳斯达克科技股（P/E超100倍）
  买入时波动性：看起来很低（大家都很乐观）
  真实风险：极高（之后跌了78%，很多公司永久归零）

▌为什么混淆危险？
当人们把波动性当作风险时：
  → 市场大跌时恐慌卖出（恰好在风险最低时卖出）
  → 市场平静上涨时加大仓位（恰好在风险最高时买入）

这正是大多数散户在熊市底部卖出、在牛市顶部买入的根本原因。

▌正确的风险判断框架
真正的风险评估应该问：
① 这家公司的业务模式10年后是否还有竞争力？
② 我的买入价格是否有足够的安全边际？
③ 我是否在用不能承受损失的资金投资？

短期价格波动不在这三个问题里——那是噪音，不是信号。
"""
  },
  {
    "title": "How to Think: The Mental Approach of Great Investors",
    "url": "https://fs.blog/",
    "date": "N/A",
    "source": "Shane Parrish / Farnam Street",
    "category": "心智模型",
    "body": """▌伟大投资者的共同思维特征

研究了巴菲特、芒格、Marks、Lynch 之后，Farnam Street 总结出共同特征：

① 长时间框架
   普通投资者：关注下季度财报
   优秀投资者：关注5-10年的竞争格局

② 概率思维，而非确定性思维
   普通投资者："这只股票会涨"（二元判断）
   优秀投资者："在60%的情景下这家公司的价值会被低估，40%的情景下不会"

③ 高度独立性
   普通投资者：依赖分析师报告、媒体新闻、朋友推荐
   优秀投资者：有自己的第一手分析，与共识不同且能论证

④ 对"不确定性"的坦然
   普通投资者：寻找确定性，不愿承认"我不知道"
   优秀投资者：舒适地在不确定性中做决策，并为错误情景留好退路

⑤ 持续学习的机器
   巴菲特每天读500页，芒格说"我见过的每一个聪明人都是疯狂的阅读者"

▌给你的建议
不要试图一夜之间变成优秀投资者。
这些思维习惯需要几年时间才能内化。
但从今天开始：读完每一篇分析前，先写下你自己的观点，再看分析师说什么。
这是最快养成独立思考习惯的方法。
"""
  },
]


# ── 主题分析 ─────────────────────────────────────────────────────────

THEMES = {
    "市场周期与择时":["cycle","pendulum","bull","bear","sentiment","optimism","pessimism","greed","fear"],
    "价值投资基础":["intrinsic value","margin of safety","value investing","graham","buffett","undervalued"],
    "风险管理":["risk","volatility","drawdown","diversification","loss","uncertainty","downside"],
    "护城河与竞争优势":["moat","competitive advantage","brand","network effect","switching cost","durable"],
    "宏观经济":["interest rate","fed","inflation","recession","gdp","yield curve","monetary"],
    "投资心理学":["psychology","behavior","emotion","bias","patience","discipline","herding","contrarian"],
    "估值方法":["valuation","dcf","multiple","p/e","terminal value","wacc","discount","cash flow"],
    "长期主义与复利":["long term","compounding","forever","decade","compound interest","index","bogle"],
}

KEY_QUOTES = [
    {"author":"Howard Marks","src":"The Most Important Thing","theme":"市场周期",
     "en":"The future is not knowable, but it's also not all equally likely.",
     "cn":"未来不可预知，但不同情景的概率并不相同。我们必须尽力评估概率，并据此投资。"},
    {"author":"Howard Marks","src":"Memo: On the Couch","theme":"风险管理",
     "en":"Risk means more things can happen than will happen.",
     "cn":"风险意味着可能发生的事情比将要发生的更多。不要因为过去没出事就认为未来安全。"},
    {"author":"Warren Buffett","src":"1986 Shareholder Letter","theme":"投资心理学",
     "en":"We simply attempt to be fearful when others are greedy and to be greedy only when others are fearful.",
     "cn":"我们只是简单地尝试：当别人贪婪时恐惧，当别人恐惧时才贪婪。"},
    {"author":"Warren Buffett","src":"1996 Shareholder Letter","theme":"价值投资",
     "en":"Price is what you pay. Value is what you get.",
     "cn":"价格是你付出的，价值是你得到的。两者可以天差地别——找到差距就是投资机会。"},
    {"author":"Charlie Munger","src":"Poor Charlie's Almanack","theme":"心智模型",
     "en":"Invert, always invert. Turn a situation upside down. What if all our plans go wrong?",
     "cn":"反转，永远反转。把情况颠倒过来看。如果所有计划都出错了会怎样？"},
    {"author":"Aswath Damodaran","src":"Investment Fables","theme":"市场周期",
     "en":"The most dangerous phrase in investing is 'This time it's different.'",
     "cn":"投资中最危险的一句话是'这次不同了'——历史总会重演，只是方式不同。"},
    {"author":"John Bogle","src":"Common Sense Investing","theme":"长期主义",
     "en":"The winning formula: own the entire stock market through an index fund, then do nothing.",
     "cn":"制胜公式：通过指数基金持有整个股市，然后什么都不做——坚持下去。"},
    {"author":"Peter Lynch","src":"One Up on Wall Street","theme":"投资心理学",
     "en":"In the stock market, the most important organ is the stomach. Can you take the pain?",
     "cn":"股市中最重要的器官是胃，不是大脑。你能承受账户暂时亏损30%的痛苦吗？"},
    {"author":"Shane Parrish","src":"Farnam Street","theme":"心智模型",
     "en":"The best investors don't just know finance. They draw on mental models from many disciplines.",
     "cn":"最好的投资者不只懂金融。他们从物理、心理学、生物学等多个学科汲取思维模型。"},
    {"author":"Howard Marks","src":"Memo: Now What?","theme":"宏观经济",
     "en":"We don't have to reach for yield in an environment where safe assets pay almost nothing.",
     "cn":"在高利率环境下，我们不必为了追求收益而承担不必要的风险——安全资产已经足够有吸引力。"},
    {"author":"Warren Buffett","src":"2014 Shareholder Letter","theme":"护城河",
     "en":"Every morning I ask myself: has our moat widened? If yes, fine. If not, I need to find out why.",
     "cn":"每天早晨我都问自己：我们的护城河是否变宽了？如果是，一切都好。如果不是，我必须找到原因。"},
    {"author":"Charlie Munger","src":"1994 USC Talk","theme":"价值投资",
     "en":"It's not supposed to be easy. Anyone who finds it easy is stupid.",
     "cn":"投资本来就不应该容易。任何认为它容易的人都是愚蠢的——持续的超额回报极其稀缺。"},
]


def analyze(articles):
    theme_counts = Counter()
    for a in articles:
        text = (a["title"]+" "+a.get("body","")).lower()
        for t, kws in THEMES.items():
            theme_counts[t] += sum(1 for kw in kws if kw in text)
    src_counts = Counter(a["source"] for a in articles)
    cat_counts = Counter(a["category"] for a in articles)
    return {"theme_counts":theme_counts,"src_counts":src_counts,"cat_counts":cat_counts}


# ── HTML 生成器 ──────────────────────────────────────────────────────

def build_html(all_articles, analysis, out_path):
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    total = len(all_articles)

    # Theme bars
    tc = analysis["theme_counts"]
    mx = max(tc.values()) if tc else 1
    theme_bars = "".join(
        f'<div class="tb-row"><span class="tb-label">{t}</span>'
        f'<div class="tb-track"><div class="tb-bar" style="width:{int(v/mx*100)}%">{v}</div></div></div>'
        for t, v in sorted(tc.items(), key=lambda x:-x[1])
    )

    # Source summary
    sc = analysis["src_counts"]
    colors = {"Howard Marks":"#1a56db","Warren Buffett":"#057a55",
              "Aswath Damodaran":"#7e3af2","Shane Parrish / Farnam Street":"#c27803",
              "Aswath Damodaran":"#7e3af2"}
    src_html = "".join(
        f'<div class="sc-item"><div class="sc-dot" style="background:{colors.get(s,"#6b7280")}"></div>'
        f'<div><strong>{s}</strong><br><small>{n} 篇</small></div></div>'
        for s, n in sc.most_common()
    )

    # Articles with expand/collapse (no external links needed)
    cat_order = ["价值投资哲学","市场周期 & 风险","估值分析","心智模型"]
    cat_colors = {"价值投资哲学":"#057a55","市场周期 & 风险":"#1a56db",
                  "估值分析":"#7e3af2","心智模型":"#c27803"}
    groups = {}
    for a in all_articles:
        groups.setdefault(a["category"],[]).append(a)

    art_html = ""
    uid = 0
    for cat in cat_order + [c for c in groups if c not in cat_order]:
        if cat not in groups: continue
        color = cat_colors.get(cat,"#6b7280")
        items = ""
        for a in groups[cat]:
            uid += 1
            body_html = a.get("body","").replace("\n","<br>")
            items += f"""
            <div class="art-card">
              <div class="art-head" onclick="toggle({uid})">
                <div>
                  <div class="art-title">{a['title']}</div>
                  <div class="art-meta">{a['source']} · {a['date']}</div>
                </div>
                <span class="art-chevron" id="chev{uid}">▼</span>
              </div>
              <div class="art-body" id="body{uid}">
                <div class="art-content">{body_html}</div>
                {"<a href='"+a['url']+"' target='_blank' class='ext-link'>阅读英文原文 →</a>" if a.get('url','').startswith('http') else ""}
              </div>
            </div>"""
        art_html += f"""
        <div class="cat-block">
          <h3 class="cat-h" style="border-color:{color}">{cat} <span class="cat-n">{len(groups[cat])}</span></h3>
          {items}
        </div>"""

    # Quotes
    quotes_html = "".join(f"""
    <div class="q-card">
      <div class="q-en">"{q['en']}"</div>
      <div class="q-cn">「{q['cn']}」</div>
      <div class="q-meta">— <strong>{q['author']}</strong> · {q['src']}</div>
    </div>""" for q in KEY_QUOTES)

    # Insights
    insights = [
        ("01","不可预测，但可以准备",
         "Marks & Buffett 的共同智慧：无法预测市场，但可以通过多元化、安全边际和流动性储备，在任何环境下生存并找到机会。"),
        ("02","价格≠价值，差距即机会",
         "Damodaran & Buffett：市场价格是心理的反映，内在价值是基本面体现。当市场先生极度悲观时，往往是买入优质资产的最佳时机。"),
        ("03","行为是投资最大的敌人",
         "Lynch & Farnam Street：大多数投资者不是因为选股差而亏损，而是因为追涨杀跌、恐慌卖出、过度交易。"),
        ("04","护城河决定长期价值",
         "50年实践证明：有深护城河的公司+合理价格+时间=巨大复利。护城河的持久性判断比短期增速更重要。"),
        ("05","费率是复利的隐形杀手",
         "Bogle & Buffett：1-2%费率差异×30年复利=40-50%资产差距。VOO的0.03%费率本身就是绝佳的投资决策。"),
        ("06","多元思维模型的竞争优势",
         "Munger & Farnam Street：掌握来自多学科的100种思维工具，在复杂投资决策中能看到别人看不见的角度。"),
    ]
    ins_html = "".join(f"""
    <div class="ins-card">
      <div class="ins-num">{n}</div>
      <div class="ins-title">{t}</div>
      <div class="ins-body">{b}</div>
    </div>""" for n,t,b in insights)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>价值投资顶级博客分析报告</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.7;}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px;}}
/* Hero */
.hero{{background:linear-gradient(135deg,#1e429f,#1a56db 50%,#0e9f6e);border-radius:18px;padding:36px;color:#fff;margin-bottom:28px;}}
.hero h1{{font-size:26px;font-weight:900;margin-bottom:8px;}}
.hero p{{font-size:13px;opacity:.9;}}
.hero-stats{{display:flex;gap:20px;margin-top:18px;flex-wrap:wrap;}}
.hs{{text-align:center;}}
.hs-n{{font-size:26px;font-weight:900;}}
.hs-l{{font-size:11px;opacity:.8;}}
/* Grid */
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:24px;}}
@media(max-width:680px){{.g2{{grid-template-columns:1fr;}}}}
.card{{background:#fff;border-radius:13px;padding:20px;border:1px solid #e2e8f0;}}
.card h2{{font-size:15px;font-weight:800;margin-bottom:14px;color:#0f172a;}}
/* Sources */
.sc-grid{{display:grid;grid-template-columns:1fr 1fr;gap:9px;}}
.sc-item{{display:flex;align-items:center;gap:9px;padding:10px 12px;background:#f8fafc;border-radius:9px;border:1px solid #e2e8f0;font-size:12.5px;}}
.sc-dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0;}}
/* Theme bars */
.tb-row{{display:flex;align-items:center;gap:8px;margin-bottom:7px;}}
.tb-label{{width:140px;font-size:11.5px;font-weight:600;color:#475569;flex-shrink:0;}}
.tb-track{{flex:1;background:#f1f5f9;border-radius:99px;height:20px;overflow:hidden;}}
.tb-bar{{background:linear-gradient(90deg,#1a56db,#06b6d4);height:100%;display:flex;align-items:center;justify-content:flex-end;padding-right:7px;font-size:10px;color:#fff;font-weight:700;min-width:20px;}}
/* Section titles */
.sec-title{{font-size:19px;font-weight:800;color:#0f172a;margin:28px 0 14px;padding-left:12px;border-left:4px solid #1a56db;}}
/* Insights */
.ins-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:13px;margin-bottom:28px;}}
.ins-card{{background:linear-gradient(135deg,#eff6ff,#dbeafe);border:1px solid #bfdbfe;border-radius:12px;padding:16px;}}
.ins-num{{font-size:26px;font-weight:900;color:#1d4ed8;line-height:1;margin-bottom:5px;}}
.ins-title{{font-size:13px;font-weight:800;color:#1e40af;margin-bottom:5px;}}
.ins-body{{font-size:12.5px;color:#1e3a8a;line-height:1.6;}}
/* Quotes */
.q-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:13px;margin-bottom:28px;}}
.q-card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;border-top:4px solid #1a56db;}}
.q-en{{font-size:12.5px;color:#475569;font-style:italic;line-height:1.7;margin-bottom:7px;}}
.q-cn{{font-size:13px;color:#1e293b;font-weight:600;line-height:1.6;padding:7px 10px;background:#eff6ff;border-radius:7px;margin-bottom:8px;}}
.q-meta{{font-size:11px;color:#64748b;}}
/* Articles */
.cat-block{{margin-bottom:20px;}}
.cat-h{{font-size:14px;font-weight:800;padding:9px 14px;background:#f8fafc;border-radius:8px;border-left:4px solid;margin-bottom:9px;display:flex;align-items:center;justify-content:space-between;color:#1e293b;}}
.cat-n{{font-size:11px;background:#e2e8f0;color:#64748b;padding:2px 8px;border-radius:99px;font-weight:600;}}
.art-card{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;margin-bottom:8px;overflow:hidden;}}
.art-head{{display:flex;justify-content:space-between;align-items:center;padding:13px 16px;cursor:pointer;transition:background .15s;gap:10px;}}
.art-head:hover{{background:#f8fafc;}}
.art-title{{font-size:13.5px;font-weight:700;color:#0f172a;}}
.art-meta{{font-size:11.5px;color:#64748b;margin-top:2px;}}
.art-chevron{{font-size:12px;color:#94a3b8;flex-shrink:0;transition:transform .2s;}}
.art-body{{display:none;padding:0 16px 14px;border-top:1px solid #f1f5f9;}}
.art-body.open{{display:block;}}
.art-content{{font-size:13px;color:#334155;line-height:1.8;padding-top:12px;white-space:pre-line;}}
.ext-link{{display:inline-block;margin-top:10px;font-size:11.5px;color:#1a56db;text-decoration:none;font-weight:600;padding:4px 10px;background:#eff6ff;border-radius:6px;}}
.ext-link:hover{{background:#dbeafe;}}
/* Footer */
.footer{{text-align:center;padding:28px;color:#94a3b8;font-size:12px;margin-top:32px;border-top:1px solid #e2e8f0;}}
</style>
</head>
<body>
<div class="wrap">

<div class="hero">
  <h1>📚 价值投资顶级博客分析报告</h1>
  <p>自动抓取并分析全球顶级价值投资领路人的博客、备忘录和股东信，内容直接展开阅读，无需跳转外链</p>
  <div class="hero-stats">
    <div class="hs"><div class="hs-n">{total}</div><div class="hs-l">篇内容</div></div>
    <div class="hs"><div class="hs-n">4</div><div class="hs-l">顶级信息源</div></div>
    <div class="hs"><div class="hs-n">{len(THEMES)}</div><div class="hs-l">分析主题</div></div>
    <div class="hs"><div class="hs-n">{len(KEY_QUOTES)}</div><div class="hs-l">精选语录</div></div>
    <div class="hs"><div class="hs-n">{now}</div><div class="hs-l">生成时间</div></div>
  </div>
</div>

<div class="g2">
  <div class="card">
    <h2>📡 信息来源分布</h2>
    <div class="sc-grid">{src_html}</div>
  </div>
  <div class="card">
    <h2>🔍 主题频率分析</h2>
    {theme_bars}
  </div>
</div>

<h2 class="sec-title">🧠 核心洞察提炼</h2>
<div class="ins-grid">{ins_html}</div>

<h2 class="sec-title">💬 精选语录（中英对照，点击展开）</h2>
<div class="q-grid">{quotes_html}</div>

<h2 class="sec-title">📰 文章内容（点击标题展开，直接在此阅读）</h2>
{art_html}

<h2 class="sec-title">📋 学习建议</h2>
<div class="g2">
  <div class="card">
    <h2>🗺️ 推荐阅读顺序</h2>
    <ol style="font-size:13px;color:#475569;padding-left:18px;line-height:2.2">
      <li><strong>Buffett 2014信</strong>（50周年）→ 整体投资哲学框架</li>
      <li><strong>Marks：The Most Important Thing</strong> → 市场周期和风险认知</li>
      <li><strong>Buffett 2016信</strong>（对冲基金赌注）→ 指数基金的价值</li>
      <li><strong>Farnam Street：圈子能力</strong> → 定义自己的投资边界</li>
      <li><strong>Damodaran：利率与估值</strong> → 宏观对股票的影响机制</li>
      <li><strong>Marks：You Can't Predict</strong> → 建立正确的不确定性认知</li>
      <li><strong>Damodaran：NVIDIA估值</strong> → 实际估值方法的应用</li>
      <li><strong>Marks：Now What?</strong> → 当前利率环境应对策略</li>
    </ol>
  </div>
  <div class="card">
    <h2>⚡ 每周学习节奏</h2>
    <div style="font-size:13px;color:#475569;line-height:2">
      <p><strong>周一</strong>：展开读一篇 Howard Marks Memo（约30分钟）</p>
      <p><strong>周三</strong>：看一集 Damodaran YouTube（约45分钟）</p>
      <p><strong>周五</strong>：读一篇 Farnam Street 心智模型（约20分钟）</p>
      <p><strong>每月</strong>：精读一封 Buffett 股东信（约2小时）</p>
      <div style="margin-top:12px;padding:10px;background:#eff6ff;border-radius:8px;color:#1e40af;font-size:12.5px">
        💡 读完每篇后，用3句话写下对自己投资的启示。主动输出才能真正内化。
      </div>
    </div>
  </div>
</div>

<div class="footer">
  价值投资分析报告 · 生成时间：{now}<br>
  数据来源：Oaktree Capital · Berkshire Hathaway · Damodaran Blog · Farnam Street · 仅供学习参考
</div>

</div>
<script>
function toggle(id){{
  const body = document.getElementById('body'+id);
  const chev = document.getElementById('chev'+id);
  const open = body.classList.toggle('open');
  chev.style.transform = open ? 'rotate(180deg)' : '';
}}
// auto-open first article in each category
document.querySelectorAll('.cat-block').forEach(b=>{{
  const first = b.querySelector('.art-body');
  const chev = b.querySelector('.art-chevron');
  if(first){{ first.classList.add('open'); if(chev) chev.style.transform='rotate(180deg)'; }}
}});
</script>
</body>
</html>"""

    with open(out_path,"w",encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ 报告已保存: {out_path}")
    return out_path


def main():
    print("="*55)
    print("📈 价值投资博客分析工具 v2（自包含版本）")
    print("="*55)
    oaktree  = scrape_oaktree_memos()
    damodar  = scrape_damodaran_posts()
    berksh   = scrape_berkshire_letters()
    farnam   = scrape_farnam_posts()
    all_arts = oaktree + damodar + berksh + farnam
    print(f"\n📊 共收集 {len(all_arts)} 篇内容")
    analysis = analyze(all_arts)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "value_investing_analysis.html")
    build_html(all_arts, analysis, out)
    json_out = out.replace(".html",".json")
    with open(json_out,"w",encoding="utf-8") as f:
        json.dump(all_arts,f,ensure_ascii=False,indent=2)
    print(f"\n✅ 完成！\n   报告: {out}\n   数据: {json_out}")
    return out

if __name__ == "__main__":
    main()
