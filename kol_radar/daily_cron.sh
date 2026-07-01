#!/usr/bin/env bash
# 每日定时刷新：按「昨天 8:00 ~ 今天 8:00（中国时区，UTC+8）」精确时间窗口抓推文
# + newsletter 全文（免费），直接写到 nginx 服务目录，网站 index.html 自动更新。
#
# 用精确时间窗口而不是「最近 N 条」，好处：
#   - 不会因为某天发太多而漏抓，也不会因为发太少而重复展示前一天的内容
#   - 时区用 Python 显式按 UTC+8 计算（中国无夏令时，固定偏移），不依赖服务器系统时区设置，
#     不管服务器是 UTC 还是别的时区，算出来的窗口都是准确的「中国时间昨天8点到今天8点」
#
# 用法：
#   ./daily_cron.sh                                   # 用默认参数
#   ./daily_cron.sh /var/www/kol-radar 50              # 自定义 输出目录 单人条数安全上限
#
# 成本提示：按「实际落在这 24 小时窗口内的推文数」计费（不是固定按上限收费），
# MAX_TWEETS 只是防失控的安全上限，正常情况下每人一天几条，成本远低于按 --limit 拉「最近N条」的旧方案。

set -uo pipefail
cd "$(dirname "$0")"

OUTPUT="${1:-/var/www/kol-radar}"
MAX_TWEETS="${2:-50}"

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d_%H%M).log"

# 计算「中国时区 昨天8点 ~ 今天8点」，转成 UTC 传给 radar.py（--since/--until 按 UTC 解析）
WINDOW=$(python3 -c "
from datetime import datetime, timedelta, timezone
CST = timezone(timedelta(hours=8))
now = datetime.now(CST)
today_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
if now < today_8am:
    today_8am -= timedelta(days=1)
yesterday_8am = today_8am - timedelta(days=1)
since_utc = yesterday_8am.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
until_utc = today_8am.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
print(f'{since_utc} {until_utc}')
")
SINCE=$(echo "$WINDOW" | awk '{print $1}')
UNTIL=$(echo "$WINDOW" | awk '{print $2}')

{
  echo "═══ $(date '+%Y-%m-%d %H:%M:%S') 开始每日刷新（窗口 ${SINCE} ~ ${UNTIL} UTC，即中国时区昨天8点~今天8点） ═══"
  python3 radar.py --output "$OUTPUT" --since "$SINCE" --until "$UNTIL" --daily \
    --max-tweets "$MAX_TWEETS" --source both
  echo "═══ $(date '+%Y-%m-%d %H:%M:%S') 完成 ═══"
} >> "$LOG_FILE" 2>&1

# 只保留最近 30 天日志，避免堆积
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete 2>/dev/null

exit 0
