# 📡 kol_radar · X/推特 KOL 言论与引用文章雷达

拉取一组 X（推特）科技/半导体/投研 KOL 的**最新言论**，自动提取他们引用的
**外部文章链接并抓回正文**，产出两份供「后续研究」的产物：

| 产物 | 用途 |
|------|------|
| `output/kol_feed_<时间>.json` | 结构化数据（推文 + 文章正文），可程序化二次处理 / 喂给 LLM |
| `output/kol_briefing_<时间>.html` | 按分类组织的可读简报，浏览器直接打开 |

> 本工具仅供研究，请遵守 X 平台条款与各文章站点版权。

---

## 🎯 关注的 KOL（在 `kol_targets.py` 中维护）

| 分类 | KOL | handle | 关注领域 |
|------|-----|--------|----------|
| 半导体与硬核硬件 | Dylan Patel | `@SemiAnalysis` | AI 算力架构、先进封装(CoWoS)、数据中心 CapEx |
| 半导体与硬核硬件 | Fabricated Knowledge | `@PhabulousFab` | 晶圆代工、半导体设备财务模型与估值 |
| AI 软件与云 | Beth Kindig | `@Beth_Kindig` | AI 软件变现、科技股买入区间 |
| AI 软件与云 | Jamin Ball | `@jaminball` | SaaS 估值倍数、云景气度 |
| 宏观与应用科技 | Matthew Ball | `@ballmatthew` | 3D 引擎、空间计算、具身智能 |
| 开源情报 | itsone | `@itsone` | 对冲基金资金流向、数据中心 OSINT |

增删关注对象：直接改 `kol_targets.py` 的 `TARGET_KOLS` 列表即可。

---

## ⚠️ 关于「抓 X 数据」的现实

X 对未授权抓取限制极严，没有任何一个免费来源是长期稳定的。本工具因此做成
**多后端 + 自动降级**结构，你至少要配置其中一个才能拿到数据：

| 后端 | 稳定性 | 成本 | 配置 |
|------|--------|------|------|
| `x_api` | ★★★★★ 最稳 | 按量付费 ~$0.005/读，本工具约 $7/月 | `X_BEARER_TOKEN` |
| `nitter` | ★★ 公共实例常挂 | 免费 | `NITTER_BASE`（建议自建） |
| `rsshub` | ★★★ 自建较稳 | 免费/自建 | `RSSHUB_BASE`（公共 `rsshub.app` 常限流） |

> 没有任何后端配置时，工具仍会跑完并生成空简报，并在末尾提示如何配置。

### 接入 X 官方 API（推荐）

> ⚠️ 2026-02 起 X 取消了免费层，新开发者一律「按量付费」：读取约 `$0.005/条`、
> 无月最低消费（不调用就 $0）。本工具用量极低（6 KOL×8 条 ≈ 48 读/次），
> 每天跑一次约 **$7/月**，可在 Developer Console 设消费上限封顶。

1. 用你的 X 账号登录 <https://console.x.com>，创建一个 App（用途选 read）。
2. 充值少量 credits（如 $10），并设置月度 spending limit 防超支。
3. 在 App 的 **Keys and tokens** 里生成 **Bearer Token**。
4. 把 token 填进 `.env` 的 `X_BEARER_TOKEN=`，确认 `KOL_SOURCE=x_api`。
5. `python radar.py` 即可拉到真实推文与引用文章。

> 省钱备选：第三方聚合 API（如 TwitterAPI.io）读取约 `$0.00015/条`，比官方便宜约 33×，
> 但属非官方渠道。如需接入可另行扩展一个后端。

---

## 🚀 快速开始

```bash
cd kol_radar
pip install -r requirements.txt          # 装 bs4（正文提取增强）

cp .env.example .env                      # 配置数据源
# 编辑 .env：填 X_BEARER_TOKEN（推荐），或 NITTER_BASE / RSSHUB_BASE

python radar.py                           # 每个 KOL 抓最近 8 条 + 引用文章
```

跑完后 macOS 会自动用浏览器打开简报。

### 常用参数

```bash
python radar.py --source newsletter              # 只抓 newsletter 全文（免费，无需 token）★推荐先用
python radar.py --source tweets                  # 只抓 X 实时推文（需 X_BEARER_TOKEN）
python radar.py --source both                    # 两者都抓（默认）
python radar.py --news-limit 3                   # 每人抓最近 3 篇 newsletter
python radar.py --limit 15                       # 每人抓 15 条推文
python radar.py --no-articles                    # 不抓推文里的外部文章正文（快）
python radar.py --handles SemiAnalysis,jaminball # 只抓指定 KOL
python radar.py --output /var/www/kol            # 自定义输出目录（服务器部署）
```

---

## 🛤️ 双轨数据源（实时 + 深度）

这 6 位 KOL 里 5 位运营官方 newsletter，**推文常只是给长文引流的钩子，真正的干货在 newsletter 全文里**。因此本工具做成双轨：

| 轨道 | 来源 | 成本 | 适合 |
|------|------|------|------|
| ⚡ 实时层 | X API（`@handle` 最近推文） | 按量付费 | 短评、转发、即时观点 |
| 📚 深度层 | 官方 newsletter RSS（全文） | **免费** | 完整论点、数据、估值模型 |

各博主 newsletter RSS（在 `kol_targets.py` 维护，实测可用）：

| 博主 | RSS | 全文 |
|------|-----|------|
| Dylan Patel | `semianalysis.com/feed` | ✅ |
| Doug O'Laughlin | `fabricatedknowledge.com/feed` | ✅ |
| Jamin Ball | `cloudedjudgement.substack.com/feed` | ✅ |
| Beth Kindig | `iofund.substack.com/feed` | ⚠️ Substack 2026-02 关闭，将迁 io-fund.com |
| Matthew Ball | `matthewball.co/all?format=rss` | ⚠️ 仅摘要，全文需抓正文页 |
| itsone | — | 无 newsletter，仅 X / 历史归档 |

> 付费 newsletter 的 RSS 通常只给免费预览（工具会标记「仅预览/付费」）。完整付费内容需用你订阅账号的**私有 RSS**（Substack 设置里的 `…/feed/private/<token>`，等同密码，勿提交 git）。

### 历史推文（一次性回溯某个时间段的全部内容）

好消息：2026 起 X 官方 API 改为按量付费后，**全档案搜索 `/2/tweets/search/all` 已直接对 pay-per-use 账户开放**（以前只有 Academic/Enterprise 能用），
不需要接第三方，本工具已内置支持，直接用现有的 `X_BEARER_TOKEN` 即可：

```bash
# 一次性拉取 aleabitoreddit 今年以来的全部原创推文（不含转发/回复），上限 1000 条防止超额扣费
python radar.py --handles aleabitoreddit --since 2026-01-01 --max-tweets 1000

# 指定结束日期、连回复也要
python radar.py --handles aleabitoreddit --since 2026-01-01 --until 2026-06-30 --include-replies
```

- 成本：约 `$0.005/条`（去重后 24h 内重复请求不二次计费），1000 条 ≈ $5，建议先用较小的 `--max-tweets` 试跑确认数量再放大。
- 输出不会覆盖日常简报的 `index.html`/`latest.json`，而是单独存为 `kol_feed_archive_<起始>_to_<结束>.json` / `kol_briefing_archive_...html`，专供研究用。
- 若想更省钱，第三方聚合 API 仍是补充选项：

| 途径 | 能力 | 成本 |
|------|------|------|
| **X 官方 `search/all`（已内置）** | 官方数据最全最准，支持全部查询操作符 | ~$0.005/条 |
| **TwitterAPI.io** | `advanced_search` 支持 `from:user since: until:` | ~$0.00015/条（比官方便宜约 33×）|
| **Sorsa API** | `/v3/user-tweets` 拉完整历史，无 3200 上限，回溯 2006 | flat rate，Pro ~$199/月 ≈ 200 万条 |
| Wayback Tweets / tweetarchive.org | 网页 UI 查单条旧推 | 免费（无 API）|

---

## 🧱 模块结构

```
kol_radar/
├── kol_targets.py       # KOL 清单（从 targetKOLs.ts 移植）
├── sources.py           # 多后端抓推文：x_api / nitter / rsshub + 自动降级
├── article_extractor.py # 跟随 t.co 重定向，抓外部文章并提取标题/正文摘要
├── radar.py             # 主程序：采集 → 输出 JSON + HTML 简报
├── requirements.txt
├── .env.example
└── output/              # 运行产物（已 gitignore）
```

---

## 📦 JSON 结构（供后续研究 / 程序化处理）

```jsonc
{
  "generated_at": "2026-06-30T13:40:00",
  "kol_count": 6,
  "kols": [
    {
      "name": "Dylan Patel",
      "handle": "SemiAnalysis",
      "category_label": "半导体与硬核硬件",
      "focus": "...",
      "backend": "x_api",
      "tweets": [
        {
          "text": "推文正文…",
          "created_at": "2026-06-29T...",
          "tweet_url": "https://x.com/SemiAnalysis/status/...",
          "article_urls": ["https://semianalysis.com/..."],
          "articles": [
            { "title": "文章标题", "final_url": "...", "excerpt": "正文摘要…", "word_count": 1234, "ok": true }
          ]
        }
      ]
    }
  ]
}
```

可直接把 `excerpt` 字段喂给 LLM 做摘要 / 主题聚类 / 观点提取。

---

## ⏰ 定时运行（可选）

```bash
# 每天早上 8 点抓一次，输出到固定目录
0 8 * * *  cd /path/to/kol_radar && /usr/bin/python3 radar.py --output /var/www/kol >> radar.log 2>&1
```
