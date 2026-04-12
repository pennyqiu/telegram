"""
套餐初始化种子脚本

用法：
    cd tg-subscription
    python seed_plans.py

会向数据库写入《美股系统学习》的买断套餐及定制服务占位套餐。
如套餐 ID 已存在则跳过（幂等）。
"""

import asyncio
from app.core.database import AsyncSessionLocal
from app.models.plan import Plan


PLANS = [
    # ── 主产品：课程买断 ─────────────────────────────────────────
    {
        "id":             "us_stock_lifetime",
        "name":           "《美股系统学习》· 买断版",
        "description":    "一次付款，永久访问完整30节课（约39小时）及所有配套工具。",
        "stars_price":    4999,          # ≈ $65（Stars 汇率约 0.013 USD/Star）
        "cny_price_fen":  59800,         # ¥598 买断
        "billing_cycle":  "one_time",
        "trial_days":     0,
        "features": [
            "📈 完整30节课 · 约39小时",
            "🧮 估值实战：可口可乐 / 谷歌 / 微软 / 英伟达 / Meta / 亚马逊",
            "🛡️ 风险管理完整框架 + 压力测试",
            "🎯 养老规划全周期（42岁→退休）",
            "📊 投资监控仪表盘（持仓追踪 + 财报日历）",
            "🥚 CPA 跨境税务深度指南（彩蛋）",
            "🎧 通勤学习播客路线图",
            "♾️ 买断终身有效，内容持续更新",
        ],
        "channels":   [],   # 开通答疑频道后填入频道 ID
        "sort_order": 1,
        "is_active":  True,
    },

    # ── 扩展服务：定制咨询（暂不上线，is_active=False）────────────
    # 未来可按需开放，无需改代码，只需后台把 is_active 改为 True
    {
        "id":             "custom_consult_1h",
        "name":           "一对一投资组合诊断（1小时）",
        "description":    "针对你的持仓、目标、风险偏好，定制化分析与建议。",
        "stars_price":    3000,          # ≈ $39
        "cny_price_fen":  39800,         # ¥398
        "billing_cycle":  "one_time",
        "trial_days":     0,
        "features": [
            "📋 提前提交持仓明细",
            "💬 1小时视频/语音通话",
            "📄 书面分析报告（PDF）",
            "🔁 7天内免费跟进一次",
        ],
        "channels":   [],
        "sort_order": 2,
        "is_active":  False,   # 暂时不对外展示
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        created = 0
        skipped = 0
        for p in PLANS:
            existing = await db.get(Plan, p["id"])
            if existing:
                print(f"  跳过（已存在）: {p['id']}")
                skipped += 1
                continue
            plan = Plan(**p)
            db.add(plan)
            status = "✅ 已上线" if p["is_active"] else "🔒 暂未上线"
            print(f"  创建套餐 [{status}]: {p['name']} (id={p['id']})")
            created += 1
        await db.commit()
        print(f"\n完成：新建 {created} 个套餐，跳过 {skipped} 个。")


if __name__ == "__main__":
    asyncio.run(seed())
