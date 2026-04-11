#!/usr/bin/env bash
# ============================================================
#  投资监控系统 · 一键 VPS 部署脚本
#  支持 Ubuntu 20.04 / 22.04
#
#  用法：
#    bash vps-setup.sh
#
#  迁移到新 VPS：
#    1. 将整个 investment_tracker/ 目录上传到新 VPS
#    2. 在新 VPS 上运行：bash vps-setup.sh
#  ============================================================

set -e

# ── 可修改的配置 ────────────────────────────────────────────
GITHUB_REPO="https://github.com/pennyqiu/telegram.git"
APP_DIR="/opt/telegram"                       # 代码目录
BRIEFING_DIR="/var/www/briefing"              # 简报输出目录
WEBSITE_DIR="/var/www/website"                # 网站静态文件目录
API_PORT=8001                                 # price_api 监听端口
ADMIN_USER="admin"                            # 简报 Basic Auth 用户名
ADMIN_PASS="admin123"                         # 简报 Basic Auth 密码
DEMO_USER="demo"                              # 演示账号
DEMO_PASS="demo2024"                          # 演示密码

# ── 颜色输出 ────────────────────────────────────────────────
GREEN="\e[32m"; YELLOW="\e[33m"; RED="\e[31m"; RESET="\e[0m"; BOLD="\e[1m"
ok()   { echo -e "${GREEN}  ✓ $*${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${RESET}"; }
info() { echo -e "  → $*"; }

# ── 检查 root ──────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  echo -e "${RED}请用 root 账户运行此脚本${RESET}"
  exit 1
fi

echo -e "\n${BOLD}══════════════════════════════════════${RESET}"
echo -e "${BOLD}   投资监控系统 · VPS 一键部署${RESET}"
echo -e "${BOLD}══════════════════════════════════════${RESET}\n"

# ════════════════════════════════════════
# 1. 系统依赖
# ════════════════════════════════════════
echo -e "[1/7] ${BOLD}安装系统依赖...${RESET}"
apt-get update -qq
apt-get install -y -qq \
  python3 python3-pip nginx git curl \
  apache2-utils net-tools lsof > /dev/null
ok "系统依赖安装完成"

# ════════════════════════════════════════
# 2. Python 依赖
# ════════════════════════════════════════
echo -e "\n[2/7] ${BOLD}安装 Python 依赖...${RESET}"
pip3 install -q yfinance requests feedparser fastapi uvicorn
ok "Python 依赖安装完成"

# ════════════════════════════════════════
# 3. 拉取代码
# ════════════════════════════════════════
echo -e "\n[3/7] ${BOLD}同步代码仓库...${RESET}"
if [ -d "$APP_DIR/.git" ]; then
  info "已存在，执行 git pull..."
  git -C "$APP_DIR" pull --ff-only
else
  info "首次克隆..."
  git clone "$GITHUB_REPO" "$APP_DIR"
fi
ok "代码同步完成：$APP_DIR"

# ════════════════════════════════════════
# 4. 目录 & 权限
# ════════════════════════════════════════
echo -e "\n[4/7] ${BOLD}配置目录...${RESET}"
mkdir -p "$BRIEFING_DIR" "$WEBSITE_DIR"

# 将网站静态文件同步到 web 目录（软链也可以，这里复制更稳健）
cp -ru "$APP_DIR"/. "$WEBSITE_DIR"/ 2>/dev/null || true
ok "网站文件已同步到：$WEBSITE_DIR"

# ════════════════════════════════════════
# 5. 生成初始简报
# ════════════════════════════════════════
echo -e "\n[5/7] ${BOLD}生成初始简报...${RESET}"
for MODE in daily weekly monthly; do
  info "生成 ${MODE} 简报..."
  BRIEFING_OUTPUT="$BRIEFING_DIR" python3 "$APP_DIR/investment_tracker/tracker.py" "$MODE" \
    2>&1 | grep -E "✅|ERROR|警告" || true
done
ok "简报生成完成：$BRIEFING_DIR"

# ════════════════════════════════════════
# 6. 配置 Nginx
# ════════════════════════════════════════
echo -e "\n[6/7] ${BOLD}配置 Nginx...${RESET}"

# Basic Auth
htpasswd -cb /etc/nginx/.htpasswd "$ADMIN_USER" "$ADMIN_PASS" > /dev/null
htpasswd -b  /etc/nginx/.htpasswd "$DEMO_USER"  "$DEMO_PASS"  > /dev/null

# Nginx 站点配置
cat > /etc/nginx/sites-available/investment << NGINX_CONF
server {
    listen 80 default_server;
    server_name _;

    # ── 股票行情 API（反代到 FastAPI price_api.py）──────────────
    location /api/ {
        proxy_pass         http://127.0.0.1:${API_PORT};
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        add_header         Access-Control-Allow-Origin "*" always;
        add_header         Access-Control-Allow-Methods "GET, OPTIONS" always;
        add_header         Access-Control-Allow-Headers "*" always;
        if (\$request_method = OPTIONS) { return 204; }
    }

    # ── 每日/每周/月度简报（需要 Basic Auth）────────────────────
    location /briefing/ {
        alias   $BRIEFING_DIR/;
        index   daily.html index.html;
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime  on;
        auth_basic           "投资简报";
        auth_basic_user_file /etc/nginx/.htpasswd;
        try_files \$uri \$uri/ =404;
    }

    # ── 网站静态文件（investment-tracker.html 等）───────────────
    location / {
        root  $WEBSITE_DIR;
        index index.html;
        try_files \$uri \$uri/ =404;
    }
}
NGINX_CONF

# 启用站点
ln -sf /etc/nginx/sites-available/investment /etc/nginx/sites-enabled/investment
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
ok "Nginx 配置完成"

# ════════════════════════════════════════
# 7. 配置 price-api systemd 服务
# ════════════════════════════════════════
echo -e "\n[7/7] ${BOLD}配置 price-api 服务...${RESET}"

# 先杀掉占用端口的旧进程
fuser -k ${API_PORT}/tcp 2>/dev/null || true
sleep 1

cat > /etc/systemd/system/price-api.service << SERVICE
[Unit]
Description=Investment Tracker Price API
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}/investment_tracker
Environment=PYTHONPATH=${APP_DIR}/investment_tracker
ExecStart=/usr/local/bin/uvicorn price_api:app --host 127.0.0.1 --port ${API_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable price-api
systemctl restart price-api
sleep 3

if systemctl is-active --quiet price-api; then
  ok "price-api 服务已启动（端口 ${API_PORT}）"
else
  warn "price-api 启动失败，请检查：journalctl -u price-api -n 30"
fi

# ════════════════════════════════════════
# 8. 配置 Cron 定时任务
# ════════════════════════════════════════
echo -e "\n[+] ${BOLD}配置 Cron 定时任务...${RESET}"

# 配置 cron 更新网站文件的辅助脚本
cat > /usr/local/bin/update-website.sh << 'SYNC'
#!/bin/bash
APP_DIR="/opt/telegram"
WEBSITE_DIR="/var/www/website"
git -C "$APP_DIR" pull --ff-only 2>&1
rsync -a --delete "$APP_DIR"/ "$WEBSITE_DIR"/ \
  --exclude='.git' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='.env'
SYNC
chmod +x /usr/local/bin/update-website.sh

cat > /etc/cron.d/investment-tracker << CRON
# 投资监控自动化任务
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
BRIEFING_OUTPUT=${BRIEFING_DIR}

# 每日简报（工作日 08:00 UTC = 北京时间 16:00）
0 8 * * 1-5  root BRIEFING_OUTPUT=${BRIEFING_DIR} python3 ${APP_DIR}/investment_tracker/tracker.py daily  >> /var/log/tracker.log 2>&1

# 每周简报（周一 08:30 UTC）
30 8 * * 1   root BRIEFING_OUTPUT=${BRIEFING_DIR} python3 ${APP_DIR}/investment_tracker/tracker.py weekly >> /var/log/tracker.log 2>&1

# 月度简报（每月1日 09:00 UTC）
0 9 1 * *    root BRIEFING_OUTPUT=${BRIEFING_DIR} python3 ${APP_DIR}/investment_tracker/tracker.py monthly >> /var/log/tracker.log 2>&1

# 每日同步代码 + 网站文件（02:00 UTC）
0 2 * * *    root /usr/local/bin/update-website.sh >> /var/log/tracker.log 2>&1
CRON
chmod 644 /etc/cron.d/investment-tracker
ok "Cron 定时任务配置完成"

# ════════════════════════════════════════
# 验证部署
# ════════════════════════════════════════
echo ""
VPS_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
API_HEALTH=$(curl -s http://127.0.0.1:${API_PORT}/api/health 2>/dev/null || echo '{"status":"unreachable"}')

echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo -e "${BOLD}  ✅  部署完成！${RESET}"
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo ""
echo -e "  投资监控仪表盘：  ${GREEN}http://${VPS_IP}/investment-tracker.html${RESET}"
echo -e "  每日简报：        ${GREEN}http://${VPS_IP}/briefing/daily.html${RESET}"
echo -e "  每周简报：        ${GREEN}http://${VPS_IP}/briefing/weekly.html${RESET}"
echo -e "  月度简报：        ${GREEN}http://${VPS_IP}/briefing/monthly.html${RESET}"
echo -e "  历史快照目录：    ${GREEN}http://${VPS_IP}/briefing/${RESET}"
echo -e "  API 健康检查：    ${GREEN}http://${VPS_IP}/api/health${RESET}"
echo ""
echo -e "  简报账号：  ${YELLOW}${ADMIN_USER} / ${ADMIN_PASS}${RESET}"
echo -e "  演示账号：  ${YELLOW}${DEMO_USER} / ${DEMO_PASS}${RESET}"
echo ""
echo -e "  API 状态：  ${API_HEALTH}"
echo ""
echo -e "  日志：     tail -f /var/log/tracker.log"
echo -e "  服务：     systemctl status price-api"
echo -e "  更新代码： /usr/local/bin/update-website.sh"
echo ""
echo -e "${BOLD}  ⚡ 迁移到新 VPS 只需：${RESET}"
echo -e "     git clone ${GITHUB_REPO} && bash telegram/investment_tracker/vps-setup.sh"
echo ""
