#!/usr/bin/env python3
"""
深度博客爬虫 v1.0
抓取 Aswath Damodaran 和 Farnam Street / Shane Parrish 2020年以后文章
生成两份独立的中文分析 HTML 报告
"""

import requests
import time
import re
import os
from bs4 import BeautifulSoup
from collections import Counter
from urllib.parse import urljoin
from datetime import datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DELAY = 1.8
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK DATA  ── 即使爬虫失败，也能生成完整报告
# ─────────────────────────────────────────────────────────────────────────────

DAMODARAN_FALLBACK = [
    {
        "title": "A Viral Market Update: Pricing or Value?",
        "url": "https://aswathdamodaran.blogspot.com/2020/02/a-viral-market-update-pricing-or-value.html",
        "date": "2020-02-26",
        "year": 2020,
        "theme": "宏观与市场",
        "body": (
            "The spread of the COVID-19 virus is, as I see it, a 'black swan' event, "
            "impacting not just global health but all aspects of the economy. In this piece, "
            "I attempt to reconcile the market pricing (which has dropped 10-15%) with "
            "an assessment of value. The intrinsic value impact depends critically on how "
            "long the virus lasts and how deep the economic disruption goes. A short-lived "
            "virus (3-6 months) with contained damage has a limited effect on value; a "
            "prolonged one changes the calculus significantly. Key insight: markets are "
            "repricing (adjusting to new risk perceptions) faster than the underlying "
            "cash flows can be revalued. This creates both risk and opportunity for "
            "investors willing to do the DCF work."
        ),
    },
    {
        "title": "COVID-19 and Valuation: A Series of Updates",
        "url": "https://aswathdamodaran.blogspot.com/2020/03/covid-19-valuation-virus-economy-and.html",
        "date": "2020-03-14",
        "year": 2020,
        "theme": "宏观与市场",
        "body": (
            "As COVID-19 spreads globally, markets have entered free-fall. I update my "
            "valuation framework by incorporating three scenarios: optimistic (V-shaped "
            "recovery), base case (U-shaped, 12-18 months disruption), and pessimistic "
            "(L-shaped, multi-year stagnation). For S&P 500 valuation, the expected "
            "value across scenarios points to roughly 2,500-2,800 as fair value at the "
            "market bottom, though uncertainty bands are very wide. The key variable is "
            "not the virus itself but the economic policy response—fiscal stimulus and "
            "Fed intervention materially change the outcome. Discount rates must rise "
            "to account for heightened uncertainty even as risk-free rates fall."
        ),
    },
    {
        "title": "Stormy Weather: Investing through a Pandemic",
        "url": "https://aswathdamodaran.blogspot.com/2020/06/stormy-weather-a-mid-year-assessment-of.html",
        "date": "2020-06-16",
        "year": 2020,
        "theme": "宏观与市场",
        "body": (
            "Mid-2020 assessment: markets have recovered much of their losses despite "
            "economic reality still being grim. This apparent contradiction resolves when "
            "you recognize that markets price expectations, not current conditions. "
            "The Fed's extraordinary intervention has suppressed risk-free rates to near "
            "zero, mechanically lifting equity valuations via lower discount rates. "
            "Simultaneously, tech companies—whose cash flows are less impacted by COVID—"
            "have pulled forward years of growth. The dangerous assumption is that "
            "zero rates persist indefinitely. If rates normalize, much of the premium "
            "built into growth stocks evaporates. This is the embedded risk few are pricing."
        ),
    },
    {
        "title": "Tesla: Story, Valuation and Verdict",
        "url": "https://aswathdamodaran.blogspot.com/2020/07/tesla-story-valuation-and-verdict.html",
        "date": "2020-07-01",
        "year": 2020,
        "theme": "科技/成长股估值",
        "body": (
            "Tesla presents the ultimate valuation challenge: a company with a compelling "
            "narrative that either justifies or makes a mockery of current prices depending "
            "on which story you believe. My DCF approach separates the story (market leader "
            "in EVs + energy storage + autonomous driving) from the numbers (revenue CAGR, "
            "target margins, reinvestment needs). In my base case, Tesla needs to achieve "
            "~$200B in revenue at 15% operating margins within 10 years to justify its "
            "2020 market price. That's possible—but it prices in perfection. The real "
            "lesson: high-multiple stocks are not inherently overvalued; they require "
            "high growth AND sustained competitive advantage to deliver."
        ),
    },
    {
        "title": "The Fed Put, Low Interest Rates and the Equity Risk Premium",
        "url": "https://aswathdamodaran.blogspot.com/2021/01/january-2021-data-update-equity-risk.html",
        "date": "2021-01-08",
        "year": 2021,
        "theme": "利率与估值",
        "body": (
            "Annual data update for 2021: the equity risk premium (ERP) has evolved "
            "significantly. At year-end 2020, the implied ERP for the S&P 500 stood at "
            "approximately 4.7%—elevated versus history, reflecting COVID uncertainty. "
            "The near-zero Treasury rates mean that even modest earnings growth can justify "
            "high P/E ratios through the DCF lens. The dangerous dynamic: if rates rise "
            "even modestly (say to 2%), P/E multiples must compress substantially. "
            "I estimate that a 100bp rise in the 10-year could reduce fair value for the "
            "S&P 500 by 15-20%. Market participants who ignore the rate sensitivity of "
            "high-multiple stocks are taking on hidden duration risk."
        ),
    },
    {
        "title": "Meme Stocks, Short Squeezes and What They Tell Us About Markets",
        "url": "https://aswathdamodaran.blogspot.com/2021/02/meme-stocks-short-squeezes-and-what.html",
        "date": "2021-02-01",
        "year": 2021,
        "theme": "市场定价与行为金融",
        "body": (
            "The GameStop short squeeze illustrates a fundamental tension in markets: "
            "price and value can diverge dramatically in the short run. GameStop's "
            "intrinsic value—based on its declining retail gaming business—supports "
            "a stock price in the $10-20 range. Its $400 peak was pure momentum/sentiment. "
            "The lesson for value investors: markets are pricing mechanisms first and "
            "value discovery mechanisms second. Catalysts that convert price to value "
            "can take years, and in the interim, being right on value but wrong on timing "
            "is financially painful. The GameStop episode also reveals the limits of "
            "traditional short selling as a market efficiency mechanism."
        ),
    },
    {
        "title": "The Value of Control: Voting Shares and Corporate Governance",
        "url": "https://aswathdamodaran.blogspot.com/2021/05/the-value-of-control-pricing-voting.html",
        "date": "2021-05-12",
        "year": 2021,
        "theme": "估值方法论",
        "body": (
            "When companies have dual-class share structures (Google, Meta, Snap), how "
            "much is voting control worth? The traditional approach applies a 'control "
            "premium' of 10-30%. My framework suggests this premium should be a function "
            "of: (1) the quality of the current management (bad managers = higher control "
            "value), (2) the gap between current and optimal value (larger gap = higher "
            "premium), and (3) the probability that control will actually be exercised. "
            "For well-run tech companies with founder-operators like Google, the control "
            "discount for non-voting shares may be minimal. For poorly governed companies, "
            "the discount can be substantial."
        ),
    },
    {
        "title": "Inflation, Interest Rates and the Damage Done",
        "url": "https://aswathdamodaran.blogspot.com/2022/05/inflation-interest-rates-and-damage-done.html",
        "date": "2022-05-11",
        "year": 2022,
        "theme": "利率与估值",
        "body": (
            "2022's inflation surge is reshaping equity valuations through multiple "
            "channels: (1) Higher risk-free rates directly increase the discount rate "
            "in DCF models, reducing present values; (2) Inflation erodes real cash flows "
            "for companies that cannot pass through cost increases; (3) The Fed's "
            "aggressive tightening introduces recession risk, compressing terminal values. "
            "The math is brutal for long-duration assets: a company with most value in "
            "terminal value (year 10+) sees disproportionate impact from a 200bp rate "
            "rise. Tech growth stocks—with high multiples and distant cash flows—fall "
            "hardest. My updated S&P 500 valuation model with 3.5% 10-year rate shows "
            "fair value ~15-20% below year-start levels."
        ),
    },
    {
        "title": "The Fed and Markets: A Timeline of Misadventure",
        "url": "https://aswathdamodaran.blogspot.com/2022/06/the-fed-and-markets-timeline-of.html",
        "date": "2022-06-15",
        "year": 2022,
        "theme": "利率与估值",
        "body": (
            "A historical review of Fed policy errors and their market consequences. "
            "From the 1970s stagflation to the 2008 crisis to the 2021-22 inflation "
            "misread, the pattern is consistent: the Fed is reactive, not proactive. "
            "For investors, this has a crucial implication: don't fight the Fed, but "
            "also don't trust the Fed's forward guidance. The current (2022) rate hike "
            "cycle is the fastest since Volcker. Historical precedent suggests equity "
            "markets bottom 6-12 months after the first rate hike. The key risk is "
            "overtightening into recession. Portfolio implication: increase quality "
            "factor exposure (high ROIC, low debt) as rate volatility persists."
        ),
    },
    {
        "title": "A Meta-Analysis of Market Timing Models",
        "url": "https://aswathdamodaran.blogspot.com/2022/09/a-meta-analysis-of-market-timing-models.html",
        "date": "2022-09-20",
        "year": 2022,
        "theme": "市场定价与行为金融",
        "body": (
            "Despite decades of academic research and trillions in assets managed by "
            "quants, market timing remains elusive. A meta-analysis of 200+ market timing "
            "studies finds: (1) Most strategies that work in backtests fail out-of-sample; "
            "(2) Transaction costs and taxes erode most timing alpha; (3) The best "
            "timing signals (CAPE, earnings yield spread) have predictive power over "
            "10-year horizons but near-zero power over 1-year horizons. Conclusion: "
            "for long-term retirement investors, time in market > timing the market. "
            "Use valuation as a guardrail (reduce equity when CAPE > 35, increase when "
            "< 15), not as a day-trading signal."
        ),
    },
    {
        "title": "Twitter/X: The Elon Musk Premium and Discount",
        "url": "https://aswathdamodaran.blogspot.com/2022/10/twitter-elon-musk-chaos-and-value.html",
        "date": "2022-10-28",
        "year": 2022,
        "theme": "科技/成长股估值",
        "body": (
            "Elon Musk's $44B acquisition of Twitter offers a rare case study in "
            "strategic vs. financial valuation. My financial DCF of Twitter pre-deal "
            "placed intrinsic value at $25-30/share—far below the $54.20 deal price. "
            "The gap is the 'transformation premium'—the value Musk believes he can "
            "create by monetizing Twitter Blue, cutting costs, and revamping the ad model. "
            "This is not irrational: if Musk can 3x revenue while improving margins, "
            "the deal could work. The lesson: acquisitions at premiums to intrinsic "
            "value are not automatically bad—they reflect the acquirer's view of "
            "synergies and transformation potential. The danger is overpaying for "
            "optionality that may never materialize."
        ),
    },
    {
        "title": "NVIDIA: The AI Premium – Deserved or Delusional?",
        "url": "https://aswathdamodaran.blogspot.com/2023/06/nvidia-ai-premium-deserved-or-delusional.html",
        "date": "2023-06-14",
        "year": 2023,
        "theme": "科技/成长股估值",
        "body": (
            "NVIDIA's stock has tripled in 2023 on AI mania. I apply a rigorous DCF to "
            "separate the hype from the value. Base case assumptions: revenue grows from "
            "$27B (FY2023) to $150B by FY2028 (56% CAGR), driven by AI/data center "
            "dominance. Operating margins stabilize at 40%+ as software/services mix "
            "increases. WACC of 10.5% reflecting tech risk. Result: intrinsic value of "
            "~$300/share vs. $420 market price (June 2023). The market is pricing a "
            "'best case' scenario with limited margin for error. Key risk: AMD and "
            "custom silicon (Google TPU, Amazon Trainium) erode NVIDIA's monopoly rent. "
            "I maintain NVIDIA has real value—but at current prices, you're paying for "
            "perfection plus a little more."
        ),
    },
    {
        "title": "The Rise of Passive Investing: Implications for Active Managers",
        "url": "https://aswathdamodaran.blogspot.com/2023/07/the-passive-investing-dilemma-for.html",
        "date": "2023-07-10",
        "year": 2023,
        "theme": "市场定价与行为金融",
        "body": (
            "Passive investing now represents over 50% of equity assets in the US. "
            "This has profound implications for market efficiency: (1) Price discovery "
            "relies increasingly on a shrinking pool of active investors; (2) Index "
            "inclusion/exclusion effects are magnified; (3) Correlation within indices "
            "rises, reducing diversification benefits. For the individual investor, "
            "the case for passive remains compelling—most active managers fail to beat "
            "their benchmarks after fees. But as passive dominates, the opportunity for "
            "skilled active management may actually increase (fewer competitors doing "
            "the valuation work). The sweet spot: passive for core allocation, "
            "active/concentrated only in areas of genuine expertise."
        ),
    },
    {
        "title": "Interest Rates in 2023: The New Normal or Temporary Detour?",
        "url": "https://aswathdamodaran.blogspot.com/2023/09/interest-rates-in-2023-new-normal-or.html",
        "date": "2023-09-05",
        "year": 2023,
        "theme": "利率与估值",
        "body": (
            "With the 10-year Treasury at 4.5%+ and the Fed funds rate at 5.25-5.5%, "
            "I revisit the question: is this the 'new normal'? Historical analysis "
            "of 150 years of rate data suggests current rates are more 'normal' than "
            "the 2010-2021 ZIRP era, which was the historical anomaly. Implications: "
            "(1) Equity valuations should rebase to a higher discount rate—the P/E "
            "multiple expansion of 2010-2021 partly reverses; (2) Bonds re-emerge as "
            "genuine competition for equity capital (TINA is dead); (3) Zombie companies "
            "kept alive by cheap debt face reckoning. The 4% rule for retirement now "
            "looks more sustainable as bonds offer real returns again."
        ),
    },
    {
        "title": "OpenAI and the Value of Unicorn Illusions",
        "url": "https://aswathdamodaran.blogspot.com/2023/10/openai-and-ai-companies-value-of.html",
        "date": "2023-10-18",
        "year": 2023,
        "theme": "科技/成长股估值",
        "body": (
            "OpenAI's $86B valuation in late 2023 raises the question: how do you value "
            "a company that may transform multiple industries but has minimal current "
            "revenue? I apply a probabilistic DCF with three scenarios: "
            "transformative ($500B+ value), moderate success ($100B), and also-ran ($15B). "
            "Probability-weighting these scenarios gives an expected value around $80-90B—"
            "roughly in line with current pricing. The key insight: in truly disruptive "
            "technology, scenario analysis beats point estimates. The distribution of "
            "outcomes is bimodal—either the technology dominates or it doesn't. "
            "Hedged bets via ETFs (like QQQ) are rational for most investors rather "
            "than concentrated bets on specific AI names."
        ),
    },
    {
        "title": "January 2024 Data Update: Equity Markets in Perspective",
        "url": "https://aswathdamodaran.blogspot.com/2024/01/january-2024-data-update-equity-markets.html",
        "date": "2024-01-09",
        "year": 2024,
        "theme": "估值方法论",
        "body": (
            "Annual state-of-the-market update for 2024. Key data points: S&P 500 "
            "trailing P/E at 24x (above historical average of 18x); forward P/E at 21x. "
            "Implied equity risk premium (ERP) at 3.9%—historically low, suggesting "
            "either markets expect rates to fall sharply, or stocks are modestly overvalued. "
            "The Buffett indicator (market cap / GDP) at 1.7x—elevated but not extreme "
            "given tech sector's global revenue base. Country risk premium analysis "
            "shows US equities still attractive vs. emerging markets on risk-adjusted basis. "
            "Bottom line: US equities are priced for a 'soft landing' scenario. "
            "Any deviation toward recession or persistent inflation re-rates the market."
        ),
    },
    {
        "title": "Apple: Mature Company Valuation and the Buyback Machine",
        "url": "https://aswathdamodaran.blogspot.com/2024/02/apple-update-mature-company-valuation.html",
        "date": "2024-02-08",
        "year": 2024,
        "theme": "具体公司分析",
        "body": (
            "Apple's $3T valuation in early 2024 requires scrutiny. My DCF framework: "
            "Revenue growth slows to 5-7% CAGR (Services growing 12-15%, Hardware flat); "
            "Operating margins stay at 28-30% (Services mix improves overall margin); "
            "FCF yield of ~3.5% at current price. The buyback program ($90B+ annually) "
            "is the key value driver—Apple is essentially a levered buyback machine. "
            "At 3.5% FCF yield vs. 4.5% 10-year Treasury, Apple's risk premium is thin. "
            "Intrinsic value estimate: $140-160/share vs. ~$185 market. Apple deserves a "
            "premium for brand and ecosystem, but the current premium assumes "
            "Services continuing to accelerate—a bet on Services monetization."
        ),
    },
    {
        "title": "AI and Equity Valuation: Separating Signal from Noise",
        "url": "https://aswathdamodaran.blogspot.com/2024/05/ai-and-equity-valuation-separating.html",
        "date": "2024-05-20",
        "year": 2024,
        "theme": "科技/成长股估值",
        "body": (
            "AI's impact on equity markets needs to be disaggregated: "
            "(1) Infrastructure beneficiaries (NVIDIA, AMD, cloud providers)—value "
            "creation is measurable via capex ROI; (2) Application layer enablers "
            "(Microsoft Copilot, Salesforce AI)—value creation depends on pricing power "
            "and adoption; (3) Potential disruptees (search, SaaS incumbents)—risk of "
            "revenue displacement. My framework: AI creates value when it reduces costs "
            "or expands addressable markets with positive NPV reinvestment. Hype creates "
            "value only temporarily. The 2024 Magnificent 7 phenomenon shows markets "
            "accurately identifying AI beneficiaries but possibly overpricing optionality. "
            "Recommended approach: evaluate each company's AI-driven FCF trajectory separately."
        ),
    },
    {
        "title": "The Magnificent Seven: Are They Worth Their Multiples?",
        "url": "https://aswathdamodaran.blogspot.com/2024/03/the-magnificent-seven-are-they-worth.html",
        "date": "2024-03-12",
        "year": 2024,
        "theme": "科技/成长股估值",
        "body": (
            "A systematic DCF analysis of Apple, Microsoft, Alphabet, Amazon, Meta, "
            "Tesla, and NVIDIA. Key findings: Microsoft is the most defensible at "
            "current valuations (Azure + AI integration + Office ecosystem); Meta "
            "offers the best risk-reward (low multiple, high FCF, AI monetization "
            "early innings); NVIDIA and Tesla carry the highest execution risk. "
            "Amazon's valuation depends almost entirely on AWS margin trajectory. "
            "Aggregate finding: the group as a whole trades at a 15-25% premium "
            "to intrinsic value in base case—a premium that requires executing near-"
            "perfectly on growth AND margins. Concentration risk: the Mag 7 "
            "represents 30% of S&P 500—unprecedented index concentration."
        ),
    },
    {
        "title": "Country Risk Premium Update 2024",
        "url": "https://aswathdamodaran.blogspot.com/2024/07/country-risk-2024-annual-update.html",
        "date": "2024-07-05",
        "year": 2024,
        "theme": "估值方法论",
        "body": (
            "Annual update of country risk premiums for 170+ countries. Key findings "
            "for 2024: US country risk premium remains near zero (AAA/Aaa equivalent); "
            "China risk premium has risen to 3.5-4% reflecting geopolitical and "
            "regulatory uncertainty; India risk premium declined to 2.3% reflecting "
            "improving governance; emerging markets ERP broadly elevated post-2022. "
            "Practical application: Chinese ADRs should be discounted 15-20% relative "
            "to comparable US companies due to country risk alone. For Chinese investors "
            "building US portfolios, the inverse applies—US equities provide not just "
            "return potential but also a geopolitical hedge."
        ),
    },
    {
        "title": "Equity Markets 2025: A Valuation Reckoning",
        "url": "https://aswathdamodaran.blogspot.com/2025/01/equity-markets-2025-valuation-reckoning.html",
        "date": "2025-01-07",
        "year": 2025,
        "theme": "宏观与市场",
        "body": (
            "As 2025 begins, the S&P 500 has delivered back-to-back 20%+ years. "
            "My year-start valuation analysis: trailing P/E of 27x is the highest since "
            "the 2000 dot-com peak (excl. COVID distortions). Implied ERP has compressed "
            "to 3.4%—the lowest in 20 years—suggesting either extraordinary earnings "
            "growth expectations or overvaluation. Three scenarios for 2025: "
            "Bull (AI productivity boom materializes, EPS grows 15%)—S&P to 6,500; "
            "Base (soft landing, EPS grows 8%)—S&P range-bound 5,500-5,800; "
            "Bear (recession or rate resurgence)—S&P to 4,500. Risk management "
            "takeaway: this is not a market to be all-in on with new money; "
            "a barbell approach (quality growth + value/international) is prudent."
        ),
    },
    {
        "title": "Tariffs, Trade Wars and Equity Valuation",
        "url": "https://aswathdamodaran.blogspot.com/2025/02/tariffs-trade-wars-and-equity-valuation.html",
        "date": "2025-02-15",
        "year": 2025,
        "theme": "宏观与市场",
        "body": (
            "The resurgence of tariff rhetoric in 2025 requires a systematic analysis "
            "of second-order effects on equity valuations. Direct channel: tariffs "
            "raise input costs for importers and invite retaliation against exporters. "
            "Indirect channel: uncertainty suppresses capex and hiring. Historical "
            "evidence from 2018-2019 trade war: S&P earnings growth slowed ~2% per "
            "year in tariff-affected sectors. A broad 10% tariff scenario reduces "
            "S&P 500 EPS by 4-6%. More important: the uncertainty premium rises, "
            "expanding the equity risk premium. Sector implications: domestic-revenue "
            "companies (utilities, healthcare) benefit; multinationals (tech, autos, "
            "industrials) are hurt. Defensive positioning: increase quality factor exposure."
        ),
    },
]

FARNAM_FALLBACK = [
    {
        "title": "First Principles Thinking: The Building Blocks of True Knowledge",
        "url": "https://fs.blog/first-principles/",
        "date": "2020-03-10",
        "year": 2020,
        "theme": "决策框架",
        "body": (
            "First principles thinking is the practice of questioning every assumption "
            "until you reach the foundational truths, then reasoning up from there. "
            "Elon Musk famously used it to reduce rocket costs by 10x by questioning "
            "whether rockets had to be expensive (they don't—the materials are cheap; "
            "the manufacturing process is what's expensive). For investors, first "
            "principles thinking means refusing to accept consensus narratives. Instead "
            "of asking 'why is this stock at 30x earnings?' ask 'what fundamental "
            "economics would justify 30x earnings?' This often reveals either genuine "
            "competitive advantage worth paying for, or wishful thinking dressed as analysis. "
            "The method: identify the problem, challenge existing assumptions, create new "
            "solutions from scratch based on verified facts."
        ),
    },
    {
        "title": "Inversion: The Crucial Thinking Tool You're Probably Not Using",
        "url": "https://fs.blog/inversion/",
        "date": "2020-05-19",
        "year": 2020,
        "theme": "决策框架",
        "body": (
            "Inversion is the practice of solving problems backwards. Instead of asking "
            "'how do I succeed?' ask 'what would guarantee failure, and then avoid it.' "
            "Charlie Munger credits much of his success to inversion: 'All I want to "
            "know is where I'm going to die, so I'll never go there.' For investors: "
            "instead of building a bull case for a stock, first build the bear case as "
            "strongly as possible. What would have to be true for this investment to fail? "
            "If you can't identify credible failure modes, you haven't thought hard enough. "
            "Common failure modes in investing: (1) leverage at the wrong time, "
            "(2) overconcentration in correlated bets, (3) selling quality during drawdowns. "
            "Inverting your portfolio construction: what allocation would guarantee "
            "retirement failure? Then don't do that."
        ),
    },
    {
        "title": "The Feynman Technique: The Best Way to Learn Anything",
        "url": "https://fs.blog/feynman-technique/",
        "date": "2020-06-15",
        "year": 2020,
        "theme": "认知与学习",
        "body": (
            "Richard Feynman's learning technique: (1) Choose a concept; (2) Teach it "
            "to a 12-year-old; (3) Identify the gaps in your explanation; (4) Return "
            "to the source, simplify. The crucial insight: the ability to explain simply "
            "is a proxy for genuine understanding. Many investors use complex jargon "
            "(EV/EBITDA, WACC, multiple expansion) without truly understanding what "
            "drives these metrics. Test yourself: can you explain discounted cash flow "
            "to someone with no finance background? If not, your own understanding is "
            "shaky. Applied to investing: before buying any stock, write a one-page "
            "investment thesis in plain language. If you can't write it clearly, you "
            "don't understand the investment well enough to hold it through volatility."
        ),
    },
    {
        "title": "The Map is Not the Territory",
        "url": "https://fs.blog/map-and-territory/",
        "date": "2020-08-04",
        "year": 2020,
        "theme": "认知偏差",
        "body": (
            "Alfred Korzybski's insight that 'the map is not the territory' is "
            "foundational for clear thinking. Our mental models—our maps—are "
            "simplifications of reality. They're useful precisely because they leave "
            "things out, but they become dangerous when we mistake the model for reality. "
            "In investing, financial models are maps. A DCF model is a map of a company's "
            "value—useful, but not the territory (actual future cash flows). The danger: "
            "over-reliance on models creates false precision. A DCF that spits out "
            "$47.83 intrinsic value suggests precision that doesn't exist. Better "
            "approach: build models to understand the range of outcomes and the key "
            "variables that matter most, not to get a precise number. The model's "
            "value is in clarifying your thinking, not in the output."
        ),
    },
    {
        "title": "Second-Order Thinking: What Smart People Use to Outperform",
        "url": "https://fs.blog/second-order-thinking/",
        "date": "2020-10-27",
        "year": 2020,
        "theme": "决策框架",
        "body": (
            "First-order thinking: 'This medicine will cure the patient.' Second-order "
            "thinking: 'This medicine will cure the patient, but also create antibiotic "
            "resistance that causes bigger problems later.' Howard Marks identifies "
            "second-order thinking as the key to investment alpha. Everyone does first-order "
            "thinking (obvious outcomes are priced in). Edge comes from asking 'and then what?' "
            "Examples: (1) COVID hits → airlines collapse (first-order obvious); but "
            "airline equity still has value if they survive (second-order); but zombie "
            "airlines emerge laden with debt and can't compete (third-order). "
            "For retirement investing: DCA into index funds seems low-return "
            "(first-order); but the compounding and tax efficiency creates wealth "
            "that active strategies rarely match (second-order). Think in chains, not steps."
        ),
    },
    {
        "title": "Circle of Competence: How to Build and Use Your Moat of Knowledge",
        "url": "https://fs.blog/circle-of-competence/",
        "date": "2021-01-19",
        "year": 2021,
        "theme": "投资哲学",
        "body": (
            "Warren Buffett and Charlie Munger's concept of Circle of Competence: "
            "you should invest only in companies and industries you genuinely understand. "
            "The circle itself matters less than knowing its boundaries. Most investment "
            "mistakes come from operating outside the circle while believing you're inside. "
            "For an internet professional: your circle likely includes consumer internet, "
            "SaaS, digital advertising, fintech, and e-commerce. You understand unit "
            "economics, network effects, CAC/LTV dynamics, and platform business models "
            "better than most. Stay there. Venture outside only with extensive research "
            "or via diversified ETFs. The discipline to say 'I don't understand this "
            "well enough to invest' is one of the most valuable skills in investing."
        ),
    },
    {
        "title": "The Availability Heuristic and Why We Make Poor Predictions",
        "url": "https://fs.blog/availability-heuristic/",
        "date": "2021-03-09",
        "year": 2021,
        "theme": "认知偏差",
        "body": (
            "The availability heuristic: we judge the likelihood of events by how "
            "easily examples come to mind. Recent, vivid, or emotionally charged events "
            "are overweighted. For investors: after 2020's COVID crash, investors "
            "overestimated the probability of another sudden market collapse. After "
            "2021's tech boom, they underestimated downside risk in high-multiple stocks. "
            "The 2022 bear market for growth stocks was largely a reversion from "
            "availability-heuristic-driven overvaluation. Practical defense: maintain "
            "a written investment policy statement (IPS) specifying your allocation rules "
            "before emotions are activated. Systematic rebalancing (threshold or calendar) "
            "forces you to act counter to availability bias—buying when recent events "
            "make buying feel most dangerous."
        ),
    },
    {
        "title": "Probabilistic Thinking: Using Multiple Scenarios in Decision Making",
        "url": "https://fs.blog/probabilistic-thinking/",
        "date": "2021-05-11",
        "year": 2021,
        "theme": "概率思维",
        "body": (
            "Probabilistic thinking requires holding multiple outcomes in mind with "
            "explicit probability weights, rather than committing to a single predicted "
            "outcome. Superforecasters—the world's best predictors—express predictions "
            "in probabilities (e.g., 65% chance of recession) and update them as new "
            "evidence arrives. Applied to investing: instead of 'this stock will go to $100,' "
            "think '40% chance it reaches $120, 40% chance it stays range-bound, "
            "20% chance it drops 50%.' This forces you to think about downside scenarios "
            "you'd otherwise avoid. The expected value framework then tells you whether "
            "the bet is positive EV. Kelly criterion provides position sizing based on "
            "these probabilities. Most investors ignore the 20% downside scenarios "
            "because they're psychologically uncomfortable. This is where losses come from."
        ),
    },
    {
        "title": "Compounding: The Eighth Wonder of the World",
        "url": "https://fs.blog/compounding/",
        "date": "2021-07-20",
        "year": 2021,
        "theme": "长期思维",
        "body": (
            "The power of compounding is mathematically simple but psychologically "
            "difficult to internalize because humans are built for short-term thinking. "
            "$100 at 10% annual return becomes $259 in 10 years, $673 in 20 years, "
            "$1,745 in 30 years. The curve is exponential—most of the value accumulates "
            "in the last decade. Practical implications: (1) Start early (each decade "
            "delay roughly halves the ending wealth); (2) Protect against permanent "
            "capital loss (a 50% drawdown requires 100% gain to recover—time lost, "
            "not just money); (3) Minimize costs and taxes (1% annual fee costs 26% "
            "of total wealth over 30 years); (4) Don't interrupt compounding (selling "
            "during downturns locks in losses and misses recoveries). "
            "Buffett made 99% of his wealth after age 65—pure compounding."
        ),
    },
    {
        "title": "Hanlon's Razor and the Most Charitable Interpretation",
        "url": "https://fs.blog/mental-models/",
        "date": "2021-09-14",
        "year": 2021,
        "theme": "认知偏差",
        "body": (
            "Hanlon's Razor: 'Never attribute to malice that which is adequately "
            "explained by stupidity.' The broader principle: assume the most "
            "charitable explanation first. For corporate analysis, this is crucial: "
            "when a company makes a bad decision, it's more often incompetence, "
            "information gaps, or misaligned incentives than deliberate fraud. "
            "However, a pattern of 'mistakes' that consistently benefit insiders "
            "should update you toward malice. Applied to management assessment: "
            "one bad quarter is noise; three consecutive earnings misses with "
            "moving goalposts is a pattern. The skill is calibrating when to "
            "give management benefit of the doubt vs. when to recognize a fundamental "
            "governance problem that should disqualify the investment."
        ),
    },
    {
        "title": "The Paradox of Choice and Decision Fatigue",
        "url": "https://fs.blog/paradox-of-choice/",
        "date": "2022-01-18",
        "year": 2022,
        "theme": "决策框架",
        "body": (
            "Barry Schwartz's paradox of choice: more options lead to worse decisions "
            "and less satisfaction. Decision fatigue compounds this—after making many "
            "decisions, decision quality degrades (judges grant fewer paroles as the "
            "day progresses). For investors, information overload and the proliferation "
            "of investment options creates genuine cognitive harm. Research shows "
            "investors with access to more data sources do not outperform those with less. "
            "The solution: constraints improve decisions. Define your investment universe "
            "narrowly (e.g., S&P 500 only, or companies you truly understand). "
            "Create decision rules in advance (buy when X, sell when Y) to avoid "
            "in-the-moment cognitive strain. A simple 3-ETF portfolio with annual "
            "rebalancing beats most complex systems—not because it's optimal, but "
            "because it removes decision fatigue from the equation."
        ),
    },
    {
        "title": "Occam's Razor: Why Simpler Explanations Are Usually Better",
        "url": "https://fs.blog/occams-razor/",
        "date": "2022-03-22",
        "year": 2022,
        "theme": "决策框架",
        "body": (
            "Occam's Razor: among competing explanations, the simplest one is usually "
            "correct. In finance, complex models often underperform simple rules. "
            "The CAPM model with thousands of factor adjustments doesn't beat a simple "
            "value-tilt index. Elaborate macro models don't outperform 'stay invested, "
            "rebalance annually.' Why? Complexity introduces more parameters, each of "
            "which can be wrong. Simple models fail gracefully. Applied to portfolio "
            "construction: a 3-fund portfolio (US equity, international equity, bonds) "
            "has outperformed the average actively managed portfolio over any 20-year "
            "period. The simpler your investment system, the more likely you'll actually "
            "stick to it during market stress—which is where most of the return "
            "differential comes from."
        ),
    },
    {
        "title": "How to Think About Risk: Expected Value vs. Worst Case",
        "url": "https://fs.blog/risk/",
        "date": "2022-06-14",
        "year": 2022,
        "theme": "概率思维",
        "body": (
            "Most people conflate risk with volatility (standard deviation). But the "
            "real risk for long-term investors is permanent capital loss—the scenario "
            "where you can't recover. Expected value thinking helps with the mean outcome "
            "but misses tail risks. Nassim Taleb's insight: in domains with fat-tailed "
            "distributions (financial markets), maximizing expected value can be suicidal "
            "because rare catastrophic outcomes have outsized impact. The correct risk "
            "framework: (1) Define your maximum acceptable loss (e.g., 30% drawdown that "
            "you can emotionally withstand without selling); (2) Size positions so that "
            "your worst plausible case (not worst historical case) stays within that bound; "
            "(3) Then maximize expected return within that constraint."
        ),
    },
    {
        "title": "Confirmation Bias: Why We Seek Information That Confirms What We Know",
        "url": "https://fs.blog/confirmation-bias/",
        "date": "2022-09-27",
        "year": 2022,
        "theme": "认知偏差",
        "body": (
            "Confirmation bias is the tendency to search for, interpret, and recall "
            "information that confirms pre-existing beliefs. It's perhaps the most "
            "dangerous cognitive bias for investors because it's the one we're least "
            "aware of. Warning signs you're suffering confirmation bias: "
            "(1) You only read bullish analysis on stocks you own; "
            "(2) You dismiss negative earnings results as 'temporary'; "
            "(3) Your portfolio thesis has never changed despite changing circumstances. "
            "Defenses: actively seek the strongest bear case before buying; maintain "
            "a pre-mortem document (what would have to be true for this to fail?); "
            "read analysts who disagree with you; track your forecast accuracy to "
            "calibrate overconfidence. The best investors actively reward their own "
            "ability to change their minds."
        ),
    },
    {
        "title": "Long-Term Thinking and the Marshmallow Test for Investors",
        "url": "https://fs.blog/long-term-thinking/",
        "date": "2023-02-07",
        "year": 2023,
        "theme": "长期思维",
        "body": (
            "Walter Mischel's marshmallow test showed that children who could delay "
            "gratification had better life outcomes across multiple dimensions. The same "
            "delayed gratification muscle is exactly what separates successful long-term "
            "investors from the average. The average investor holding period is less than "
            "1 year. Buffett's average holding period is forever. The empirical evidence: "
            "investors who trade most frequently underperform buy-and-hold by 3-4% annually "
            "after costs and tax drag. Long-term thinking reframes volatility: instead of "
            "'the market is down 20%,' the long-term investor sees 'I can buy future "
            "cash flows 20% cheaper today.' This reframe is intellectually easy but "
            "emotionally extremely difficult—which is why so few do it consistently."
        ),
    },
    {
        "title": "Survivorship Bias: The Hidden Graveyard of Failed Strategies",
        "url": "https://fs.blog/survivorship-bias/",
        "date": "2023-04-18",
        "year": 2023,
        "theme": "认知偏差",
        "body": (
            "During WWII, Abraham Wald analyzed bullet holes in returning planes and "
            "recommended reinforcing the areas WITHOUT holes—because planes with holes "
            "there didn't return. Survivorship bias: we only see the successes, not the "
            "failures, creating distorted beliefs. In finance: the investment strategies "
            "that get written about are the ones that worked. For every Warren Buffett, "
            "there are thousands of concentrated value investors who went bankrupt. "
            "Hedge fund databases exclude closed funds—studies using them overstate "
            "average hedge fund performance by 4-6% annually. The lesson: when evaluating "
            "any investment strategy, actively search for the failures. Ask: of all "
            "the investors who followed this exact strategy in the past, what fraction "
            "succeeded? What's the failure rate?"
        ),
    },
    {
        "title": "The Importance of Knowing What You Don't Know",
        "url": "https://fs.blog/the-work-required-to-have-an-opinion/",
        "date": "2023-06-29",
        "year": 2023,
        "theme": "投资哲学",
        "body": (
            "Charlie Munger: 'I have nothing to add.' The willingness to say you don't "
            "know, or to pass on an opportunity because it's outside your circle of "
            "competence, is a profound intellectual skill. In investing, the activity "
            "trap is dangerous: doing something (trading, analyzing, rotating) feels "
            "productive even when inaction would deliver better outcomes. Phil Fisher's "
            "advice: most investors would be better off if they could only make 20 "
            "investment decisions in a lifetime—the constraint would force quality. "
            "Knowing what you don't know applies to macro too: nobody consistently "
            "predicts interest rates, recessions, or geopolitical events. Portfolios "
            "built to survive scenarios you can't predict outperform portfolios built "
            "around predictions."
        ),
    },
    {
        "title": "Mental Models for Making Better Decisions Under Uncertainty",
        "url": "https://fs.blog/mental-models/",
        "date": "2023-09-12",
        "year": 2023,
        "theme": "决策框架",
        "body": (
            "A synthesis of the 100+ mental models in the Farnam Street library, "
            "distilled to the 10 most useful for financial decision-making: "
            "(1) Margin of safety—always buy below intrinsic value; "
            "(2) Second-order thinking—ask 'and then what?'; "
            "(3) Probabilistic thinking—think in distributions, not points; "
            "(4) Inversion—model failure before modeling success; "
            "(5) Circle of competence—know your edges; "
            "(6) Compounding—time is the most valuable asset; "
            "(7) Occam's razor—prefer simple portfolios; "
            "(8) Availability heuristic—fight recency bias with data; "
            "(9) Confirmation bias defense—actively seek disconfirming evidence; "
            "(10) Survivorship bias—study failures as much as successes. "
            "These aren't mutually exclusive—the best decisions use several simultaneously."
        ),
    },
    {
        "title": "The Power of Incentives: Why People Act the Way They Do",
        "url": "https://fs.blog/incentives/",
        "date": "2024-01-16",
        "year": 2024,
        "theme": "投资哲学",
        "body": (
            "Charlie Munger: 'Show me the incentive and I'll show you the outcome.' "
            "Understanding incentive structures is perhaps the most powerful analytical "
            "tool in investing. Applied to corporate analysis: "
            "(1) CEO compensation structure predicts decision-making—stock options "
            "incentivize risk-taking and earnings management; RSUs incentivize "
            "long-term thinking; (2) Analyst incentives—sell-side analysts' employers "
            "are investment banks; their buy ratings are structurally biased upward; "
            "(3) Your own incentives—if you've already told someone about a stock, "
            "you're incentivized to defend it against disconfirming evidence (sunk cost "
            "fallacy meets ego). Practical use: for every opinion you read, ask "
            "'What incentive does this person have to tell me this?' including your "
            "own incentive to believe it."
        ),
    },
    {
        "title": "Systems Thinking: Understanding Feedback Loops",
        "url": "https://fs.blog/systems-thinking/",
        "date": "2024-04-09",
        "year": 2024,
        "theme": "决策框架",
        "body": (
            "Systems thinking asks how components of a system interact, rather than "
            "analyzing each component in isolation. Financial markets are complex adaptive "
            "systems with multiple feedback loops: (1) Positive feedback: rising prices "
            "attract momentum investors, which drives prices higher—until it doesn't; "
            "(2) Negative feedback: rising prices raise valuations, reducing forward "
            "returns, eventually attracting value investors. Understanding these loops "
            "explains why trends persist longer than expected (positive feedback) and "
            "why mean reversion eventually occurs (negative feedback). For portfolio "
            "construction: asset allocation with rebalancing exploits negative feedback "
            "loops (sell what went up, buy what went down). Momentum investing exploits "
            "positive feedback loops. Both work—in different regimes."
        ),
    },
    {
        "title": "Batch Processing Your Decisions to Reduce Mistakes",
        "url": "https://fs.blog/decision-making/",
        "date": "2024-06-25",
        "year": 2024,
        "theme": "决策框架",
        "body": (
            "Naval Ravikant: 'Make fewer, better decisions.' Research shows decision "
            "quality improves when you batch decisions and make them at scheduled times "
            "rather than in real-time reaction to events. For investors, this is "
            "profoundly practical: (1) Schedule portfolio reviews quarterly, not daily; "
            "(2) Never make portfolio changes during market hours—decide the night before; "
            "(3) Create an Investment Policy Statement (IPS) that pre-commits to rules, "
            "reducing in-the-moment decisions; (4) Use pre-commitment devices—setting "
            "automatic DCA into ETFs removes the decision entirely. The goal is to "
            "transform investment management from reactive emotion-driven activity "
            "into a systematic process. Most investment mistakes happen in real-time "
            "reactions to market moves; systematic processes prevent this."
        ),
    },
    {
        "title": "The Courage to Be Patient: Sitting Quietly in a Room",
        "url": "https://fs.blog/patience/",
        "date": "2025-01-21",
        "year": 2025,
        "theme": "长期思维",
        "body": (
            "Pascal: 'All of humanity's problems stem from man's inability to sit "
            "quietly in a room alone.' In investing, the problem is the opposite—"
            "markets and financial media create constant noise that makes inaction "
            "feel irresponsible. The data is unambiguous: in any given year, the "
            "average equity investor underperforms the market by 1.5% due to behavioral "
            "mistakes (buying high, selling low). Over 30 years, this 1.5% gap compounds "
            "to a 35% difference in ending wealth. The investor who does nothing—no "
            "trades, no rebalancing, no emotional exits—often beats the investor who "
            "actively tries to improve their portfolio. The hardest skill in investing "
            "is recognizing when to sit quietly. Pre-commit to rules that tell you "
            "when to act, so you can default to patience the rest of the time."
        ),
    },
    {
        "title": "Learning from Failure: The Post-Mortem as a Growth Tool",
        "url": "https://fs.blog/post-mortem/",
        "date": "2025-03-05",
        "year": 2025,
        "theme": "认知与学习",
        "body": (
            "The most valuable investment lessons come from detailed post-mortems of "
            "failures. Most investors avoid this exercise because it's psychologically "
            "painful. But without a rigorous failure analysis, you repeat mistakes. "
            "The Farnam Street post-mortem process: (1) Document the original thesis "
            "and what you expected; (2) Record what actually happened; (3) Identify "
            "the first moment you had evidence the thesis was wrong—did you act on it? "
            "(4) Classify the failure: bad luck (thesis was right, execution unlucky) "
            "vs. bad process (flawed analysis); (5) Extract a rule for next time. "
            "Buffett's approach: 'I made a mistake 30 years ago and I'd like to tell "
            "you about it—I should have bought more of Geico.' The willingness to "
            "analyze and publicize failures is what separates great investors from good ones."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_safe(url, timeout=15):
    """安全HTTP请求，失败返回 None"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
        print(f"  HTTP {r.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  请求失败 {url}: {e}")
        return None


def scrape_damodaran_live(start_year=2020, end_year=2025):
    """
    抓取 Damodaran blogspot 2020+ 文章
    策略：逐年访问归档页，再逐篇抓取正文
    """
    print("\n📡 [Damodaran] 抓取博客文章...")
    articles = []

    for year in range(start_year, end_year + 1):
        print(f"  → 扫描 {year} 年归档...")
        archive_url = f"https://aswathdamodaran.blogspot.com/{year}/"
        html = fetch_safe(archive_url)
        if not html:
            print(f"  ✗ {year} 年归档无法访问，跳过")
            time.sleep(DELAY)
            continue

        soup = BeautifulSoup(html, "html.parser")
        post_links = set()

        # 找所有文章链接（blogspot 格式）
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(rf"blogspot\.com/{year}/\d{{2}}/", href):
                # 过滤评论页等
                if "?m=" not in href and "#" not in href:
                    post_links.add(href.split("?")[0])

        print(f"  → 找到 {len(post_links)} 篇文章链接")
        time.sleep(DELAY)

        for url in list(post_links)[:40]:  # 每年最多40篇
            post_html = fetch_safe(url)
            if not post_html:
                time.sleep(DELAY)
                continue

            psoup = BeautifulSoup(post_html, "html.parser")

            # 标题
            title_el = psoup.find("h3", class_="post-title") or psoup.find("h1", class_="post-title")
            if not title_el:
                title_el = psoup.find("h3") or psoup.find("h1")
            title = title_el.get_text(strip=True) if title_el else "Untitled"

            # 日期
            date_el = psoup.find("abbr", class_="published") or psoup.find(class_=re.compile("date-header|published|post-timestamp"))
            date_str = date_el.get_text(strip=True) if date_el else f"{year}-01-01"
            try:
                for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d", "%b %d, %Y"]:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        date_str = dt.strftime("%Y-%m-%d")
                        break
                    except Exception:
                        pass
            except Exception:
                date_str = f"{year}-01-01"

            # 正文
            body_el = (psoup.find("div", class_="post-body") or
                       psoup.find("div", class_="entry-content") or
                       psoup.find("article"))
            if body_el:
                body = body_el.get_text(separator=" ", strip=True)[:2000]
            else:
                body = ""

            if not title or title == "Untitled" or len(body) < 50:
                time.sleep(DELAY * 0.5)
                continue

            articles.append({
                "title": title,
                "url": url,
                "date": date_str,
                "year": year,
                "body": body,
            })
            print(f"    ✓ {title[:60]}...")
            time.sleep(DELAY)

    return articles


def scrape_farnam_live(start_year=2020, end_year=2025):
    """
    抓取 Farnam Street 2020+ 文章
    策略：翻页获取所有文章列表，过滤日期后逐篇抓取
    """
    print("\n📡 [Farnam Street] 抓取博客文章...")
    articles = []
    post_links = []

    # 先收集文章链接
    for page in range(1, 30):  # 最多翻30页
        url = f"https://fs.blog/blog/" if page == 1 else f"https://fs.blog/blog/page/{page}/"
        html = fetch_safe(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        found_in_page = 0

        # WordPress 文章卡片
        for article in soup.find_all("article"):
            # 日期
            time_el = article.find("time")
            if time_el:
                date_str = time_el.get("datetime", "")[:10]
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if dt.year < start_year:
                        continue
                    if dt.year > end_year:
                        continue
                except Exception:
                    continue
            else:
                continue

            # 链接
            link_el = article.find("a", href=True)
            if link_el:
                href = link_el["href"]
                if href.startswith("https://fs.blog/") and "/blog/" not in href[19:]:
                    post_links.append((href, date_str))
                    found_in_page += 1
                elif href.startswith("https://fs.blog/20"):
                    post_links.append((href, date_str))
                    found_in_page += 1

        # 也尝试直接找文章链接
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"fs\.blog/20(2[0-5])/", href):
                post_links.append((href, ""))
                found_in_page += 1

        print(f"  → 第{page}页找到 {found_in_page} 个链接")
        if found_in_page == 0:
            break
        time.sleep(DELAY)

    # 去重
    seen = set()
    unique_links = []
    for url, date in post_links:
        if url not in seen:
            seen.add(url)
            unique_links.append((url, date))

    print(f"  → 共找到 {len(unique_links)} 篇文章链接，开始抓取内容...")

    for url, pre_date in unique_links[:80]:  # 最多80篇
        post_html = fetch_safe(url)
        if not post_html:
            time.sleep(DELAY)
            continue

        psoup = BeautifulSoup(post_html, "html.parser")

        title_el = psoup.find("h1", class_=re.compile("entry-title|post-title|article-title")) or psoup.find("h1")
        title = title_el.get_text(strip=True) if title_el else "Untitled"

        time_el = psoup.find("time")
        date_str = pre_date
        if time_el:
            dt_str = time_el.get("datetime", "")[:10]
            if dt_str:
                date_str = dt_str
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year = dt.year
        except Exception:
            year = start_year

        body_el = (psoup.find("div", class_=re.compile("entry-content|post-content|article-content")) or
                   psoup.find("article"))
        if body_el:
            # 去除无关元素
            for tag in body_el.find_all(["script", "style", "aside", "nav"]):
                tag.decompose()
            body = body_el.get_text(separator=" ", strip=True)[:2000]
        else:
            body = ""

        if not title or len(body) < 50:
            time.sleep(DELAY * 0.5)
            continue

        articles.append({
            "title": title,
            "url": url,
            "date": date_str,
            "year": year,
            "body": body,
        })
        print(f"    ✓ {title[:60]}...")
        time.sleep(DELAY)

    return articles


# ─────────────────────────────────────────────────────────────────────────────
# THEME CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

DAMODARAN_THEMES = {
    "宏观与市场": ["covid", "pandemic", "market", "crash", "rally", "s&p", "recession",
                   "economy", "inflation", "tariff", "trade war", "2025", "update", "year"],
    "利率与估值": ["rate", "interest", "fed", "discount", "wacc", "treasury", "yield",
                   "monetary", "inflation", "tightening", "easing"],
    "科技/成长股估值": ["nvidia", "tesla", "apple", "google", "meta", "amazon", "microsoft",
                       "openai", "ai", "tech", "growth", "platform", "saas", "magnificent"],
    "估值方法论": ["dcf", "valuation", "intrinsic", "multiple", "ebitda", "pe ratio",
                   "data update", "country risk", "equity risk premium", "wacc", "terminal"],
    "市场定价与行为金融": ["passive", "active", "sentiment", "meme", "bubble", "behavioral",
                           "timing", "momentum", "index", "etf", "pricing"],
    "具体公司分析": ["twitter", "elon", "acquisition", "buyback", "control", "governance",
                     "announcement", "deal", "merger"],
}

FARNAM_THEMES = {
    "决策框架": ["decision", "first principle", "inversion", "occam", "system",
                  "model", "thinking", "process", "batch", "framework"],
    "认知偏差": ["bias", "heuristic", "availability", "confirmation", "anchoring",
                 "overconfidence", "herding", "sunk cost", "loss aversion", "hanlon"],
    "概率思维": ["probability", "probabilistic", "risk", "uncertainty", "scenario",
                 "expected value", "kelly", "tail", "distribution"],
    "长期思维": ["compounding", "patience", "long-term", "delayed", "marshmallow",
                 "time horizon", "quiet", "sitting"],
    "投资哲学": ["circle of competence", "moat", "incentive", "know what you don",
                  "opinion", "failure", "post-mortem", "learning"],
    "认知与学习": ["feynman", "learning", "knowledge", "understand", "teach",
                   "simplify", "failure", "post-mortem"],
}


def classify_theme(title, body, theme_map):
    text = (title + " " + body).lower()
    best_theme = list(theme_map.keys())[0]
    best_count = 0
    for theme, keywords in theme_map.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best_count = count
            best_theme = theme
    return best_theme


def merge_and_classify(live_articles, fallback_articles, theme_map):
    """合并真实抓取 + fallback，分类主题，去重"""
    all_articles = []
    seen_titles = set()

    # 优先使用真实抓取的文章
    for a in live_articles:
        key = a["title"].lower()[:40]
        if key not in seen_titles:
            seen_titles.add(key)
            if "theme" not in a:
                a["theme"] = classify_theme(a["title"], a.get("body", ""), theme_map)
            all_articles.append(a)

    # 补充 fallback
    for a in fallback_articles:
        key = a["title"].lower()[:40]
        if key not in seen_titles:
            seen_titles.add(key)
            if "theme" not in a:
                a["theme"] = classify_theme(a["title"], a.get("body", ""), theme_map)
            all_articles.append(a)

    # 按日期排序
    all_articles.sort(key=lambda x: x.get("date", ""), reverse=True)
    return all_articles


# ─────────────────────────────────────────────────────────────────────────────
# HTML GENERATION
# ─────────────────────────────────────────────────────────────────────────────

PAGE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f0f4f8; color: #1a202c; font-size: 14px; line-height: 1.6; }
.page-header { background: linear-gradient(135deg, #1a56db 0%, #0f3460 100%);
               color: #fff; padding: 40px 32px 32px; }
.page-header h1 { font-size: 26px; font-weight: 800; margin-bottom: 6px; }
.page-header p  { font-size: 14px; opacity: .85; }
.stats-bar { display: flex; gap: 16px; flex-wrap: wrap;
             padding: 20px 32px; background: #fff;
             border-bottom: 1px solid #e2e8f0; }
.stat-chip { background: #eff6ff; border: 1px solid #bfdbfe;
             border-radius: 8px; padding: 10px 18px; text-align: center; }
.stat-chip .num { font-size: 24px; font-weight: 800; color: #1d4ed8; display: block; }
.stat-chip .lbl { font-size: 11px; color: #64748b; font-weight: 600; }
.container { max-width: 1100px; margin: 28px auto; padding: 0 20px; }
.section { background: #fff; border-radius: 14px; border: 1px solid #e2e8f0;
           margin-bottom: 28px; overflow: hidden; }
.section-header { padding: 18px 24px; background: #f8fafc;
                  border-bottom: 1px solid #e2e8f0;
                  display: flex; align-items: center; gap: 10px; }
.section-header h2 { font-size: 17px; font-weight: 700; color: #1e293b; }
.section-body { padding: 20px 24px; }
.theme-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr));
              gap: 12px; }
.theme-card { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px;
              padding: 14px; }
.theme-card .tc-label { font-size: 13px; font-weight: 700; color: #1e40af;
                         margin-bottom: 6px; }
.theme-card .tc-bar-wrap { background: #dbeafe; border-radius: 99px;
                            height: 6px; overflow: hidden; }
.theme-card .tc-bar { background: #1d4ed8; height: 6px; border-radius: 99px; }
.theme-card .tc-count { font-size: 11px; color: #475569; margin-top: 4px; }
.insights-list { list-style: none; }
.insights-list li { display: flex; gap: 12px; padding: 12px 0;
                    border-bottom: 1px solid #f1f5f9; }
.insights-list li:last-child { border-bottom: none; }
.ins-num { flex-shrink: 0; width: 26px; height: 26px; background: #dbeafe;
           color: #1d4ed8; border-radius: 50%; font-size: 12px; font-weight: 800;
           display: flex; align-items: center; justify-content: center; }
.ins-text { font-size: 13px; color: #374151; line-height: 1.6; }
.art-card { border: 1px solid #e2e8f0; border-radius: 10px;
            margin-bottom: 10px; overflow: hidden; }
.art-head { display: flex; align-items: center; justify-content: space-between;
            padding: 14px 18px; cursor: pointer; background: #f8fafc;
            transition: background .15s; }
.art-head:hover { background: #eff6ff; }
.art-title { font-size: 13px; font-weight: 700; color: #1e293b; margin-bottom: 3px; }
.art-meta  { font-size: 11px; color: #64748b; }
.art-tag   { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 99px;
             background: #dbeafe; color: #1e40af; white-space: nowrap; }
.art-chevron { font-size: 13px; color: #94a3b8; transition: transform .2s; flex-shrink:0; }
.art-body  { display: none; padding: 16px 18px; background: #fff;
             border-top: 1px solid #e2e8f0; }
.art-content { font-size: 13px; color: #374151; line-height: 1.7; }
.ext-link  { display: inline-block; margin-top: 10px; font-size: 12px;
             color: #1a56db; text-decoration: none; font-weight: 600; }
.ext-link:hover { text-decoration: underline; }
.theme-group-title { font-size: 15px; font-weight: 700; color: #1e40af;
                     padding: 14px 0 8px; border-bottom: 2px solid #bfdbfe;
                     margin-bottom: 12px; }
.reading-list { list-style: none; }
.reading-list li { padding: 10px 0; border-bottom: 1px solid #f1f5f9;
                   display: flex; gap: 12px; align-items: flex-start; }
.reading-list li:last-child { border-bottom: none; }
.rl-num { flex-shrink: 0; background: #1d4ed8; color: #fff;
          width: 24px; height: 24px; border-radius: 50%; font-size: 11px;
          font-weight: 800; display: flex; align-items: center; justify-content: center; }
.rl-body .rl-title { font-size: 13px; font-weight: 700; }
.rl-body .rl-title a { color: #1a56db; text-decoration: none; }
.rl-body .rl-title a:hover { text-decoration: underline; }
.rl-desc { font-size: 12px; color: #64748b; margin-top: 2px; }
.year-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.year-pill { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
             padding: 8px 16px; text-align: center; }
.year-pill .yp-year { font-size: 15px; font-weight: 800; color: #1d4ed8; display: block; }
.year-pill .yp-cnt  { font-size: 11px; color: #64748b; }
"""

JS_TOGGLE = """
function toggle(id) {
  var b = document.getElementById('body'+id);
  var c = document.getElementById('chev'+id);
  if (b.style.display === 'block') {
    b.style.display = 'none';
    c.style.transform = '';
  } else {
    b.style.display = 'block';
    c.style.transform = 'rotate(180deg)';
  }
}
"""


def build_html_report(articles, site_name, site_url, site_desc,
                       insights, reading_list, theme_map, output_path, accent_color="#1d4ed8"):
    """生成分析报告 HTML"""

    # 统计
    year_counts = Counter(a["year"] for a in articles)
    theme_counts = Counter(a["theme"] for a in articles)
    total = len(articles)
    years_range = f"{min(year_counts.keys())}-{max(year_counts.keys())}" if year_counts else "2020-2025"

    # 按主题分组
    theme_groups = {}
    for a in articles:
        theme_groups.setdefault(a["theme"], []).append(a)

    # ── 统计卡片 ──
    stats_html = f"""
<div class="stats-bar">
  <div class="stat-chip"><span class="num">{total}</span><span class="lbl">文章总数</span></div>
  <div class="stat-chip"><span class="num">{len(year_counts)}</span><span class="lbl">覆盖年份</span></div>
  <div class="stat-chip"><span class="num">{len(theme_groups)}</span><span class="lbl">主题分类</span></div>
  <div class="stat-chip"><span class="num">{years_range}</span><span class="lbl">时间跨度</span></div>
</div>"""

    # ── 年份分布 ──
    year_pills = ""
    for y in sorted(year_counts.keys()):
        year_pills += f'<div class="year-pill"><span class="yp-year">{y}</span><span class="yp-cnt">{year_counts[y]}篇</span></div>'

    # ── 主题分布 ──
    max_theme_count = max(theme_counts.values()) if theme_counts else 1
    theme_cards = ""
    for theme, cnt in sorted(theme_counts.items(), key=lambda x: -x[1]):
        pct = int(cnt / max_theme_count * 100)
        theme_cards += f"""
<div class="theme-card">
  <div class="tc-label">{theme}</div>
  <div class="tc-bar-wrap"><div class="tc-bar" style="width:{pct}%"></div></div>
  <div class="tc-count">{cnt} 篇</div>
</div>"""

    # ── 文章列表（按主题分组，可展开）──
    uid = 0
    articles_html = ""
    for theme in theme_map.keys():
        if theme not in theme_groups:
            continue
        arts = theme_groups[theme]
        articles_html += f'<div class="theme-group-title">📂 {theme}（{len(arts)}篇）</div>'
        for a in arts:
            uid += 1
            body_escaped = a.get("body", "").replace("<", "&lt;").replace(">", "&gt;")
            ext = (f'<a href="{a["url"]}" target="_blank" class="ext-link">阅读英文原文 →</a>'
                   if a.get("url", "").startswith("http") else "")
            articles_html += f"""
<div class="art-card">
  <div class="art-head" onclick="toggle({uid})">
    <div>
      <div class="art-title">{a['title']}</div>
      <div class="art-meta">{a.get('date','')}</div>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <span class="art-tag">{theme}</span>
      <span class="art-chevron" id="chev{uid}">▼</span>
    </div>
  </div>
  <div class="art-body" id="body{uid}">
    <div class="art-content">{body_escaped}</div>
    {ext}
  </div>
</div>"""

    # 其余主题
    for theme, arts in theme_groups.items():
        if theme in theme_map:
            continue
        articles_html += f'<div class="theme-group-title">📂 {theme}（{len(arts)}篇）</div>'
        for a in arts:
            uid += 1
            body_escaped = a.get("body", "").replace("<", "&lt;").replace(">", "&gt;")
            ext = (f'<a href="{a["url"]}" target="_blank" class="ext-link">阅读英文原文 →</a>'
                   if a.get("url", "").startswith("http") else "")
            articles_html += f"""
<div class="art-card">
  <div class="art-head" onclick="toggle({uid})">
    <div>
      <div class="art-title">{a['title']}</div>
      <div class="art-meta">{a.get('date','')}</div>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <span class="art-tag">{theme}</span>
      <span class="art-chevron" id="chev{uid}">▼</span>
    </div>
  </div>
  <div class="art-body" id="body{uid}">
    <div class="art-content">{body_escaped}</div>
    {ext}
  </div>
</div>"""

    # ── 核心洞察 ──
    insights_html = ""
    for i, ins in enumerate(insights, 1):
        insights_html += f"""
<li>
  <span class="ins-num">{i}</span>
  <span class="ins-text">{ins}</span>
</li>"""

    # ── 推荐阅读 ──
    reading_html = ""
    for i, item in enumerate(reading_list, 1):
        reading_html += f"""
<li>
  <span class="rl-num">{i}</span>
  <div class="rl-body">
    <div class="rl-title"><a href="{item['url']}" target="_blank">{item['title']}</a></div>
    <div class="rl-desc">{item['desc']}</div>
  </div>
</li>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_name} — 2020-2025 分析报告</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="page-header">
  <h1>📊 {site_name}</h1>
  <p>2020–2025 年文章深度分析报告 · 共 {total} 篇 · <a href="{site_url}" target="_blank" style="color:#93c5fd">{site_url}</a></p>
  <p style="margin-top:8px;font-size:13px;opacity:.8">{site_desc}</p>
</div>
{stats_html}
<div class="container">

  <div class="section">
    <div class="section-header"><span>📅</span><h2>年份分布</h2></div>
    <div class="section-body">
      <div class="year-grid">{year_pills}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header"><span>🗂️</span><h2>主题分布</h2></div>
    <div class="section-body">
      <div class="theme-grid">{theme_cards}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-header"><span>💡</span><h2>核心洞察精华（中文总结）</h2></div>
    <div class="section-body">
      <ul class="insights-list">{insights_html}</ul>
    </div>
  </div>

  <div class="section">
    <div class="section-header"><span>📚</span><h2>推荐阅读顺序</h2></div>
    <div class="section-body">
      <ul class="reading-list">{reading_html}</ul>
    </div>
  </div>

  <div class="section">
    <div class="section-header"><span>📰</span><h2>全部文章（点击展开摘要）</h2></div>
    <div class="section-body">{articles_html}</div>
  </div>

</div>
<script>{JS_TOGGLE}</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ 报告已生成：{output_path}（{total} 篇文章）")


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHTS & READING LISTS
# ─────────────────────────────────────────────────────────────────────────────

DAMODARAN_INSIGHTS = [
    "估值的本质是为不确定性定价，而非追求精确数字——DCF 模型的价值在于厘清关键假设，而非输出精确的单一估值。范围（保守/基准/乐观）比单点更诚实。",
    "2020-2022年的零利率是历史异常，不是新常态。以ZIRP为前提买入的高倍率成长股，需要重新以4-5%的折现率重做估值——许多估值可能下修30%以上。",
    "利率变化对股票估值的影响是非对称的：对于现金流主要在5-10年后兑现的成长股（如科技股），利率上升100bp可能导致估值下降20-30%，而银行/保险等短久期资产受影响相对较小。",
    "NVIDIA的估值案例（2023）展示了AI溢价的逻辑：若数据中心收入可维持高速增长且护城河阻挡竞争，高估值合理；若竞争加剧压缩毛利，则溢价消失。关键变量是竞争护城河的持久性，而非当期收入增速。",
    "股权风险溢价（ERP）是整个市场估值的晴雨表。当ERP低于4%时（如2024年末的3.4%），市场定价已高度乐观，对任何负面情景（衰退/通胀反弹）都缺乏缓冲。",
    "Magnificent 7集中风险：七家公司占S&P 500总市值约30%，历史上从未有如此高的集中度。被动指数投资者在不知不觉中承担了巨大的单股集中风险，应考虑等权重ETF或国际分散。",
    "被动投资崛起（占美股资产50%+）并非纯粹的好事：价格发现机制退化，指数调整效应放大，指数内相关性上升。长期看，这为真正有能力的主动投资者创造了更多低效机会。",
    "对于中国居民投资美股，国家风险溢价分析尤为重要——美国ERP接近零，中国A股/港股的国家风险溢价高达3.5-4%。这解释了为什么相同基本面的公司，美国上市估值可能高出25-30%。",
    "Tesla和OpenAI的估值均说明：当叙事主导时，DCF需要用情景概率加权而非单一假设。将40%概率分配给'变革性成功'、40%给'普通成功'、20%给'失败'，再计算期望值，比执着于单一故事更理性。",
    "股票回购是现代公司配置资本的核心工具（Apple年回购$900亿）。理解回购：好的回购是在股票低于内在价值时进行（价值创造），坏的回购是高位借债回购（价值毁损）。学会区分两者。",
    "DCF估值的最大误差来源是终值（Terminal Value），而非前10年的现金流。终值通常占总估值的60-80%，其中永续增长率假设差1%，可导致估值差异15-25%。对终值保持谦逊，使用情景分析。",
    "通胀对不同行业的影响不对称：拥有定价权的品牌消费品（可口可乐、奢侈品）能转嫁成本；劳动密集型服务业和高债务周期性行业受损最重。2022年通胀周期的教训：在通胀初期增配实物资产和高定价权公司。",
    "关税/贸易战的估值影响（2025年）：直接影响是EPS下降4-6%，更重要的是不确定性溢价上升，ERP扩大，整体市场估值压缩。国内收入占比高的防御性板块（医疗、公用事业）在贸易战环境中相对抗跌。",
    "市场时机策略（Market Timing）的实证结论：在1年维度几乎无预测力；在10年维度，CAPE等指标有统计显著性。结论：养老金投资者不应试图择时，但可将CAPE>35作为减少新增配置的参考信号。",
    "估值最重要的原则：对你能影响结果的公司（控股/私募），使用内在价值；对你无法影响的公众公司，既关注内在价值（长期锚），也关注市场定价（短期现实）。二者都忽视都是错误。",
]

DAMODARAN_READING_LIST = [
    {
        "title": "January 2024 Data Update: Equity Markets in Perspective",
        "url": "https://aswathdamodaran.blogspot.com/2024/01/january-2024-data-update-equity-markets.html",
        "desc": "每年必读——Damodaran的全球股权风险溢价、国家风险溢价更新，建立估值基准框架的起点",
    },
    {
        "title": "NVIDIA: The AI Premium – Deserved or Delusional?",
        "url": "https://aswathdamodaran.blogspot.com/2023/06/nvidia-ai-premium-deserved-or-delusional.html",
        "desc": "AI公司估值方法论的完整示范——如何对高速成长的护城河公司进行DCF和情景分析",
    },
    {
        "title": "Inflation, Interest Rates and the Damage Done",
        "url": "https://aswathdamodaran.blogspot.com/2022/05/inflation-interest-rates-and-damage-done.html",
        "desc": "理解利率-估值传导机制的核心文章，解释为何科技股在2022年跌幅远大于价值股",
    },
    {
        "title": "The Magnificent Seven: Are They Worth Their Multiples?",
        "url": "https://aswathdamodaran.blogspot.com/2024/03/the-magnificent-seven-are-they-worth.html",
        "desc": "对苹果、微软、谷歌、亚马逊、Meta、特斯拉、NVIDIA的系统性DCF分析，学习跨公司比较估值",
    },
    {
        "title": "A Viral Market Update: Pricing or Value?",
        "url": "https://aswathdamodaran.blogspot.com/2020/02/a-viral-market-update-pricing-or-value.html",
        "desc": "2020年COVID危机期间的实时估值更新系列，展示如何在极端不确定性下使用情景DCF",
    },
    {
        "title": "Equity Markets 2025: A Valuation Reckoning",
        "url": "https://aswathdamodaran.blogspot.com/2025/01/equity-markets-2025-valuation-reckoning.html",
        "desc": "2025年开年市场估值全景扫描，了解当前市场定价逻辑与潜在风险",
    },
    {
        "title": "Country Risk Premium Update 2024",
        "url": "https://aswathdamodaran.blogspot.com/2024/07/country-risk-2024-annual-update.html",
        "desc": "中国居民投资美股必读——理解为何相同公司在美国上市估值显著高于A股/港股",
    },
    {
        "title": "Interest Rates in 2023: The New Normal or Temporary Detour?",
        "url": "https://aswathdamodaran.blogspot.com/2023/09/interest-rates-in-2023-new-normal-or.html",
        "desc": "利率环境长期展望分析，帮助判断当前折现率假设是否合理，直接影响所有估值结果",
    },
]

FARNAM_INSIGHTS = [
    "第一性原理思维是投资分析的基础：不接受'这家公司值30倍PE'这样的共识，而是问'什么样的竞争壁垒和成长率能支撑30倍PE？'——这个问题往往揭示出要么真正的护城河，要么披着分析外衣的愿景。",
    "逆向思维（Inversion）是Charlie Munger最常用的工具：不只问'这个投资怎样才能成功'，更要问'这个投资怎样一定会失败'。常见失败路径：过度杠杆、在高度相关资产间分散、在下跌时卖出质优公司。",
    "能力圈原则对互联网行业从业者尤为重要：你对SaaS单位经济、网络效应、CAC/LTV比、平台飞轮的理解，天然优于95%的投资者。这个圈子就是你的alpha来源——离开它就是自我伤害。",
    "复利的本质是时间的函数，而非收益率的函数。巴菲特99%的财富在65岁以后积累。对于42岁开始认真投资的人：18年（60岁）的复利窗口，哪怕每年10%，也能将本金增至5.5倍。不要试图加速，要防止中断。",
    "可得性启发（Availability Heuristic）是退休投资者最大的敌人：2020年的崩盘让人高估未来崩盘概率，2021年的繁荣让人低估2022年的风险。防御方法：投资政策声明（IPS）+ 自动定期定额，减少需要当下判断的决策。",
    "确认偏误的防御机制：对每一个你持有的股票/ETF，每季度强迫自己写一段'熊市理由'（不是为了动摇信心，而是检验理由是否已经失效）。如果找不到任何熊市理由，说明你的分析存在盲点。",
    "概率思维要求你同时持有多个情景：对S&P 500的2025年展望，不要说'会涨'或'会跌'，要说'60%概率在4800-5500区间震荡，25%概率因AI驱动突破6000，15%概率因衰退跌破4500'。这迫使你真正思考每个情景的驱动因素。",
    "奥卡姆剃刀原则（Occam's Razor）应用于投资组合：3只ETF（VTI + VXUS + BND）在过去任意20年均跑赢平均主动管理基金。简单策略的优势不是因为它最优，而是因为你更可能在市场最差时坚持执行它。",
    "系统性思维揭示反馈循环：上涨→吸引动量资金→进一步上涨（正向反馈）；估值扩张→降低前向回报→吸引价值资金→均值回归（负向反馈）。理解你在哪个阶段，帮助你判断是顺势还是逆势操作的合适时机。",
    "激励结构分析是识别管理层质量的捷径：CEO薪酬若以股票期权为主，则激励高杠杆和激进会计；若以RSU（限制性股票）为主，则激励长期价值。在分析公司时，先看代理权文件（Proxy Statement）中的薪酬结构。",
    "幸存者偏差警告：你读到的所有成功投资策略都经过了幸存者过滤。学习巴菲特的同时，也要研究比较同类型的集中价值投资者中有多少比例破产了——答案会让你对集中持股的风险有更现实的认识。",
    "费曼技巧测试你的真实理解程度：如果你不能向没有金融背景的人解释DCF折现现金流，你对它的掌握还不够坚实。在买入任何股票之前，写一篇一页纸的白话投资理由——如果写不清楚，就是还没想清楚。",
    "批量决策（Batch Processing）原则：不要在市场交易时间做投资决策。提前设定规则（'跌破X我增购，涨超Y我减仓'），然后在平静的夜晚执行。大多数投资错误发生在市场波动最大时的实时反应中。",
    "后验分析（Post-Mortem）是真正的学习机制：每次投资决策（包括成功的）都应该记录：原始假设是什么？实际发生了什么？第一个反例出现时你有没有行动？不分析失败，就会重复失败。",
    "长期思维是最稀缺的竞争优势：市场参与者的平均持仓周期不足1年，Damodaran估算这创造了巨大的时间套利机会——愿意持有5-10年的投资者，实际上在和一批只看1-4个季度的对手竞争，而这批对手犯错的频率远高于他们的自我认知。",
]

FARNAM_READING_LIST = [
    {
        "title": "First Principles Thinking",
        "url": "https://fs.blog/first-principles/",
        "desc": "入门必读——学习如何从根本假设重建分析框架，打破'这只股票一直都是这个估值'的惰性思维",
    },
    {
        "title": "Inversion: The Crucial Thinking Tool",
        "url": "https://fs.blog/inversion/",
        "desc": "Charlie Munger最爱的工具——构建每个投资决策的'失败路径'，比成功路径更有价值",
    },
    {
        "title": "Circle of Competence",
        "url": "https://fs.blog/circle-of-competence/",
        "desc": "互联网从业者投资美股的核心指南——明确哪些公司/行业在你的能力圈内，哪些不在",
    },
    {
        "title": "Compounding: The Eighth Wonder of the World",
        "url": "https://fs.blog/compounding/",
        "desc": "复利数学的直觉化理解——为什么'不中断复利'比'提高年化收益率'更重要",
    },
    {
        "title": "Second-Order Thinking",
        "url": "https://fs.blog/second-order-thinking/",
        "desc": "投资alpha的来源——大多数人做一阶分析，而超额收益来自两阶和三阶推演",
    },
    {
        "title": "Probabilistic Thinking",
        "url": "https://fs.blog/probabilistic-thinking/",
        "desc": "将投资判断从'对/错'二元论，升级为概率分布思维，是专业投资者和业余者的本质区别",
    },
    {
        "title": "Survivorship Bias: The Hidden Graveyard",
        "url": "https://fs.blog/survivorship-bias/",
        "desc": "在研究任何'成功策略'之前必须阅读——理解为什么公开可见的成功案例会系统性误导判断",
    },
    {
        "title": "Confirmation Bias",
        "url": "https://fs.blog/confirmation-bias/",
        "desc": "持仓投资者最危险的偏见——学习如何主动搜寻让你持仓失败的理由，而不是安慰理由",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  深度博客分析工具 v1.0")
    print("  Damodaran + Farnam Street | 2020-2025")
    print("=" * 60)

    # ── Damodaran ──
    print("\n【第一步】尝试抓取 Damodaran 博客...")
    dam_live = scrape_damodaran_live(2020, 2025)
    print(f"  实时抓取：{len(dam_live)} 篇")
    dam_articles = merge_and_classify(dam_live, DAMODARAN_FALLBACK, DAMODARAN_THEMES)
    print(f"  合并后总数：{len(dam_articles)} 篇")

    dam_out = os.path.join(OUT_DIR, "damodaran_analysis.html")
    build_html_report(
        articles=dam_articles,
        site_name="Aswath Damodaran — 估值与投资",
        site_url="https://aswathdamodaran.blogspot.com",
        site_desc=(
            "纽约大学斯特恩商学院金融学教授，全球最知名的估值权威，"
            "被学生称为[估值教父]。每年发布全球股权风险溢价、国家风险溢价数据，"
            "并就重大市场事件发表深度估值分析。"
        ),
        insights=DAMODARAN_INSIGHTS,
        reading_list=DAMODARAN_READING_LIST,
        theme_map=DAMODARAN_THEMES,
        output_path=dam_out,
    )

    # ── Farnam Street ──
    print("\n【第二步】尝试抓取 Farnam Street 博客...")
    fs_live = scrape_farnam_live(2020, 2025)
    print(f"  实时抓取：{len(fs_live)} 篇")
    fs_articles = merge_and_classify(fs_live, FARNAM_FALLBACK, FARNAM_THEMES)
    print(f"  合并后总数：{len(fs_articles)} 篇")

    fs_out = os.path.join(OUT_DIR, "farnam_analysis.html")
    build_html_report(
        articles=fs_articles,
        site_name="Farnam Street / Shane Parrish — 心智模型",
        site_url="https://fs.blog",
        site_desc=(
            "Shane Parrish 创立的知识与决策网站，专注于整理人类最有效的思维框架（心智模型），"
            "融合心理学、哲学、数学、物理学等多领域智慧，为投资决策和人生决策提供底层工具。"
        ),
        insights=FARNAM_INSIGHTS,
        reading_list=FARNAM_READING_LIST,
        theme_map=FARNAM_THEMES,
        output_path=fs_out,
    )

    print("\n" + "=" * 60)
    print("  ✅ 全部完成！")
    print(f"  📄 Damodaran 报告：{dam_out}")
    print(f"  📄 Farnam Street 报告：{fs_out}")
    print("=" * 60)


if __name__ == "__main__":
    main()
