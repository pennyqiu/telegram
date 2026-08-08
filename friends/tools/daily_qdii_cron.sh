#!/usr/bin/env bash
# 场内纳指/标普 QDII · 每日刷新 +（可选）邮件提醒
#
# 做什么：
#   1. 拉取东财最新溢价 → 写入 friends/qdii-premium.json（供监控页读取）
#   2. 若配置了 qdii_email.env 且 EMAIL_ENABLED=true → 发邮件
#
# 安装到服务器 crontab（中国时间工作日约 09:35，错开 us-dip 的 09:30；用上一交易日收盘溢价）：
#   chmod +x /app/telegram/friends/tools/daily_qdii_cron.sh
#   (crontab -l 2>/dev/null | grep -v 'daily_qdii_cron.sh'; \
#     echo "35 9 * * 1-5 TZ=Asia/Shanghai /app/telegram/friends/tools/daily_qdii_cron.sh >> /var/log/qdii-premium.log 2>&1") | crontab -
#   crontab -l
#
# 邮件配置：
#   cp /app/telegram/friends/tools/qdii_email.env.example /app/telegram/friends/tools/qdii_email.env
#   # 编辑填写 SMTP，设 EMAIL_ENABLED=true
#   # 投递由 qdii_email_recipients.txt 标签控制：
#   #   all  = 每次都发（心跳/失败通知）
#   #   qdii = 仅「可投」机会时发
#
# 手动试跑：
#   ./friends/tools/daily_qdii_cron.sh
#   ./friends/tools/daily_qdii_cron.sh --email-force   # 强制发一封（含 us/qdii 机会收件人）

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

EXTRA_ARGS=()
for a in "$@"; do
  EXTRA_ARGS+=("$a")
done

# 默认带 --email；若只想刷新 JSON：DAILY_QDII_EMAIL=0 ./daily_qdii_cron.sh
if [[ "${DAILY_QDII_EMAIL:-1}" != "0" ]]; then
  EXTRA_ARGS+=(--email)
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_qdii_cron start ROOT=$ROOT"
python3 "$ROOT/friends/tools/fetch_qdii_premium.py" "${EXTRA_ARGS[@]}"
rc=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_qdii_cron done rc=$rc"
exit $rc
