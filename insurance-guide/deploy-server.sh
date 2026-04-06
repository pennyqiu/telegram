#!/bin/bash
# ============================================================
# hkins.guide — Nginx 部署脚本
# 在服务器 SSH 终端中直接粘贴运行
# ============================================================
set -e

DOMAIN="hkins.guide"
WWW_DOMAIN="www.hkins.guide"
WEB_ROOT="/var/www/hkins-guide"
NGINX_CONF="/etc/nginx/sites-available/hkins-guide"

echo "=== [1/4] 创建 Web 目录 ==="
mkdir -p "$WEB_ROOT"
chown -R www-data:www-data "$WEB_ROOT" 2>/dev/null || true

echo "=== [2/4] 写入 Nginx 配置 ==="
cat > "$NGINX_CONF" << 'NGINXEOF'
server {
    listen 80;
    listen [::]:80;
    server_name hkins.guide www.hkins.guide;

    # 临时 HTTP 访问，后续 certbot 会自动改为 HTTPS 重定向
    root /var/www/hkins-guide;
    index index.html;

    # 静态文件缓存
    location ~* \.(css|js|html|png|jpg|ico|svg|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # 单页应用支持（所有路径回退到 index.html）
    location / {
        try_files $uri $uri/ $uri.html /index.html;
    }

    # 关闭 access log 减少 I/O
    access_log /var/log/nginx/hkins-guide.access.log;
    error_log  /var/log/nginx/hkins-guide.error.log;
}
NGINXEOF

echo "=== [3/4] 启用站点 ==="
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/hkins-guide
nginx -t && nginx -s reload
echo ">>> Nginx 配置完成，HTTP 已上线"

echo "=== [4/4] 申请 SSL 证书（需域名已解析到此 IP）==="
echo ">>> 运行以下命令申请证书："
echo "certbot --nginx -d hkins.guide -d www.hkins.guide --non-interactive --agree-tos -m your@email.com"

echo ""
echo "=============================="
echo " 部署完成！访问 http://hkins.guide"
echo "=============================="
