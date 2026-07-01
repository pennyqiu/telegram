#!/usr/bin/env bash
# 一次性对多位 KOL 做历史回溯（全档案搜索 /2/tweets/search/all，按量计费）。
# 逐个 KOL 单独跑，各自产出独立的 kol_feed_archive_<handle>_...json /
# kol_briefing_archive_<handle>_...html，互不覆盖，可在 archive_index.html 统一导航查看。
#
# 用法：
#   ./backfill_all.sh                                    # 用下面的默认参数
#   ./backfill_all.sh 2026-01-01 1000 /var/www/kol-radar  # 自定义 起始日期 单人上限 输出目录
#
# 成本提示：按 max_tweets_per_kol × 实际抓到条数 × $0.005 计费（不会因为设高上限就多花钱，
# 只按真实条数收费）。单个 KOL 失败不会中断整体流程，会跳到下一位并在最后汇总。

set -uo pipefail
cd "$(dirname "$0")"

SINCE="${1:-2026-01-01}"
MAX_TWEETS="${2:-1000}"
OUTPUT="${3:-/var/www/kol-radar}"

# Serenity(aleabitoreddit) 已单独跑过，这里默认只跑剩下几位；
# 如需连它一起重跑（例如换了更晚的 --since），把对应注释去掉即可。
HANDLES=(
  SemiAnalysis_
  # FoolAllTheTime  # 已确认无原创X内容（kol_targets.py 里 skip_tweets=True），历史回溯没有意义
  # aleabitoreddit
  Beth_Kindig
  jaminball
  ballmatthew
  itsone
)

echo "═══════════════════════════════════════════════════════"
echo "📡 批量回溯：${SINCE} ~ 现在 | 单人上限 ${MAX_TWEETS} 条 | 输出到 ${OUTPUT}"
echo "═══════════════════════════════════════════════════════"
echo

FAILED=()
for h in "${HANDLES[@]}"; do
  echo "──────────────────────────────"
  echo "→ @${h}"
  echo "──────────────────────────────"
  if ! python3 radar.py --handles "$h" --since "$SINCE" --max-tweets "$MAX_TWEETS" --output "$OUTPUT"; then
    echo "⚠️  @${h} 失败，跳过继续下一位"
    FAILED+=("$h")
  fi
  echo
done

echo "═══════════════════════════════════════════════════════"
if [ "${#FAILED[@]}" -eq 0 ]; then
  echo "✅ 全部完成，导航页：${OUTPUT}/archive_index.html"
else
  echo "⚠️  完成，但以下 KOL 失败，可单独重跑：${FAILED[*]}"
  echo "   导航页：${OUTPUT}/archive_index.html"
fi
echo "═══════════════════════════════════════════════════════"
