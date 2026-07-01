#!/usr/bin/env bash
# 每日定时刷新：newsletter 全文（免费）+ 每位 KOL 最新推文（按量计费），
# 直接写到 nginx 服务目录，网站的 index.html / latest.json 自动更新。
# 配合 crontab 每天跑一次即可实现「网站持续更新」。
#
# 用法：
#   ./daily_cron.sh                                   # 用默认参数
#   ./daily_cron.sh /var/www/kol-radar 15              # 自定义 输出目录 单人推文条数
#
# 成本提示：7 位 KOL × limit 条 × $0.005/条，limit=15 时约 $0.5/天 ≈ $16/月，
# 记得去 console.x.com 的 Billing 里把月度 spending limit 调高到覆盖这个量。

set -uo pipefail
cd "$(dirname "$0")"

OUTPUT="${1:-/var/www/kol-radar}"
LIMIT="${2:-15}"

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d_%H%M).log"

{
  echo "═══ $(date '+%Y-%m-%d %H:%M:%S') 开始每日刷新（output=${OUTPUT}, limit=${LIMIT}） ═══"
  python3 radar.py --output "$OUTPUT" --limit "$LIMIT" --source both
  echo "═══ $(date '+%Y-%m-%d %H:%M:%S') 完成 ═══"
} >> "$LOG_FILE" 2>&1

# 只保留最近 30 天日志，避免堆积
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete 2>/dev/null

exit 0
