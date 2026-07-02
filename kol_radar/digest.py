#!/usr/bin/env python3
"""
KOL 雷达 · 摘要压缩工具

把 radar.py 产出的原始 JSON（含大量元数据字段：id/source/backend/entities 等）
压缩成更适合直接喂给 AI 分析的精简 Markdown 文档：
  - 去掉冗余字段，只保留 日期 / 正文 / 引用链接 / cashtags 等分析真正需要的信息
  - 按时间排序，同一博主多次抓取的重复推文自动按 id 去重
  - 同时生成「每位博主单独一份」+「全部博主合并的时间线」两种粒度，
    后者适合做跨博主横向对比分析

用法：
  python3 digest.py                                    # 汇总 output/ 下所有回溯归档 JSON
  python3 digest.py --input-dir /var/www/kol-radar      # 指定 JSON 所在目录（如 nginx 服务目录）
  python3 digest.py --pattern "kol_feed_*.json"         # 连日常简报的 JSON 也一起汇总
  python3 digest.py --out-dir /var/www/kol-radar/digest # 自定义摘要输出目录

  # 每日模式：只处理单个 JSON 文件（如当天 daily_cron.sh 刚产出的 latest.json），
  # 输出一份合并了「全部博主推文 + newsletter」的精简摘要，供当天的 AI 分析使用
  python3 digest.py --daily-json /var/www/kol-radar/latest.json --out-dir /var/www/kol-radar/digest
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_kols(paths: list) -> dict:
    """合并多个 JSON 文件里的 KOL 数据；同一 handle 出现多次时按推文 id / newsletter 链接去重。"""
    by_handle: dict = {}
    for p in paths:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  跳过 {p}（读取失败：{e}）")
            continue
        for kol in data.get("kols", []):
            handle = kol.get("handle", "")
            if not handle:
                continue
            entry = by_handle.setdefault(handle, {
                "name": kol.get("name", handle),
                "handle": handle,
                "focus": kol.get("focus", ""),
                "tweets": {},
                "newsletter_posts": {},
            })
            for tw in kol.get("tweets", []):
                key = tw.get("id") or tw.get("tweet_url") or tw.get("text", "")[:50]
                entry["tweets"][key] = tw
            for post in kol.get("newsletter_posts", []):
                key = post.get("link") or post.get("title", "")
                if key:
                    entry["newsletter_posts"][key] = post
    return by_handle


def _tag_str(tags: list) -> str:
    return f" [{'/'.join('$' + t for t in tags)}]" if tags else ""


def tweet_block(tw: dict) -> str:
    date = (tw.get("created_at") or "")[:10] or "未知日期"
    text = (tw.get("text") or "").strip()
    lines = [f"**{date}**{_tag_str(tw.get('cashtags') or [])}", text]
    for url in tw.get("article_urls", []) or []:
        lines.append(f"> 引用: {url}")
    return "\n".join(lines)


def post_block(post: dict) -> str:
    date = (post.get("published") or "")[:10] or "未知日期"
    title = post.get("title", "")
    excerpt = (post.get("excerpt") or "").strip()
    if len(excerpt) > 800:
        excerpt = excerpt[:800] + "…（已截断，完整正文见原 JSON）"
    paywalled = "（仅预览/付费）" if post.get("paywalled") else ""
    return f"**{date} · {title}**{paywalled}\n{excerpt}"


def build_kol_digest(entry: dict) -> str:
    tweets = sorted(entry["tweets"].values(), key=lambda t: t.get("created_at", ""))
    posts = sorted(entry["newsletter_posts"].values(), key=lambda p: p.get("published", ""))
    lines = [f"# {entry['name']} (@{entry['handle']})", "", f"> 关注领域：{entry['focus']}", ""]
    if posts:
        lines += [f"## 📚 Newsletter 全文（{len(posts)} 篇）", ""]
        for p in posts:
            lines += [post_block(p), ""]
    if tweets:
        lines += [f"## ⚡ 推文时间线（{len(tweets)} 条，已去重）", ""]
        for tw in tweets:
            lines += [tweet_block(tw), ""]
    if not tweets and not posts:
        lines.append("_暂无数据_")
    return "\n".join(lines)


def build_combined_timeline(by_handle: dict) -> str:
    items = []
    for entry in by_handle.values():
        for tw in entry["tweets"].values():
            items.append((tw.get("created_at", ""), entry["name"], entry["handle"], tw))
    items.sort(key=lambda x: x[0])

    lines = [f"# 全部博主推文时间线（{len(items)} 条，按时间排序，适合横向对比）", ""]
    for date, name, handle, tw in items:
        d = (date or "")[:10] or "未知日期"
        lines.append(f"**{d} · {name} (@{handle})**{_tag_str(tw.get('cashtags') or [])}")
        lines.append((tw.get("text") or "").strip())
        for url in tw.get("article_urls", []) or []:
            lines.append(f"> 引用: {url}")
        lines.append("")
    return "\n".join(lines)


def build_daily_digest(by_handle: dict, generated_at: str) -> str:
    """单日精简摘要：把当天所有博主的推文按时间合并成一条时间线 + newsletter 更新，
    体量小（一天通常几条到几十条），适合直接整篇喂给 AI 做当日分析。"""
    date = (generated_at or "")[:10] or "未知日期"
    lines = [f"# KOL 每日摘要 · {date}", "", f"> 生成时间：{generated_at}", ""]

    items = []
    for entry in by_handle.values():
        for tw in entry["tweets"].values():
            items.append((tw.get("created_at", ""), entry["name"], entry["handle"], tw))
    items.sort(key=lambda x: x[0])
    if items:
        lines += [f"## ⚡ 今日推文（{len(items)} 条，按时间排序）", ""]
        for created_at, name, handle, tw in items:
            d = (created_at or "").replace("T", " ").rstrip("Z") or "未知时间"
            lines.append(f"**{d} · {name} (@{handle})**{_tag_str(tw.get('cashtags') or [])}")
            lines.append((tw.get("text") or "").strip())
            for url in tw.get("article_urls", []) or []:
                lines.append(f"> 引用: {url}")
            lines.append("")

    posts = []
    for entry in by_handle.values():
        for post in entry["newsletter_posts"].values():
            posts.append((entry["name"], entry["handle"], post))
    posts.sort(key=lambda x: x[2].get("published", ""))
    if posts:
        lines += [f"## 📚 Newsletter 更新（{len(posts)} 篇）", ""]
        for name, handle, post in posts:
            lines.append(f"### {name} (@{handle})")
            lines.append(post_block(post))
            lines.append("")

    if not items and not posts:
        lines.append("_今日窗口内无新内容_")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="把 radar.py 产出的 JSON 压缩成适合喂 AI 分析的精简 Markdown 摘要")
    ap.add_argument("--input-dir", default=str(ROOT / "output"), help="JSON 文件所在目录")
    ap.add_argument("--pattern", default="kol_feed_archive_*.json", help="glob 匹配模式（默认只汇总历史回溯归档）")
    ap.add_argument("--out-dir", default="", help="摘要输出目录（默认 <input-dir>/digest/）")
    ap.add_argument("--daily-json", default="", help="每日模式：只处理这一个 JSON 文件，"
                                                       "输出单份当天合并摘要（跳过归档汇总逻辑）")
    args = ap.parse_args()

    if args.daily_json:
        src = Path(args.daily_json)
        if not src.exists():
            print(f"❌ 找不到文件：{src}")
            return
        data = json.loads(src.read_text(encoding="utf-8"))
        by_handle = load_kols([src])
        out_dir = Path(args.out_dir) if args.out_dir else src.parent / "digest"
        out_dir.mkdir(parents=True, exist_ok=True)
        date_tag = (data.get("generated_at", "") or "")[:10] or "unknown"
        out_path = out_dir / f"daily_digest_{date_tag}.md"
        out_path.write_text(build_daily_digest(by_handle, data.get("generated_at", "")), encoding="utf-8")
        latest_path = out_dir / "daily_digest_latest.md"
        latest_path.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
        total_tweets = sum(len(e["tweets"]) for e in by_handle.values())
        total_posts = sum(len(e["newsletter_posts"]) for e in by_handle.values())
        print(f"✅ {out_path.name}（{total_tweets} 条推文 + {total_posts} 篇 newsletter，固定入口：{latest_path.name}）")
        return

    input_dir = Path(args.input_dir)
    paths = sorted(input_dir.glob(args.pattern))
    if not paths:
        print(f"❌ 在 {input_dir} 下没找到匹配 {args.pattern!r} 的文件，先跑 radar.py / backfill_all.sh")
        return

    print(f"📥 读取 {len(paths)} 个文件：")
    for p in paths:
        print(f"   - {p.name}")

    by_handle = load_kols(paths)
    out_dir = Path(args.out_dir) if args.out_dir else input_dir / "digest"
    out_dir.mkdir(parents=True, exist_ok=True)

    print()
    for handle, entry in sorted(by_handle.items()):
        out_path = out_dir / f"digest_{handle}.md"
        out_path.write_text(build_kol_digest(entry), encoding="utf-8")
        print(f"✅ {out_path.name} （{len(entry['tweets'])} 条推文 + {len(entry['newsletter_posts'])} 篇 newsletter）")

    combined_path = out_dir / "digest_all_timeline.md"
    combined_path.write_text(build_combined_timeline(by_handle), encoding="utf-8")
    print(f"✅ {combined_path.name}（全部博主合并时间线，适合横向对比分析）")
    print(f"\n📂 摘要目录：{out_dir}")


if __name__ == "__main__":
    main()
