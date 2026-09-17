#!/usr/bin/env bash
# 组合纪律检查 · 每日把规则里的时限和今天的日期比对一次
#
# 做什么：
#   1. 读 决策日志.md 与 投资规则卡.md，算逾期决策、21 DTE 闸门、台账过期、复盘节奏
#   2. 若配了 friends/tools/qdii_email.env 且 EMAIL_ENABLED=true → 发邮件
#
# 不取行情，因此没有数据源可以静默失效。解析不到表格会以非零码退出。
#
# 收件人：美股持仓复盘/tools/discipline_recipients.txt（不与朋友那份名单共用，
# 因为本报告含持仓、期权义务与现金缺口）。
#
# 安装到服务器 crontab：
#   ⚠ 服务器系统时区是 UTC。crontab 数字按 UTC 解释；
#     命令前的 TZ=Asia/Shanghai 只影响脚本内部时间，不改触发时刻。
#   北京 08:00 = UTC 00:00（每天，含周末——期权闸门与复盘节奏不看交易日）
#   chmod +x /app/telegram/美股持仓复盘/tools/daily_discipline_cron.sh
#   (crontab -l 2>/dev/null | grep -v 'daily_discipline_cron.sh'; \
#     echo "0 0 * * * TZ=Asia/Shanghai /app/telegram/美股持仓复盘/tools/daily_discipline_cron.sh >> /var/log/discipline.log 2>&1") | crontab -
#   crontab -l
#
# 手动试跑：
#   ./daily_discipline_cron.sh                      # 只打印，不发信
#   DISCIPLINE_EMAIL=1 ./daily_discipline_cron.sh   # 发信
#   ./daily_discipline_cron.sh --today 2026-09-20   # 指定日期看看会报什么

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

EXTRA_ARGS=()
for a in "$@"; do EXTRA_ARGS+=("$a"); done

# cron 里默认发信；本地手动跑默认不发，免得测试时打扰自己。
if [[ "${DISCIPLINE_EMAIL:-0}" != "0" ]]; then
  EXTRA_ARGS+=(--email)
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_discipline_cron start"
python3 "$HERE/check_discipline.py" "${EXTRA_ARGS[@]}"
rc=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_discipline_cron done rc=$rc"
exit $rc
