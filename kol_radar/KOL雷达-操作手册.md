# 📡 KOL 雷达 · 操作手册

> 对应工具代码：`kol_radar/`（`radar.py` 为主入口）
> 本手册汇总调研结论 + 可直接执行的操作步骤，供后续维护/复用时按图执行。
> ⚠️ 仅供研究参考，不构成投资建议；请遵守 X 平台条款与各内容站点版权。

---

## 1. 核心结论速览

| 结论 | 说明 |
|------|------|
| ✅ 双轨数据源已实现并实测通过 | 「X 实时短评」+「官方 newsletter 深度全文」双轨，代码已在 `kol_radar/` 落地 |
| ✅ 免费轨道立即可用 | newsletter RSS 无需任何 token，4/6 位 KOL 已验证抓到全文 |
| ⚠️ X 官方 API 无免费层 | 2026-02 起按量付费，约 `$0.005/条`，本工具用量下约 **$7/月**，需信用卡+设消费上限 |
| ⚠️ 免费 X 抓取（Nitter/RSSHub）不稳定 | 公共实例常挂，仅作降级备选，不建议作为主力 |
| 📚 推文只是钩子，干货在 newsletter | Dylan Patel / Doug O'Laughlin / Jamin Ball 的 newsletter 已验证为**全文**，比推文信息密度高得多 |
| 🕰️ 官方全档案搜索已内置支持 | 2026 按量付费账户可直接用 `/2/tweets/search/all` 一次性回溯任意时间段（`radar.py --since`），约 $0.005/条；更省钱可选 TwitterAPI.io（~$0.00015/条）|
| 🈳 itsone 无覆盖 | 该 OSINT 账号无公开 newsletter，只能走 X 实时或历史推文归档，目前无免费方案 |

---

## 2. KOL 清单与数据源结论表

> 💡 想让某位博主在简报页最顶部单独置顶展示（带 ⭐ 高亮），在 `kol_targets.py` 里给他的
> `KOLProfile` 加一行 `featured=True` 即可，会自动脱离原来的分类区块单独显示在最前面。
> 目前 Serenity（`@aleabitoreddit`）已设为 `featured=True`。

在 `kol_targets.py` 维护，每人的最优数据源如下：

| 分类 | KOL | X handle | 官方 Newsletter（免费全文源） | 全文情况 |
|------|-----|----------|-------------------------------|----------|
| 半导体与硬核硬件 | Dylan Patel | `@SemiAnalysis_` | `semianalysis.com/feed` | ✅ 全文（实测 1877 词） |
| 半导体与硬核硬件 | Fabricated Knowledge | `@FoolAllTheTime` | `fabricatedknowledge.com/feed` | ✅ 全文（实测 7499 词，深度长文） |
| AI 软件与云 | Beth Kindig | `@Beth_Kindig` | `iofund.substack.com/feed` | ⚠️ 2026-02 起 Substack 关闭迁至 `io-fund.com`，需跟进改地址 |
| AI 软件与云 | Jamin Ball | `@jaminball` | `cloudedjudgement.substack.com/feed` | ✅ 全文（实测 2757 词，更新到当周） |
| 开源情报 | itsone | `@itsone` | 无 | ❌ 仅能走 X / 历史推文归档 |

> Matthew Ball（`@ballmatthew`）已于 2026-07 移除：newsletter 实测全部付费墙、RSS 只给几十字摘要，
> X 推文贡献也长期有限，整体拉取无分析价值，直接从 `kol_targets.py` 里删掉了整个条目（不只是关掉某个开关）。

---

## 3. 立即可执行：免费轨道（无需任何 token）

**用途**：日常研究，覆盖 4/6 位 KOL 的深度全文，零成本。

```bash
cd kol_radar
pip install -r requirements.txt      # 装 bs4，用于正文提取增强
python3 radar.py --source newsletter --news-limit 5
```

- [ ] 确认 `output/kol_briefing_<时间>.html` 生成并能在浏览器打开
- [ ] 检查 JSON 里 `newsletter_posts[].paywalled` 字段，`true` 表示只抓到预览
- [ ] 定期（如每周）重跑一次，观察哪些 KOL 更新了新文章

> 结论：这一步已实测通过，可直接作为日常使用方式，不必等 X API。

---

## 4. 可选执行：接入 X 官方 API（拿实时短评）

**成本预估**：6 KOL × 8 条/次 ≈ 48 次读取 × $0.005 ≈ $0.24/次，每天跑一次约 **$7/月**。

### 步骤清单

- [ ] 登录 <https://console.x.com>，接受 Developer Agreement
- [ ] 填写用途说明（≥250 字符，只读用途，示例见下）
- [ ] 创建 Project → 创建 App（如 `kol-radar`）
- [ ] 进入 App 的 **Keys and tokens**，生成 **Bearer Token**（只显示一次，立刻保存）
- [ ] 进入 **Billing**，绑定信用卡，充值 credits（如 $10）
- [ ] 设置**月度 spending limit**（如 $10），防止意外超支
- [ ] 把 Token 填入 `kol_radar/.env`：
  ```bash
  KOL_SOURCE=x_api
  X_BEARER_TOKEN=粘贴你的token
  ```
- [ ] 运行验证：
  ```bash
  python3 radar.py --source both --limit 8
  ```
- [ ] 确认简报中「⚡ X 实时短评」区块出现真实推文（而非"未抓到推文"提示）

### 用途说明模板（直接复制填表单）

```text
I am building a small personal research tool for my own use. It periodically
reads the public timelines of a handful of technology and semiconductor
analysts on X (for example @SemiAnalysis_ and @jaminball) and collects the
public articles they link to, so that I can review industry commentary on AI
infrastructure, chips, and cloud software in one place. The app only reads
public posts using the App-Only Bearer Token. It does not post, send messages,
or interact with any user, and it does not store, redistribute, or resell any
data. Usage is low-frequency, roughly once per day.
```

---

## 5. 已实现：历史推文一次性回溯（`--since`）

**触发条件**：需要一次性拉全某位 KOL 某段时间内的全部内容（例如"Serenity 今年以来的全部发言"），而不是只看最近 8 条。

**结论**：2026 按量付费账户已可直接调用官方全档案搜索 `/2/tweets/search/all`（以前只有 Academic/Enterprise 才能用），**已内置到 `sources.py`/`radar.py`，不需要接第三方**。

```bash
cd kol_radar
# 一次性拉 aleabitoreddit 今年以来全部原创推文，上限 1000 条（约 $5）防止超额扣费
python3 radar.py --handles aleabitoreddit --since 2026-01-01 --max-tweets 1000
```

- 默认排除转发/回复（只要原创内容），加 `--include-replies` 可连回复一起拉
- 输出单独存为 `output/kol_feed_archive_2026-01-01_to_now.json` 等，**不会覆盖**日常简报的 `index.html`/`latest.json`
- 成本约 `$0.005/条`，先用小的 `--max-tweets` 试跑确认总量，再决定是否放大
- 更省钱备选（第三方，按需评估）：

| 方案 | 适合场景 | 关键接口 | 成本 |
|------|----------|----------|------|
| **官方 `search/all`（已内置）** | 数据最全最准，无需额外接入 | `radar.py --since` | ~$0.005/条 |
| TwitterAPI.io | 想更省钱、量很大时 | `advanced_search`，支持 `from:user since: until:` | ~$0.00015/条 |
| Sorsa API | 拉某账号完整历史（无 3200 条上限） | `POST /v3/user-tweets`，回溯到 2006 | flat rate，Pro ~$199/月≈200万条 |
| Wayback Tweets / tweetarchive.org | 人工查单条已删除/旧推 | 网页 UI，无 API | 免费 |

- [ ] 用 `aleabitoreddit` 试跑 `--since 2026-01-01 --max-tweets 50` 验证效果和实际条数/费用比例，再决定是否放大到 `--max-tweets 1000+`
- [ ] 确认该模式只按需手动执行，不要写进 `crontab` 日常任务，避免重复扣费

### 拉完之后：压缩成适合喂 AI 分析的摘要（`digest.py`）

原始 JSON 字段多（id/source/backend/entities 等），直接喂给 AI 会浪费 token。跑完 `backfill_all.sh` 后：

```bash
python3 digest.py --input-dir /var/www/kol-radar
```

会在 `/var/www/kol-radar/digest/` 下生成：
- `digest_<handle>.md` × 每位博主一份（正文+引用链接+cashtags，按时间排序，多次抓取自动去重）
- `digest_all_timeline.md`：全部博主合并的时间线，适合横向对比分析（比如"这几位对英伟达的观点有什么分歧"）

生成的 `.md` 文件可以直接拖进 AI 对话或用 `@文件名` 引用分析。

---

## 6. 已知问题 / 待跟进项

- [ ] Beth Kindig 的 Substack 将于 2026-02 关闭并迁至 `io-fund.com`，需在 `kol_targets.py` 更新 `newsletter_rss`
- [x] Matthew Ball 的 RSS 只给摘要且全部付费墙、X 贡献也有限：已确认整体无分析价值，
      2026-07 从 `kol_targets.py` 里彻底移除关注（不再抓取，也不再展示）
- [ ] itsone 暂无覆盖方案，需决定是否值得为单一账号接入历史推文 API

---

## 7. 常用命令速查

```bash
python radar.py --source newsletter              # 只抓 newsletter 全文（免费）★日常默认
python radar.py --source tweets                   # 只抓 X 实时推文（需 token）
python radar.py --source both                     # 两者都抓
python radar.py --news-limit 3                    # 每人抓最近 3 篇 newsletter
python radar.py --limit 15                        # 每人抓 15 条推文
python radar.py --no-articles                     # 不抓推文里的外部文章正文（更快）
python radar.py --handles SemiAnalysis_,jaminball  # 只抓指定 KOL
python radar.py --output /var/www/kol             # 自定义输出目录（服务器部署）

# 一次性回溯某 KOL 指定时间段全部内容（全档案搜索，按量计费，见第 5 节）
python radar.py --handles aleabitoreddit --since 2026-01-01 --max-tweets 1000

# 批量回溯多位 KOL（逐个单独跑，产出各自独立的归档文件，见 backfill_all.sh）
./backfill_all.sh                                    # 默认参数
./backfill_all.sh 2026-01-01 1000 /var/www/kol-radar  # 自定义 起始日期/单人上限/输出目录
```

### 每日定时刷新（网站持续更新）

`daily_cron.sh` 用「精确时间窗口」抓取（中国时区昨天 8 点 ~ 今天 8 点），而不是"最近 N 条"——
好处是不会因为某天发太多而漏抓，也不会因为发太少而重复展示前一天的内容。窗口用 Python 显式按
UTC+8 计算，不依赖服务器系统时区。跑完直接覆盖写到 nginx 服务目录，网站 `index.html` 自动保持最新。

一次性把 cron 任务装好（幂等，重复执行不会重复添加）：

```bash
(crontab -l 2>/dev/null | grep -v 'daily_cron.sh'; echo "30 0 * * * /app/telegram/kol_radar/daily_cron.sh /var/www/kol-radar 50") | crontab -
crontab -l   # 确认写入成功
```

> ⚠️ 上面的 `30 0 * * *` 是假设**服务器系统时区是 UTC**（云 VPS 最常见的默认设置），
> 对应中国时间早上 8:30。先用 `date` 确认服务器当前时区：
> - 如果 `date` 打印的时间跟中国时间一致（服务器已经是 Asia/Shanghai 时区），改成 `30 8 * * *`
> - 如果服务器是 UTC，用上面默认的 `30 0 * * *` 即可
> （不管 cron 具体几点触发，`daily_cron.sh` 内部窗口计算都是按中国时区算的，只要 cron 别在
> 凌晨太早触发导致「今天8点」还没到就行，所以选在中国时间 8:30 左右触发最稳）

- 成本：不再是固定按上限收费，而是按「实际落在这 24 小时窗口内的推文数」计费——正常情况下
  7 位博主一天合计可能就几条到十几条，成本明显低于旧的「每人固定抓 15 条」方案
  （`50` 只是防失控的安全上限，不是每天都会用满）
- 日志会写到 `kol_radar/logs/daily_*.log`（已 gitignore，不会进版本库），自动清理 30 天前的旧日志
- 想验证效果，先手动跑一次看看：`./daily_cron.sh /var/www/kol-radar 50 && tail -30 logs/daily_*.log`

### 每日摘要 + AI 自动分析

`daily_cron.sh` 在 `radar.py` 抓完之后，会自动多跑两步（都写进了同一个日志文件）：

1. **`digest.py --daily-json`**：把当天 `latest.json`（含全部字段：id/source/backend 等元数据）
   压缩成一份精简 Markdown（只留日期/正文/引用链接/cashtag），写到 `<输出目录>/digest/daily_digest_latest.md`。
   这份文件本身就是「AI 友好格式」——体量小（一天通常几条到几十条），可以直接拖进任意 AI
   对话框，或在 Cursor 里 `@digest/daily_digest_latest.md` 直接问。
2. **`ai_analyze.py`**：尝试把上面这份摘要自动推送给一个大模型 API，生成结构化分析（今日要点/
   信号分歧/提及标的情绪/待跟踪线索），写成 `digest/analysis_latest.md` + `analysis_latest.html`。

**开启自动分析**：在 `kol_radar/.env` 里配置（任选一个 OpenAI 兼容供应商，无需改代码，参见
`.env.example` 里的详细注释）：

```bash
AI_API_KEY=sk-xxxxxxxx
AI_API_BASE=https://api.deepseek.com/v1   # 或 OpenAI / Moonshot / 智谱GLM 的 base_url
AI_MODEL=deepseek-chat
```

**没配置也没关系**：`ai_analyze.py` 会打印清晰提示并直接跳过，不会让 cron 报错中断，
`daily_digest_latest.md` 照常生成，手动拖给 AI 分析即可（这也是「推送不了就给手动方案」的兜底）。

配置好后，网站首页（`index.html`）footer 会自动出现「🤖 查看今日 AI 分析 →」的链接，
指向 `digest/analysis_latest.html`，浏览器直接打开就能看，不用改 nginx。

想单独测试这两步（不重新抓取，用已有的 `latest.json`）：

```bash
python3 digest.py --daily-json /var/www/kol-radar/latest.json --out-dir /var/www/kol-radar/digest
python3 ai_analyze.py --input /var/www/kol-radar/digest/daily_digest_latest.md --out-dir /var/www/kol-radar/digest
```

---

## 8. 后续可扩展方向（未决策，需用户拍板）

- [ ] 接 Telegram 推送：复用 `ib_quant` 现成的 Bot，把每日简报 + AI 分析结果推到手机
- [ ] 对「仅预览/付费」的 newsletter 文章自动抓正文页补全（公开站点有效，付费墙无效）
- [x] 历史推文回溯：已通过官方全档案搜索实现（`--since`，见第 5 节）
- [x] AI 友好摘要 + 自动推送分析：已实现（`digest.py --daily-json` + `ai_analyze.py`，见第 7 节）

> 详细的项目结构、JSON 字段说明、模块职责见同目录 [`README.md`](./README.md)；本手册只保留「结论 + 可执行步骤」。
