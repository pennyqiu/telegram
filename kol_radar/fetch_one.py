#!/usr/bin/env python3
"""
抓单个 X 账号「指定时间段」的全部原创推文，导出干净 JSON —— 专用于临时把某位
博主的历史推文喂给大模型分析，不写入 kol_targets.py 的长期关注清单。

依赖 kol_radar 已有的 sources.fetch_tweets_archive（X 官方 API 全档案搜索），
因此需要在同目录 .env 里配置具备「按量付费 / search/all 权限」的 X_BEARER_TOKEN。

用法：
  # 默认抓最近 3 个月
  python fetch_one.py ArtofSpecuycky

  # 自定义时间窗口 / 上限 / 是否含回复
  python fetch_one.py ArtofSpecuycky --since 2026-04-04 --until 2026-07-04 \
      --max-tweets 800 --include-replies

产物：output/single_<handle>_<since>_to_<until>.json
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import fetch_tweets_archive  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"


def _load_env():
    """极简 .env 解析（无 python-dotenv 依赖）。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description="抓单个 X 账号指定时间段的原创推文并导出 JSON")
    parser.add_argument("handle", help="X 用户名（不含 @），如 ArtofSpecuycky")
    parser.add_argument("--since", default="",
                        help="起始日期 YYYY-MM-DD（默认：今天往前 3 个月）")
    parser.add_argument("--until", default="", help="结束日期 YYYY-MM-DD（默认：现在）")
    parser.add_argument("--max-tweets", type=int, default=800,
                        help="抓取条数上限，防止超额扣费（默认 800）")
    parser.add_argument("--include-replies", action="store_true",
                        help="是否包含回复（默认只抓原创，不含转发/回复）")
    args = parser.parse_args()

    _load_env()

    handle = args.handle.lstrip("@")
    since = args.since or (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    until = args.until

    est_cost = args.max_tweets * 0.005
    print(f"📡 抓取 @{handle} 的推文：{since} ~ {until or '现在'}"
          f"（上限 {args.max_tweets} 条，最坏情况约 ${est_cost:.2f}）...", flush=True)

    tweets, backend = fetch_tweets_archive(
        handle, since, until, args.max_tweets, args.include_replies,
    )

    if backend.startswith("FAILED"):
        print(f"\n❌ 抓取失败：{backend}")
        print("   多半是 X_BEARER_TOKEN 未配置或无 search/all（全档案）权限。")
        print("   在 kol_radar/.env 里填好 X_BEARER_TOKEN 后重试。")
        sys.exit(1)

    data = {
        "handle": handle,
        "profile_url": f"https://x.com/{handle}",
        "since": since,
        "until": until or "now",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "backend": backend,
        "tweet_count": len(tweets),
        "tweets": [t.to_dict() for t in tweets],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"single_{handle}_{since}_to_{until or 'now'}.json"
    out_path = OUTPUT_DIR / fname
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 完成：{len(tweets)} 条原创推文")
    print(f"   JSON：{out_path}")
    if not tweets:
        print("   （0 条：确认 handle 是否正确、该时间段是否真有原创推文、或 token 权限是否足够）")


if __name__ == "__main__":
    main()
