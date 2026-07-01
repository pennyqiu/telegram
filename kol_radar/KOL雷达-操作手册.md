# 📡 KOL 雷达 · 操作手册

> 对应工具代码：`kol_radar/`（`radar.py` 为主入口）
> 本手册汇总调研结论 + 可直接执行的操作步骤，供后续维护/复用时按图执行。
> ⚠️ 仅供研究参考，不构成投资建议；请遵守 X 平台条款与各内容站点版权。

---

## 1. 核心结论速览

| 结论 | 说明 |
|------|------|
| ✅ 双轨数据源已实现并实测通过 | 「X 实时短评」+「官方 newsletter 深度全文」双轨，代码已在 `kol_radar/` 落地 |
| ✅ 免费轨道立即可用 | newsletter RSS 无需任何 token，5/6 位 KOL 已验证抓到全文 |
| ⚠️ X 官方 API 无免费层 | 2026-02 起按量付费，约 `$0.005/条`，本工具用量下约 **$7/月**，需信用卡+设消费上限 |
| ⚠️ 免费 X 抓取（Nitter/RSSHub）不稳定 | 公共实例常挂，仅作降级备选，不建议作为主力 |
| 📚 推文只是钩子，干货在 newsletter | Dylan Patel / Doug O'Laughlin / Jamin Ball 的 newsletter 已验证为**全文**，比推文信息密度高得多 |
| 🕰️ 历史推文走第三方更划算 | TwitterAPI.io（~$0.00015/条）或 Sorsa API（flat rate，回溯到 2006），官方全档案仅企业级可用 |
| 🈳 itsone 无覆盖 | 该 OSINT 账号无公开 newsletter，只能走 X 实时或历史推文归档，目前无免费方案 |

---

## 2. KOL 清单与数据源结论表

在 `kol_targets.py` 维护，每人的最优数据源如下：

| 分类 | KOL | X handle | 官方 Newsletter（免费全文源） | 全文情况 |
|------|-----|----------|-------------------------------|----------|
| 半导体与硬核硬件 | Dylan Patel | `@SemiAnalysis` | `semianalysis.com/feed` | ✅ 全文（实测 1877 词） |
| 半导体与硬核硬件 | Fabricated Knowledge | `@PhabulousFab` | `fabricatedknowledge.com/feed` | ✅ 全文（实测 7499 词，深度长文） |
| AI 软件与云 | Beth Kindig | `@Beth_Kindig` | `iofund.substack.com/feed` | ⚠️ 2026-02 起 Substack 关闭迁至 `io-fund.com`，需跟进改地址 |
| AI 软件与云 | Jamin Ball | `@jaminball` | `cloudedjudgement.substack.com/feed` | ✅ 全文（实测 2757 词，更新到当周） |
| 宏观与应用科技 | Matthew Ball | `@ballmatthew` | `matthewball.co/all?format=rss` | ⚠️ RSS 仅给摘要（14 词），需抓正文页补全 |
| 开源情报 | itsone | `@itsone` | 无 | ❌ 仅能走 X / 历史推文归档 |

---

## 3. 立即可执行：免费轨道（无需任何 token）

**用途**：日常研究，覆盖 5/6 位 KOL 的深度全文，零成本。

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
analysts on X (for example @SemiAnalysis and @jaminball) and collects the
public articles they link to, so that I can review industry commentary on AI
infrastructure, chips, and cloud software in one place. The app only reads
public posts using the App-Only Bearer Token. It does not post, send messages,
or interact with any user, and it does not store, redistribute, or resell any
data. Usage is low-frequency, roughly once per day.
```

---

## 5. 可选执行：历史推文回溯

**触发条件**：需要深挖某位 KOL 过去某个时间点的具体观点（例如"Dylan Patel 在 2024 年对 CoWoS 产能的判断"）。

| 方案 | 适合场景 | 关键接口 | 成本 |
|------|----------|----------|------|
| TwitterAPI.io | 按关键词+时间窗口检索 | `advanced_search`，支持 `from:user since: until:` | ~$0.00015/条 |
| Sorsa API | 拉某账号完整历史（无 3200 条上限） | `POST /v3/user-tweets`，回溯到 2006 | flat rate，Pro ~$199/月≈200万条 |
| Wayback Tweets / tweetarchive.org | 人工查单条已删除/旧推 | 网页 UI，无 API | 免费 |

- [ ] 若决定接入，选一个方案在 `sources.py` 里新增一个后端函数（复用现有 `Tweet` 结构）
- [ ] 明确该后端只用于「按需查询」而非日常定时任务，避免不必要的调用费用

---

## 6. 已知问题 / 待跟进项

- [ ] Beth Kindig 的 Substack 将于 2026-02 关闭并迁至 `io-fund.com`，需在 `kol_targets.py` 更新 `newsletter_rss`
- [ ] Matthew Ball 的 RSS 只给摘要，若需要全文，需扩展 `article_extractor.py` 对 `matthewball.co` 正文页做二次抓取
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
python radar.py --handles SemiAnalysis,jaminball  # 只抓指定 KOL
python radar.py --output /var/www/kol             # 自定义输出目录（服务器部署）
```

定时任务示例（每天早上 8 点跑一次免费轨道）：

```bash
0 8 * * *  cd /path/to/kol_radar && /usr/bin/python3 radar.py --source newsletter >> radar.log 2>&1
```

---

## 8. 后续可扩展方向（未决策，需用户拍板）

- [ ] 接 Telegram 推送：复用 `ib_quant` 现成的 Bot，把每日简报推到手机
- [ ] 对「仅预览/付费」的 newsletter 文章自动抓正文页补全（公开站点有效，付费墙无效）
- [ ] 接入历史推文 API，支持按关键词回溯某 KOL 历史观点

> 详细的项目结构、JSON 字段说明、模块职责见同目录 [`README.md`](./README.md)；本手册只保留「结论 + 可执行步骤」。
