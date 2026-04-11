#!/bin/bash
# ============================================================
# 投资自动化监控 - VPS 一键部署脚本
# 在 VPS 上以 root 运行：bash deploy-vps.sh
# ============================================================
set -e
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 投资监控自动化 · VPS 部署脚本"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. 安装依赖 ──────────────────────────────────────────────
echo "[1/6] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip nginx git curl

echo "[2/6] 安装 Python 依赖..."
pip3 install -q yfinance requests feedparser

# ── 2. 克隆 / 更新代码仓库 ───────────────────────────────────
REPO_DIR="/opt/telegram"
BRIEFING_DIR="/var/www/briefing"

if [ -d "$REPO_DIR/.git" ]; then
  echo "[3/6] 更新代码仓库..."
  git -C "$REPO_DIR" pull
else
  echo "[3/6] 克隆代码仓库..."
  git clone https://github.com/pennyqiu/telegram.git "$REPO_DIR"
fi

mkdir -p "$BRIEFING_DIR"

# ── 3. 生成初始简报 ──────────────────────────────────────────
echo "[4/6] 生成初始每日简报..."
cd "$REPO_DIR"
BRIEFING_OUTPUT="$BRIEFING_DIR" python3 investment_tracker/tracker.py daily || true

# ── 4. 配置 Nginx ────────────────────────────────────────────
echo "[5/6] 配置 Nginx..."
cat > /etc/nginx/sites-available/briefing << 'NGINX_CONF'
server {
    listen 80;
    server_name _;

    # 行情 API（反代到 Python price_api.py:8001）
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        add_header Access-Control-Allow-Origin "*";
        add_header Access-Control-Allow-Methods "GET, OPTIONS";
    }

    # 投资简报（需要 Basic Auth 保护）
    location /briefing/ {
        alias /var/www/briefing/;
        index daily.html index.html;
        try_files $uri $uri/ =404;

        # Basic Auth 保护（防止直接访问）
        auth_basic "投资简报";
        auth_basic_user_file /etc/nginx/.htpasswd;

        # 跨域允许（让 GitHub Pages 上的页面可以 iframe 嵌入）
        add_header Access-Control-Allow-Origin "*";
    }

    # 健康检查
    location /health {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}
NGINX_CONF

# 设置 Basic Auth 密码（与网站账号一致）
apt-get install -y -qq apache2-utils
htpasswd -bc /etc/nginx/.htpasswd admin admin123
htpasswd -b  /etc/nginx/.htpasswd demo  demo2024

# 启用站点
ln -sf /etc/nginx/sites-available/briefing /etc/nginx/sites-enabled/briefing
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 5. 设置 Cron 定时任务 ────────────────────────────────────
echo "[6/6] 配置 Cron 定时任务..."
cat > /etc/cron.d/investment-tracker << 'CRON_CONF'
# 每天 08:00 UTC（北京时间 16:00）生成每日简报
0 8 * * * root cd /opt/telegram && BRIEFING_OUTPUT=/var/www/briefing python3 investment_tracker/tracker.py daily >> /var/log/tracker.log 2>&1

# 每周一 08:00 UTC 生成每周简报
0 8 * * 1 root cd /opt/telegram && BRIEFING_OUTPUT=/var/www/briefing python3 investment_tracker/tracker.py weekly >> /var/log/tracker.log 2>&1

# 每月 1 日 08:00 UTC 生成月度简报
0 8 1 * * root cd /opt/telegram && BRIEFING_OUTPUT=/var/www/briefing python3 investment_tracker/tracker.py monthly >> /var/log/tracker.log 2>&1

# 每天 08:05 UTC 自动 git pull 更新代码
5 8 * * * root git -C /opt/telegram pull >> /var/log/tracker.log 2>&1
CRON_CONF

chmod 644 /etc/cron.d/investment-tracker

# ── 6. 启动股票行情 API 服务 ─────────────────────────────────────
echo "[+] 安装 FastAPI / uvicorn..."
pip3 install -q fastapi uvicorn

echo "[+] 创建 systemd 服务（price_api）..."
cat > /etc/systemd/system/price-api.service << 'SVC'
[Unit]
Description=Stock Price API for investment tracker
After=network.target

[Service]
WorkingDirectory=/opt/telegram/investment_tracker
ExecStart=/usr/local/bin/uvicorn price_api:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable price-api
systemctl restart price-api
sleep 2
systemctl is-active --quiet price-api && echo "  ✅ price-api 服务已启动" || echo "  ❌ price-api 启动失败，查看：journalctl -u price-api -n 20"

# ── 完成 ─────────────────────────────────────────────────────
VPS_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✅ 部署完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " 每日简报地址：http://${VPS_IP}/briefing/daily.html"
echo " 每周简报地址：http://${VPS_IP}/briefing/weekly.html"
echo " 月度简报地址：http://${VPS_IP}/briefing/monthly.html"
echo ""
echo " 访问账号："
echo "   用户名：admin  密码：admin123"
echo "   用户名：demo   密码：demo2024"
echo ""
echo " 日志查看：tail -f /var/log/tracker.log"
echo " 手动生成：cd /opt/telegram && BRIEFING_OUTPUT=/var/www/briefing python3 investment_tracker/tracker.py daily"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
