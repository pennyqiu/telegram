#!/usr/bin/env bash
# 场内纳指/标普 QDII · 每日刷新 +（可选）邮件提醒
#
# 做什么：
#   1. 拉取东财最新溢价与管理费/托管费 → 写入 friends/qdii-premium.json（供监控页读取）
#   2. 刷新长期走势对比 → friends/qdii-history.json（供 qdii-vs-us.html 读取；失败不影响主流程）
#   3. 每周一重跑量化回测 → friends/qdii-quant.json（供 qdii-quant.html 读取；失败不影响主流程）
#   4. 若配置了 qdii_email.env 且 EMAIL_ENABLED=true → 发邮件
#
# 安装到服务器 crontab：
#   ⚠ 服务器系统时区是 UTC。crontab 数字按 UTC 解释；
#     命令前的 TZ=Asia/Shanghai 只影响脚本内部时间，不改触发时刻。
#   北京 09:35 = UTC 01:35（工作日，错开 us-dip 的 01:30 UTC；用上一交易日收盘溢价）
#   chmod +x /app/telegram/friends/tools/daily_qdii_cron.sh
#   (crontab -l 2>/dev/null | grep -v 'daily_qdii_cron.sh'; \
#     echo "35 1 * * 1-5 TZ=Asia/Shanghai /app/telegram/friends/tools/daily_qdii_cron.sh >> /var/log/qdii-premium.log 2>&1") | crontab -
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
# 空数组在 bash 3.2 + set -u 下会报 unbound variable（DAILY_QDII_EMAIL=0 且无参数时）
python3 "$ROOT/friends/tools/fetch_qdii_premium.py" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
rc=$?

# 长期走势是慢变量（且依赖 Yahoo，偶发限流），失败只记日志，不影响溢价监控与邮件
if [[ "${DAILY_QDII_HISTORY:-1}" != "0" ]]; then
  if python3 "$ROOT/friends/tools/fetch_qdii_history.py" >/tmp/qdii_history.out 2>&1; then
    tail -n 3 /tmp/qdii_history.out
  else
    echo "[warn] fetch_qdii_history.py 失败（不影响溢价监控）："
    tail -n 5 /tmp/qdii_history.out
  fi
fi

# 量化回测结论几乎不随一天的行情变化，每周一重跑一次即可（DAILY_QDII_QUANT=1 可强制）
if [[ "${DAILY_QDII_QUANT:-auto}" != "0" ]]; then
  if [[ "${DAILY_QDII_QUANT:-auto}" == "1" || "$(date +%u)" == "1" ]]; then
    {
      python3 "$ROOT/friends/tools/fetch_qdii_quant_data.py" --stale-days 4 &&
      python3 "$ROOT/friends/tools/qdii_quant.py" --json "$ROOT/friends/qdii-quant.json"
    } >/tmp/qdii_quant.out 2>&1
    if [[ $? -eq 0 ]]; then
      tail -n 2 /tmp/qdii_quant.out
    else
      echo "[warn] qdii_quant 刷新失败（页面会回退 qdii-quant.sample.json）："
      tail -n 6 /tmp/qdii_quant.out
    fi
  fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_qdii_cron done rc=$rc"
exit $rc
