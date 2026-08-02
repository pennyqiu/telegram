# KOL 雷达 · 会话上下文速览（Session Bootstrap）

> 用途：新开 AI session 时 `@` 引用本文件即可快速载入环境与工作流，避免重复探索、节省 token。
> 维护：改动 `kol_radar` 结构 / KOL 列表 / 部署方式后，顺手更新本文件。
> 最后更新：2026-07-08

---

## 1. 这是什么

`kol_radar/` 是一个 **AI/半导体/美股 KOL 内容雷达**：每天按精确时间窗口抓取一批 X（推特）博主的原创推文 + 免费 newsletter 全文，生成网页简报和「喂给大模型的摘要」，可选自动 AI 分析。

- 本地仓库根：`/Users/hustqiu/Downloads/个人开发/telegram`
- Git 远端：`origin = https://github.com/pennyqiu/telegram.git`，主分支 `main`
- 生产服务器：`root@202.182.104.186`（主机名 `tg-club-system`），仓库在 `/app/telegram`，网站输出目录 `/var/www/kol-radar`

## 2. 文件地图（kol_radar/）

| 文件 | 作用 |
|---|---|
| `kol_targets.py` | **KOL 关注清单**（`TARGET_KOLS` 列表 + `CATEGORY_LABELS`）。增删关注对象只改这里 |
| `radar.py` | 主程序：抓取 + 生成网页/JSON。`from kol_targets import TARGET_KOLS` |
| `daily_cron.sh` | 每日定时脚本：算「中国时区昨天8点~今天8点」窗口 → 跑 radar.py → digest.py → ai_analyze.py |
| `fetch_one.py` | **临时**抓单个博主指定时间段推文导出 JSON（用于分析，不写进长期清单） |
| `digest.py` | 把当天 JSON 压成 AI 友好摘要 |
| `ai_analyze.py` | 可选：把摘要推给大模型自动分析（没配 key 会跳过，不报错） |
| `sources.py` | 数据源后端（x_api / nitter / rsshub）+ `fetch_tweets_archive` 全档案搜索 |
| `newsletters.py` / `article_extractor.py` | newsletter RSS 全文 / 文章正文抓取 |
| `.env` | 密钥与后端配置（**已 gitignore，不进版本库**） |
| `KOL雷达-操作手册.md` / `README.md` | 详细操作文档 |

## 3. 数据源 / 环境变量（kol_radar/.env）

- `KOL_SOURCE=x_api`（首选，失败自动降级 nitter/rsshub）
- `X_BEARER_TOKEN=...`（X 官方 API v2，需「按量付费 + search/all 全档案」权限；**密钥只在 .env，不要写进任何跟踪文件**）
- 计费：约 `$0.005/条读取`，用量极低（当前 KOL 数 × 每人几条/天），成本可忽略

## 4. 增 / 删一个 KOL（标准流程）

1. 编辑 `kol_targets.py` 的 `TARGET_KOLS`，新增一条 `KOLProfile`：
   ```python
   KOLProfile(
       name="显示名",
       handle="X用户名不含@",
       category="Hardware & Semiconductor",  # 必须是 CATEGORY_LABELS 里已有的 key，否则网页分组不显示
       focus="关注领域一句话",
       newsletter="",       # 有官方 newsletter 才填
       newsletter_rss="",   # 对应 RSS
       # 可选开关：
       # skip_tweets=True     # 该号在 X 无原创、只走 newsletter
       # skip_newsletter=True # newsletter 全付费墙、无价值
       # featured=True        # 简报页顶部置顶
   )
   ```
   - `CATEGORY_LABELS` 三个 key：`Hardware & Semiconductor`（半导体与硬件）、`Software & Cloud`（AI 软件与云）、`OSINT & Hyperscalers`（开源情报与超大厂）。要新分类得同时加进 `CATEGORY_LABELS`。
2. 本地验证：
   ```bash
   cd kol_radar && python3 -c "from kol_targets import TARGET_KOLS; print([k.handle for k in TARGET_KOLS])"
   ```
3. 提交 + 推送（见 §6 git 约定）。
4. 服务器拉取（见 §5），**务必赶在次日 08:30 CST 前**，当天定时任务即会带上新博主。

## 5. 部署 / 让「明天生效」

- 服务器 cron：`30 0 * * *`（UTC）≈ **中国时间每天 8:30** 触发 `daily_cron.sh /var/www/kol-radar 50`
- 抓取窗口 = 中国时区「昨天8点 ~ 今天8点」（脚本内部按 UTC+8 计算，不依赖服务器时区）
- **改动到服务器**：push 到 GitHub 后，在服务器执行：
  ```bash
  cd /app/telegram && git pull
  ```
  （本仓库惯例：本地 commit → push origin/main → 服务器 git pull。服务器 `.env` 已 gitignore，不会被覆盖）

## 6. Git 约定（重要）

- 提交身份：`hustqiu <hustqiu@users.noreply.github.com>`
- **不要修改 git config**（全局或本地）。本机未配 identity，提交时用一次性 inline 参数：
  ```bash
  git -c user.name=hustqiu -c user.email=hustqiu@users.noreply.github.com commit -m "..."
  ```
- 只提交本次真正改动的文件（如 `kol_radar/kol_targets.py`），仓库根下常有未相关的 md/pdf 改动，别一起 add。
- 未经明确要求不要 commit / push。

## 7. 分析某个博主的准确率（可复用方法论）

1. 抓数据：
   ```bash
   cd kol_radar && python3 fetch_one.py <handle> --since YYYY-MM-DD --until YYYY-MM-DD --max-tweets 800
   # 产物：output/single_<handle>_<since>_to_<until>.json
   ```
2. 从推文中分离：**可验证的事实陈述**（点位/财报/成交/宏观数据）与**方向性预测/目标价**。
3. 用联网搜索（Yahoo Finance / CNBC / SEC / 官方新闻稿）交叉核对事实，并判定已到期预测是否兑现。
4. 评估：事实准确度 + 预测命中率 + 分析框架合理性（注意永多偏见、幸存者偏差、宏观错配等）。
5. 数据密集的审计结论用 **Canvas** 呈现（`~/.cursor/projects/<workspace>/canvases/*.canvas.tsx`）。

## 8. 当前 KOL 名单（7 个，2026-07-08）

| handle | 名称 | 分类 | 备注 |
|---|---|---|---|
| `aleabitoreddit` | Serenity | 半导体与硬件 | featured 置顶；瓶颈理论；仅 X |
| `SemiAnalysis_` | Dylan Patel | 半导体与硬件 | + SemiAnalysis newsletter |
| `FoolAllTheTime` | Fabricated Knowledge | 半导体与硬件 | `skip_tweets`，只走 newsletter |
| `ArtofSpecuycky` | ArtofSpecuycky | 半导体与硬件 | 中文算力/美股/宏观/技术面；仅 X（本 session 新增） |
| `Beth_Kindig` | Beth Kindig | AI 软件与云 | + I/O Fund newsletter |
| `jaminball` | Jamin Ball | AI 软件与云 | + Clouded Judgement newsletter |
| `itsone` | itsone | 开源情报与超大厂 | OSINT，仅 X |

## 9. 本 session 变更记录

- 对 `@ArtofSpecuycky`（output 里已有 `single_ArtofSpecuycky_2026-04-05_to_now.json`，324 条）做了准确率审计：事实数据高度可靠、AI 牛市选股命中率高，但有结构性永多偏见、比特币短线择时偏弱、鹰派环境下满多的宏观错配风险。审计仪表盘为 Canvas：`ArtofSpecuycky-accuracy-audit.canvas.tsx`。
- 将 `ArtofSpecuycky` 加入 `TARGET_KOLS`（半导体与硬件类，仅抓 X）。提交 `8fc35f7` 已 push 到 `origin/main`；**服务器端 `git pull` 由用户手动执行**。
