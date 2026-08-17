#!/usr/bin/env bash
# 场内纳指/标普 QDII · 每日刷新 +（可选）邮件提醒
#
# 做什么：
#   1. 拉取东财最新溢价与管理费/托管费 → 写入 friends/qdii-premium.json（供监控页读取）
#   2. 刷新长期走势对比 → friends/qdii-history.json（供 qdii-vs-us.html 读取；失败不影响主流程）
#   3. 每周一重跑量化回测 → friends/qdii-quant.json（供 qdii-quant.html 读取；失败不影响主流程）
#   4. 重算 5 只纳指 QDII 近三年逐日溢价曲线 → friends/qdii-premium-curve.{json,html}（自包含页）
#   5. 若配置了 qdii_email.env 且 EMAIL_ENABLED=true → 发邮件
#
# 安装到服务器 crontab：
#   ⚠ 服务器系统时区是 UTC。crontab 数字按 UTC 解释；
#     命令前的 TZ=Asia/Shanghai 只影响脚本内部时间，不改触发时刻。
#   工作日三条：两次盘中发邮件（IOPV 与现价都是实时的，溢价可直接用于当天下单），
#   收盘后一次只维护网页数据（日线类产物要用真收盘价，盘中抓到的是快照）。
#     北京 11:00 = UTC 03:00 → --light，溢价 + 邮件
#     北京 14:00 = UTC 06:00 → --light，溢价 + 邮件
#     北京 15:30 = UTC 07:30 → 全量但不发信（历史 + 周一量化 + 溢价曲线）
#   chmod +x /app/telegram/friends/tools/daily_qdii_cron.sh
#   (crontab -l 2>/dev/null | grep -v 'daily_qdii_cron.sh'; \
#     echo "0 3 * * 1-5 TZ=Asia/Shanghai /app/telegram/friends/tools/daily_qdii_cron.sh --light >> /var/log/qdii-premium.log 2>&1"; \
#     echo "0 6 * * 1-5 TZ=Asia/Shanghai /app/telegram/friends/tools/daily_qdii_cron.sh --light >> /var/log/qdii-premium.log 2>&1"; \
#     echo "30 7 * * 1-5 TZ=Asia/Shanghai DAILY_QDII_EMAIL=0 /app/telegram/friends/tools/daily_qdii_cron.sh >> /var/log/qdii-premium.log 2>&1") | crontab -
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
#   ./friends/tools/daily_qdii_cron.sh --light         # 只刷溢价 JSON + 邮件

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

EXTRA_ARGS=()
LIGHT=0
for a in "$@"; do
  # --light 由本脚本消费，不传给 python
  if [[ "$a" == "--light" ]]; then
    LIGHT=1
    continue
  fi
  EXTRA_ARGS+=("$a")
done

# 慢变量（长期走势、量化回测、溢价曲线）一天刷一次够了，盘中第二次运行只要溢价与邮件。
# 用 := 赋值，显式传入的 DAILY_QDII_* 仍然优先。
if [[ "$LIGHT" == "1" ]]; then
  : "${DAILY_QDII_HISTORY:=0}" "${DAILY_QDII_QUANT:=0}" "${DAILY_QDII_CURVE:=0}"
fi

# 默认带 --email；若只想刷新 JSON：DAILY_QDII_EMAIL=0 ./daily_qdii_cron.sh
if [[ "${DAILY_QDII_EMAIL:-1}" != "0" ]]; then
  EXTRA_ARGS+=(--email)
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_qdii_cron start ROOT=$ROOT light=$LIGHT"
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

# 溢价曲线页：补最近几天的行情/净值再重算（无重型计算，十几秒；失败不影响主流程）
if [[ "${DAILY_QDII_CURVE:-1}" != "0" ]]; then
  {
    python3 "$ROOT/friends/tools/topup_price_tail.py" &&
    python3 "$ROOT/friends/tools/build_qdii_premium_curve.py"
  } >/tmp/qdii_curve.out 2>&1
  if [[ $? -eq 0 ]]; then
    tail -n 3 /tmp/qdii_curve.out
  else
    echo "[warn] 溢价曲线刷新失败（页面沿用上次生成的结果）："
    tail -n 6 /tmp/qdii_curve.out
  fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] daily_qdii_cron done rc=$rc"
exit $rc
