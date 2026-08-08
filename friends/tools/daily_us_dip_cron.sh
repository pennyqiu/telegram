#!/usr/bin/env bash
# 美股纳指/标普 ETF · 回撤阶梯买入 · 每日刷新 +（可选）邮件提醒
#
# 做什么：
#   1. 取各 ETF 现价与历史最高，算回撤 → 写入 friends/us-dip-signal.json
#   2. 若配置了 qdii_email.env 且 EMAIL_ENABLED=true → 发邮件（复用同一套 SMTP/收件人）
#
# 安装到服务器 crontab：
#   ⚠ 服务器系统时区是 UTC。crontab 数字按 UTC 解释；
#     命令前的 TZ=Asia/Shanghai 只影响脚本内部时间，不改触发时刻。
#   北京 09:30 = UTC 01:30（周二~周六；用前一晚美股收盘数据）
#   chmod +x /app/telegram/friends/tools/daily_us_dip_cron.sh
#   (crontab -l 2>/dev/null | grep -v 'daily_us_dip_cron.sh'; \
#     echo "30 1 * * 2-6 TZ=Asia/Shanghai /app/telegram/friends/tools/daily_us_dip_cron.sh >> /var/log/us-dip.log 2>&1") | crontab -
#   crontab -l
#
# 邮件：all 每次都发；us 仅买点触发时发（见 qdii_email_recipients.txt）
#
# 手动试跑：
#   ./friends/tools/daily_us_dip_cron.sh
#   ./friends/tools/daily_us_dip_cron.sh --email-force

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

EXTRA_ARGS=()
for a in "$@"; do EXTRA_ARGS+=("$a"); done

# 默认带 --email；仅刷新 JSON：DAILY_US_DIP_EMAIL=0 ./daily_us_dip_cron.sh
if [[ "${DAILY_US_DIP_EMAIL:-1}" != "0" ]]; then
  EXTRA_ARGS+=(--email)
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_us_dip_cron start ROOT=$ROOT"
python3 "$ROOT/friends/tools/fetch_us_dip.py" "${EXTRA_ARGS[@]}"
rc=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_us_dip_cron done rc=$rc"
exit $rc
