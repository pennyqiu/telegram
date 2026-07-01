#!/usr/bin/env python3
"""
KOL 雷达 · 主程序

拉取 X(推特) 上目标 KOL 的最新言论，提取其引用的外部文章并抓取正文，
最终输出两份产物供「后续研究」：

  1. output/kol_feed_<日期>.json   —— 结构化数据（推文 + 文章正文），可程序化二次处理
  2. output/kol_briefing_<日期>.html —— 按分类组织的可读简报（沿用项目简报风格）

用法：
  python radar.py                 # 每个 KOL 抓最近 8 条，抓取引用文章
  python radar.py --limit 15      # 每个 KOL 抓最近 15 条
  python radar.py --no-articles   # 只抓推文，不抓外部文章正文（更快）
  python radar.py --handles SemiAnalysis_,jaminball   # 只抓指定 KOL

  # 回溯模式：一次性拉取指定时间段内某 KOL 的全部原创内容（全档案搜索，按量计费）
  python radar.py --handles aleabitoreddit --since 2026-01-01 --max-tweets 1000

数据源通过环境变量配置（见 .env.example）：
  KOL_SOURCE=x_api|nitter|rsshub   首选后端（失败自动降级）
  X_BEARER_TOKEN=...               官方 API（推荐）
  NITTER_BASE=https://...          Nitter 实例
  RSSHUB_BASE=https://...          RSSHub 实例
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# 允许从脚本所在目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kol_targets import TARGET_KOLS, CATEGORY_LABELS, KOLProfile  # noqa: E402
from sources import fetch_tweets, fetch_tweets_archive  # noqa: E402
from article_extractor import fetch_article  # noqa: E402
from newsletters import fetch_newsletter_safe  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"

# 可选加载 .env（无 python-dotenv 时用极简解析）
def _load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ════════════════════════════════════════════════════════════════════
#  采集
# ════════════════════════════════════════════════════════════════════

def collect(kols: list, limit: int, fetch_articles: bool,
            source: str = "both", news_limit: int = 5,
            since: str = "", until: str = "", max_tweets: int = 500,
            include_replies: bool = False) -> dict:
    results = []
    article_cache: dict = {}  # url -> Article.to_dict()，避免重复抓取
    want_tweets = source in ("tweets", "both")
    want_news = source in ("newsletter", "both")

    for kol in kols:
        print(f"  → @{kol.handle} ({kol.name})", flush=True)

        # ── 实时层：X 推文（或 --since 指定时间段的回溯抓取）──
        tweet_dicts = []
        backend = "skipped"
        if want_tweets and kol.skip_tweets:
            backend = "skipped(newsletter-only)"
            print(f"      推文: 已跳过（该账号确认无原创X内容，仅走 newsletter）")
        elif want_tweets:
            if since:
                tweets, backend = fetch_tweets_archive(
                    kol.handle, since, until, max_tweets, include_replies,
                )
            else:
                tweets, backend = fetch_tweets(kol.handle, limit)
            print(f"      推文: {len(tweets)} 条 [{backend}]")
            for tw in tweets:
                articles = []
                if fetch_articles:
                    for url in tw.article_urls:
                        if url not in article_cache:
                            print(f"      · 抓文章 {url[:70]}", flush=True)
                            article_cache[url] = fetch_article(url).to_dict()
                        articles.append(article_cache[url])
                d = tw.to_dict()
                d["articles"] = articles
                tweet_dicts.append(d)

        # ── 深度层：官方 newsletter 全文 ──
        news_dicts = []
        news_status = "skipped"
        if want_news:
            posts, news_status = fetch_newsletter_safe(kol.handle, kol.newsletter_rss, news_limit)
            if kol.newsletter_rss:
                print(f"      newsletter[{kol.newsletter}]: {len(posts)} 篇 [{news_status}]")
            news_dicts = [p.to_dict() for p in posts]

        results.append({
            "name": kol.name,
            "handle": kol.handle,
            "category": kol.category,
            "category_label": CATEGORY_LABELS.get(kol.category, kol.category),
            "focus": kol.focus,
            "backend": backend,
            "tweet_count": len(tweet_dicts),
            "tweets": tweet_dicts,
            "newsletter": kol.newsletter,
            "newsletter_rss": kol.newsletter_rss,
            "newsletter_status": news_status,
            "newsletter_count": len(news_dicts),
            "newsletter_posts": news_dicts,
        })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "kol_count": len(results),
        "limit_per_kol": limit,
        "news_limit_per_kol": news_limit,
        "articles_fetched": fetch_articles,
        "kols": results,
    }


# ════════════════════════════════════════════════════════════════════
#  HTML 简报
# ════════════════════════════════════════════════════════════════════

CSS = """
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#0f172a;color:#e2e8f0;margin:0;padding:24px}
  .container{max-width:1040px;margin:0 auto}
  h1{font-size:24px;margin-bottom:4px;color:#f8fafc}
  .subtitle{color:#94a3b8;font-size:13px;margin-bottom:24px}
  .cat{font-size:16px;font-weight:700;color:#38bdf8;margin:28px 0 12px;
       border-bottom:1px solid #1e293b;padding-bottom:6px}
  .kol-card{background:#1e293b;border:1px solid #334155;border-radius:12px;
            padding:18px;margin-bottom:18px}
  .kol-head{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
  .kol-name{font-size:16px;font-weight:700;color:#f8fafc}
  .kol-handle{color:#38bdf8;font-size:13px;text-decoration:none}
  .kol-focus{color:#94a3b8;font-size:12px;margin-bottom:12px;line-height:1.5}
  .backend{float:right;font-size:10px;color:#64748b;background:#0f172a;
           border-radius:10px;padding:2px 8px}
  .tweet{border-top:1px solid #334155;padding:12px 0}
  .tweet:first-of-type{border-top:none}
  .tweet-meta{font-size:11px;color:#64748b;margin-bottom:6px}
  .tweet-meta a{color:#64748b;text-decoration:none}
  .tweet-text{font-size:14px;line-height:1.6;color:#e2e8f0;white-space:pre-wrap}
  .tweet-tags{margin-top:6px}
  .tag{display:inline-block;background:#1e3a8a;color:#93c5fd;font-size:11px;
       font-weight:600;border-radius:4px;padding:2px 6px;margin:2px 4px 0 0}
  .article{background:#0f172a;border:1px solid #334155;border-radius:8px;
           padding:10px 12px;margin-top:8px}
  .article-title{font-size:13px;font-weight:600;color:#fbbf24}
  .article-title a{color:#fbbf24;text-decoration:none}
  .article-meta{font-size:10px;color:#64748b;margin:2px 0 6px}
  .article-excerpt{font-size:12px;color:#cbd5e1;line-height:1.6;max-height:120px;
                   overflow:auto}
  .article-err{font-size:11px;color:#f87171}
  .empty{color:#64748b;font-size:13px;font-style:italic}
  .footer{text-align:center;color:#475569;font-size:11px;margin-top:24px}
  .section-tag{font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:.05em;
               margin:14px 0 6px;text-transform:uppercase}
  .post{border-top:1px solid #334155;padding:10px 0}
  .post-title{font-size:14px;font-weight:600;color:#34d399}
  .post-title a{color:#34d399;text-decoration:none}
  .post-meta{font-size:10px;color:#64748b;margin:2px 0 6px}
  .post-excerpt{font-size:12px;color:#cbd5e1;line-height:1.6;max-height:150px;overflow:auto}
  .pill{display:inline-block;font-size:9px;padding:1px 6px;border-radius:8px;
        background:#422006;color:#fbbf24;margin-left:6px}
</style>
"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_html(data: dict, archive_index_exists: bool = False) -> str:
    ts = data["generated_at"].replace("T", " ")
    archive_link = (
        '<br><a href="archive_index.html" style="color:#38bdf8">🗂️ 查看各博主历史回溯归档 →</a>'
        if archive_index_exists else ""
    )

    # 按 category 分组（保持 CATEGORY_LABELS 的声明顺序）
    by_cat: dict = {}
    for kol in data["kols"]:
        by_cat.setdefault(kol["category"], []).append(kol)

    sections = []
    for cat, label in CATEGORY_LABELS.items():
        if cat not in by_cat:
            continue
        cards = []
        for kol in by_cat[cat]:
            tweets_html = []
            if kol["backend"] == "skipped":
                pass  # 本次未抓推文（--source newsletter）
            elif not kol["tweets"]:
                tweets_html.append(
                    f'<div class="empty">未抓到推文（{_esc(kol["backend"])}）。'
                    f'需配置 X API，详见 README。</div>'
                )
            for tw in kol["tweets"]:
                arts = []
                for a in tw.get("articles", []):
                    if a.get("ok") and a.get("excerpt"):
                        arts.append(f"""
            <div class="article">
              <div class="article-title"><a href="{_esc(a['final_url'] or a['url'])}" target="_blank">📄 {_esc(a['title'])}</a></div>
              <div class="article-meta">{_esc(a['final_url'] or a['url'])} · 约 {a.get('word_count',0)} 词</div>
              <div class="article-excerpt">{_esc(a['excerpt'])}</div>
            </div>""")
                    elif a.get("ok"):
                        arts.append(f"""
            <div class="article">
              <div class="article-title"><a href="{_esc(a['final_url'] or a['url'])}" target="_blank">🔗 {_esc(a['title'] or a['url'])}</a></div>
            </div>""")
                    else:
                        arts.append(f"""
            <div class="article">
              <div class="article-title"><a href="{_esc(a['url'])}" target="_blank">🔗 {_esc(a['url'])}</a></div>
              <div class="article-err">⚠️ 正文抓取失败：{_esc(a.get('error',''))}</div>
            </div>""")
                meta = _esc(tw.get("created_at", ""))
                if tw.get("tweet_url"):
                    meta = f'<a href="{_esc(tw["tweet_url"])}" target="_blank">{meta or "查看原推 ↗"}</a>'
                tags = tw.get("cashtags") or []
                tags_html = ""
                if tags:
                    badges = "".join(f'<span class="tag">${_esc(t)}</span>' for t in tags)
                    tags_html = f'<div class="tweet-tags">{badges}</div>'
                tweets_html.append(f"""
          <div class="tweet">
            <div class="tweet-meta">{meta}</div>
            <div class="tweet-text">{_esc(tw.get("text",""))}</div>
            {tags_html}
            {''.join(arts)}
          </div>""")

            # newsletter 全文区块
            news_html = []
            for p in kol.get("newsletter_posts", []):
                pill = '<span class="pill">仅预览/付费</span>' if p.get("paywalled") else ""
                news_html.append(f"""
            <div class="post">
              <div class="post-title"><a href="{_esc(p['link'])}" target="_blank">📰 {_esc(p['title'])}</a>{pill}</div>
              <div class="post-meta">{_esc(p['published'])} · 约 {p.get('word_count',0)} 词</div>
              <div class="post-excerpt">{_esc(p['excerpt'])}</div>
            </div>""")

            # 组装两个区块（有内容才显示对应标题）
            blocks = []
            if tweets_html:
                blocks.append('<div class="section-tag">⚡ X 实时短评</div>' + "".join(tweets_html))
            if news_html:
                label = _esc(kol.get("newsletter") or "Newsletter")
                blocks.append(f'<div class="section-tag">📚 {label} · 深度全文</div>' + "".join(news_html))
            if not blocks:
                blocks.append('<div class="empty">本次无内容。</div>')

            backend_label = kol['backend'] if kol['backend'] != 'skipped' else (kol.get('newsletter_status') or '')
            cards.append(f"""
        <div class="kol-card">
          <span class="backend">{_esc(backend_label)}</span>
          <div class="kol-head">
            <span class="kol-name">{_esc(kol['name'])}</span>
            <a class="kol-handle" href="https://x.com/{_esc(kol['handle'])}" target="_blank">@{_esc(kol['handle'])}</a>
          </div>
          <div class="kol-focus">🎯 {_esc(kol['focus'])}</div>
          {''.join(blocks)}
        </div>""")

        sections.append(f'<div class="cat">▎{_esc(label)}</div>\n{"".join(cards)}')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KOL 雷达简报 — {ts}</title>
{CSS}
</head>
<body>
<div class="container">
  <h1>📡 KOL 雷达 · X/推特言论与引用文章</h1>
  <div class="subtitle">
    生成时间：{ts} &nbsp;|&nbsp; 关注 {data['kol_count']} 位 KOL &nbsp;|&nbsp;
    数据源：{_esc(data.get('source','both'))} &nbsp;|&nbsp;
    推文/人 {data['limit_per_kol']} · 长文/人 {data.get('news_limit_per_kol','-')}
  </div>
  {''.join(sections)}
  <div class="footer">
    由 kol_radar/radar.py 自动生成 · 数据源见各卡片右上角标签<br>
    本工具仅供研究，请遵守 X 平台条款与各文章站点版权{archive_link}
  </div>
</div>
</body>
</html>"""


def build_archive_index(out_dir: Path) -> str:
    """扫描 out_dir 下所有回溯归档产物，按博主分组生成一个导航页，
    方便从一个入口跳转到各个博主的历史回溯简报，避免记文件名。"""
    entries = []
    for json_path in sorted(out_dir.glob("kol_feed_archive_*.json"), reverse=True):
        html_path = json_path.with_name(json_path.name.replace("kol_feed_", "kol_briefing_")).with_suffix(".html")
        if not html_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for kol in data.get("kols", []):
            if not kol.get("tweet_count") and not kol.get("newsletter_count"):
                continue
            entries.append({
                "name": kol.get("name", ""),
                "handle": kol.get("handle", ""),
                "tweet_count": kol.get("tweet_count", 0),
                "newsletter_count": kol.get("newsletter_count", 0),
                "generated_at": data.get("generated_at", ""),
                "file": html_path.name,
            })

    by_handle: dict = {}
    for e in entries:
        by_handle.setdefault(e["handle"], []).append(e)

    cards = []
    for handle, items in sorted(by_handle.items(), key=lambda kv: kv[0].lower()):
        name = items[0]["name"]
        rows = "".join(
            f"""
          <div class="tweet">
            <div class="tweet-meta">生成于 {_esc(it['generated_at'].replace('T',' '))}</div>
            <div class="tweet-text"><a href="{_esc(it['file'])}">📄 {it['tweet_count']} 条推文
              {f"+ {it['newsletter_count']} 篇 newsletter" if it['newsletter_count'] else ""}</a></div>
          </div>"""
            for it in items
        )
        cards.append(f"""
        <div class="kol-card">
          <div class="kol-head">
            <span class="kol-name">{_esc(name)}</span>
            <a class="kol-handle" href="https://x.com/{_esc(handle)}" target="_blank">@{_esc(handle)}</a>
          </div>
          {rows}
        </div>""")

    if not cards:
        cards.append('<div class="empty">暂无回溯归档，先用 --since 拉一次。</div>')

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KOL 雷达 · 历史回溯归档索引</title>
{CSS}
</head>
<body>
<div class="container">
  <h1>🗂️ KOL 雷达 · 历史回溯归档索引</h1>
  <div class="subtitle">
    更新时间：{ts} &nbsp;|&nbsp; 每位博主可能有多次回溯记录，按生成时间倒序排列
    &nbsp;|&nbsp; <a href="index.html" style="color:#38bdf8">← 返回日常简报</a>
  </div>
  {''.join(cards)}
  <div class="footer">由 kol_radar/radar.py --since 模式自动生成</div>
</div>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════
#  主程序
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="KOL 雷达：拉取 X KOL 言论 + newsletter 全文 + 引用文章")
    parser.add_argument("--source", choices=["tweets", "newsletter", "both"], default="both",
                        help="数据源：tweets=只抓X推文(需token) / newsletter=只抓newsletter(免费) / both=都抓（默认）")
    parser.add_argument("--limit", type=int, default=8, help="每个 KOL 抓取的推文条数（默认 8）")
    parser.add_argument("--news-limit", type=int, default=5, help="每个 KOL 抓取的 newsletter 篇数（默认 5）")
    parser.add_argument("--no-articles", action="store_true", help="不抓取推文里的外部文章正文")
    parser.add_argument("--handles", type=str, default="", help="只抓指定 handle（逗号分隔）")
    parser.add_argument("--output", type=str, default="", help="自定义输出目录")
    parser.add_argument("--since", type=str, default="",
                        help="回溯抓取起始日期(YYYY-MM-DD)，指定后改用全档案搜索一次性拉取该时间段全部内容"
                             "（需 X_BEARER_TOKEN 为 pay-per-use 权限，按量计费，务必配合 --max-tweets 控制成本）")
    parser.add_argument("--until", type=str, default="", help="回溯抓取结束日期(YYYY-MM-DD)，默认到现在")
    parser.add_argument("--max-tweets", type=int, default=500,
                        help="--since 模式下单个 KOL 最多抓取的条数上限，防止超额扣费（默认 500，约 $2.5）")
    parser.add_argument("--include-replies", action="store_true",
                        help="--since 模式下是否包含回复（默认只抓原创推文，不含转发/回复）")
    args = parser.parse_args()

    _load_env()

    kols = list(TARGET_KOLS)
    if args.handles:
        wanted = {h.strip().lower() for h in args.handles.split(",") if h.strip()}
        kols = [k for k in kols if k.handle.lower() in wanted]
        if not kols:
            print(f"❌ --handles 未匹配到任何 KOL：{args.handles}")
            sys.exit(1)

    out_dir = Path(args.output) if args.output else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.since:
        print(f"📡 回溯模式：{args.since} ~ {args.until or '现在'}，"
              f"每 KOL 上限 {args.max_tweets} 条（约 ${args.max_tweets * 0.005 * len(kols):.2f}）...")
    else:
        print(f"📡 开始采集 {len(kols)} 位 KOL（source={args.source}）...")
    data = collect(kols, args.limit, fetch_articles=not args.no_articles,
                   source=args.source, news_limit=args.news_limit,
                   since=args.since, until=args.until, max_tweets=args.max_tweets,
                   include_replies=args.include_replies)

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if args.since:
        # 归档文件名必须带 handle，否则不同博主同一时间段的回溯会互相覆盖
        handles_tag = "-".join(sorted(k.handle for k in kols)) if len(kols) <= 3 else f"{len(kols)}kols"
        tag = f"archive_{handles_tag}_{args.since}_to_{args.until or 'now'}"
    else:
        tag = stamp
    json_path = out_dir / f"kol_feed_{tag}.json"
    html_path = out_dir / f"kol_briefing_{tag}.html"
    html_str = build_html(data, archive_index_exists=(out_dir / "archive_index.html").exists())
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    json_path.write_text(json_str, encoding="utf-8")
    html_path.write_text(html_str, encoding="utf-8")

    if args.since:
        # 回溯抓取是一次性研究用途，不覆盖日常简报的固定入口
        print(f"   （回溯模式不会覆盖 index.html / latest.json，避免影响日常简报）")
        index_path = out_dir / "archive_index.html"
        index_path.write_text(build_archive_index(out_dir), encoding="utf-8")
        print(f"   归档导航页：{index_path}")
    else:
        # 固定文件名快照：始终指向「最新一次」，方便 nginx 用固定 index 托管
        # （历史时间戳文件仍保留，便于回看/对比）
        (out_dir / "index.html").write_text(html_str, encoding="utf-8")
        (out_dir / "latest.json").write_text(json_str, encoding="utf-8")

    total_tweets = sum(k["tweet_count"] for k in data["kols"])
    total_posts = sum(k["newsletter_count"] for k in data["kols"])
    print(f"\n✅ 完成：{total_tweets} 条推文 + {total_posts} 篇 newsletter")
    if args.since:
        print(f"   结构化数据：{json_path}")
        print(f"   可读简报：  {html_path}")
    else:
        print(f"   结构化数据：{json_path}（固定入口：{out_dir / 'latest.json'}）")
        print(f"   可读简报：  {html_path}（固定入口：{out_dir / 'index.html'}）")

    if total_tweets == 0 and args.source in ("tweets", "both"):
        print("\n⚠️ 没有抓到推文 —— X 数据源未配置或公共实例不可用。")
        print("   配置 X_BEARER_TOKEN 后用 --source tweets/both；或先用 --source newsletter（免费）。")

    if sys.platform == "darwin" and not args.output:
        os.system(f'open "{html_path}"')


if __name__ == "__main__":
    main()
