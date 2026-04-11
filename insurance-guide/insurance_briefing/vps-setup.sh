#!/bin/bash
#=============================================================================
# 保险资讯周报系统 - VPS 一键部署脚本
# 参考 investment_tracker/vps-setup.sh
#=============================================================================

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
REPO_URL="https://github.com/pennyqiu/telegram.git"
REPO_DIR="/app/telegram"
WEB_ROOT="/var/www/insurance-briefing"
NGINX_SITE="insurance-briefing"
CRON_USER="root"
DOMAIN="${DOMAIN:-}"  # 可选：通过环境变量设置域名

# 打印分隔线
print_header() {
    echo ""
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${BLUE}   保险资讯周报 · VPS 一键部署${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[$1] $2${NC}"
}

print_success() {
    echo -e "${GREEN}  ✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}  ✗ $1${NC}"
}

# 检查是否为 root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "请使用 root 用户运行此脚本"
        echo "  sudo bash insurance-guide/insurance_briefing/vps-setup.sh"
        exit 1
    fi
}

# 安装系统依赖
install_system_deps() {
    print_step "1/8" "安装系统依赖..."
    
    apt-get update -qq
    apt-get install -y -qq \
        python3 \
        python3-pip \
        nginx \
        git \
        apache2-utils \
        certbot \
        python3-certbot-nginx \
        > /dev/null 2>&1
    
    print_success "系统依赖安装完成"
}

# 安装 Python 依赖
install_python_deps() {
    print_step "2/8" "安装 Python 依赖..."
    
    pip3 install -q \
        requests \
        feedparser \
        beautifulsoup4 \
        lxml
    
    print_success "Python 依赖安装完成"
}

# 克隆或更新代码仓库
sync_repo() {
    print_step "3/8" "同步代码仓库..."
    
    if [ ! -d "$REPO_DIR" ]; then
        echo "  → 首次克隆代码仓库..."
        git clone --depth 1 "$REPO_URL" "$REPO_DIR"
    else
        echo "  → 已存在，执行 git pull..."
        cd "$REPO_DIR"
        git pull
    fi
    
    print_success "代码同步完成：$REPO_DIR"
}

# 配置目录
setup_directories() {
    print_step "4/8" "配置目录..."
    
    # 创建输出目录
    mkdir -p "$WEB_ROOT"
    chmod 755 "$WEB_ROOT"
    
    print_success "输出目录已创建：$WEB_ROOT"
}

# 生成初始简报（使用演示数据）
generate_initial_briefing() {
    print_step "5/8" "生成初始简报..."
    
    cd "$REPO_DIR/insurance-guide/insurance_briefing"
    
    # 首次运行使用演示数据
    python3 demo.py --output "$WEB_ROOT" 2>&1 | grep -E "(✅|✓)" || true
    
    # 将 demo 文件复制为 weekly.html
    if [ -f "$WEB_ROOT/demo_weekly.html" ]; then
        cp "$WEB_ROOT/demo_weekly.html" "$WEB_ROOT/weekly.html"
        print_success "初始简报已生成"
    else
        print_warning "简报生成失败，将在定时任务中重试"
    fi
}

# 配置 Nginx
setup_nginx() {
    print_step "6/8" "配置 Nginx..."
    
    # 生成 Nginx 配置文件
    cat > /etc/nginx/sites-available/$NGINX_SITE << 'EOF'
server {
    listen 80;
    server_name _;
    
    # 保险简报
    location /insurance-briefing/ {
        alias /var/www/insurance-briefing/;
        index weekly.html index.html;
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime on;
        
        # 基本认证
        auth_basic "保险资讯周报";
        auth_basic_user_file /etc/nginx/.htpasswd_insurance;
        
        try_files $uri $uri/ =404;
    }
}
EOF
    
    # 创建认证用户
    if [ ! -f /etc/nginx/.htpasswd_insurance ]; then
        echo "  → 创建访问账号..."
        htpasswd -bc /etc/nginx/.htpasswd_insurance admin admin123
        htpasswd -b /etc/nginx/.htpasswd_insurance demo demo2024
    fi
    
    # 启用站点
    ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/$NGINX_SITE
    
    # 测试配置
    nginx -t
    systemctl reload nginx
    
    print_success "Nginx 配置完成"
    
    # 如果提供了域名，申请 SSL 证书
    if [ -n "$DOMAIN" ]; then
        echo ""
        echo "  → 检测到域名配置：$DOMAIN，尝试申请 SSL 证书..."
        
        # 更新 Nginx 配置中的域名
        sed -i "s/server_name _;/server_name $DOMAIN;/" /etc/nginx/sites-available/$NGINX_SITE
        nginx -t && systemctl reload nginx
        
        # 申请证书
        certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@$DOMAIN || \
            print_warning "SSL 证书申请失败，请手动运行: certbot --nginx -d $DOMAIN"
        
        if [ $? -eq 0 ]; then
            print_success "SSL 证书申请成功，HTTPS 已启用：https://$DOMAIN"
        fi
    fi
}

# 配置定时任务
setup_cron() {
    print_step "7/8" "配置 Cron 定时任务..."
    
    # 创建更新脚本（使用演示数据）
    cat > /usr/local/bin/update-insurance-briefing.sh << 'EOF'
#!/bin/bash
# 保险资讯周报自动更新脚本

cd /app/telegram
git pull -q

cd /app/telegram/insurance-guide/insurance_briefing

# 使用演示数据生成
python3 demo.py --output /var/www/insurance-briefing >> /var/log/insurance-briefing.log 2>&1

# 复制为 weekly.html
if [ -f /var/www/insurance-briefing/demo_weekly.html ]; then
    cp /var/www/insurance-briefing/demo_weekly.html /var/www/insurance-briefing/weekly.html
fi
EOF
    
    chmod +x /usr/local/bin/update-insurance-briefing.sh
    
    # 添加 cron 任务（每周一早上 8:00）
    CRON_CMD="0 8 * * 1 /usr/local/bin/update-insurance-briefing.sh"
    
    # 检查是否已存在
    if ! crontab -l 2>/dev/null | grep -q "update-insurance-briefing.sh"; then
        (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
        print_success "Cron 定时任务配置完成（每周一 08:00）"
    else
        print_warning "Cron 任务已存在，跳过"
    fi
}

# 创建手动更新脚本
create_manual_scripts() {
    print_step "8/8" "创建管理脚本..."
    
    # 手动生成简报脚本（使用演示数据）
    cat > /usr/local/bin/generate-briefing << 'EOF'
#!/bin/bash
# 手动生成保险简报（使用演示数据）

echo "🔄 正在生成保险资讯周报（演示数据）..."
cd /app/telegram/insurance-guide/insurance_briefing

# 使用 demo.py 生成演示简报
python3 demo.py --output /var/www/insurance-briefing

# 复制 demo_weekly.html 为 weekly.html
if [ -f /var/www/insurance-briefing/demo_weekly.html ]; then
    cp /var/www/insurance-briefing/demo_weekly.html /var/www/insurance-briefing/weekly.html
    echo "✅ 简报已生成！"
else
    echo "⚠️  简报生成失败"
fi

echo "访问：http://$(hostname -I | awk '{print $1}')/insurance-briefing/"
EOF
    
    # 手动添加内容脚本
    cat > /usr/local/bin/add-insurance-article << 'EOF'
#!/bin/bash
# 手动添加保险文章到周报

cd /app/telegram/insurance-guide/insurance_briefing
python3 manual_curator.py
EOF
    
    chmod +x /usr/local/bin/generate-briefing
    chmod +x /usr/local/bin/add-insurance-article
    
    print_success "管理脚本创建完成"
}

# 显示部署结果
show_summary() {
    echo ""
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo -e "${GREEN}  ✅  部署完成！${NC}"
    echo -e "${BLUE}══════════════════════════════════════${NC}"
    echo ""
    
    # 获取服务器 IP
    SERVER_IP=$(hostname -I | awk '{print $1}')
    
    echo -e "${YELLOW}  📊 访问地址：${NC}"
    echo "  HTTP 访问：    http://$SERVER_IP/insurance-briefing/"
    echo "  最新周报：    http://$SERVER_IP/insurance-briefing/weekly.html"
    echo "  历史归档：    http://$SERVER_IP/insurance-briefing/index.html"
    echo ""
    
    if [ -n "$DOMAIN" ]; then
        echo "  域名访问：    https://$DOMAIN/insurance-briefing/"
        echo ""
    fi
    
    echo -e "${YELLOW}  🔐 访问账号：${NC}"
    echo "  管理员：     admin / admin123"
    echo "  演示账号：   demo / demo2024"
    echo ""
    
    echo -e "${YELLOW}  📝 管理命令：${NC}"
    echo "  手动生成：   generate-briefing"
    echo "  添加内容：   add-insurance-article"
    echo "  查看日志：   tail -f /var/log/insurance-briefing.log"
    echo "  更新代码：   /usr/local/bin/update-insurance-briefing.sh"
    echo ""
    
    echo -e "${YELLOW}  ⏰ 自动更新：${NC}"
    echo "  定时任务：   每周一 08:00 自动生成最新周报"
    echo "  查看任务：   crontab -l | grep insurance"
    echo ""
    
    echo -e "${YELLOW}  🔧 配置文件：${NC}"
    echo "  数据源配置： $REPO_DIR/insurance-guide/insurance_briefing/config.py"
    echo "  Nginx 配置： /etc/nginx/sites-available/$NGINX_SITE"
    echo "  输出目录：   $WEB_ROOT"
    echo ""
    
    echo -e "${BLUE}  ⚡ 迁移到新 VPS 只需：${NC}"
    echo "     git clone $REPO_URL && bash telegram/insurance-guide/insurance_briefing/vps-setup.sh"
    echo ""
}

# 主函数
main() {
    print_header
    
    check_root
    install_system_deps
    install_python_deps
    sync_repo
    setup_directories
    generate_initial_briefing
    setup_nginx
    setup_cron
    create_manual_scripts
    show_summary
}

# 执行主函数
main "$@"
