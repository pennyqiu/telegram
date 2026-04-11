# 保险资讯周报系统 - 服务器部署操作手册

## 📋 部署清单

### 环境要求
- ✅ Ubuntu 20.04+ / Debian 10+ / CentOS 8+
- ✅ Root 权限
- ✅ 公网 IP 或域名（可选）
- ✅ 最低配置：1 核 1GB 内存

---

## 🚀 方式一：一键部署（推荐）

### 步骤 1：SSH 登录服务器
```bash
ssh root@your-vps-ip
```

### 步骤 2：拉取代码
```bash
cd /app
git clone https://github.com/pennyqiu/telegram.git

# 或如果已存在，更新代码
cd /app/telegram
git pull
```

### 步骤 3：执行一键部署脚本
```bash
cd /app/telegram
bash insurance-guide/insurance_briefing/vps-setup.sh
```

### 步骤 4：等待部署完成
脚本会自动完成以下步骤：
1. ✅ 安装系统依赖（Python3、Nginx、Git 等）
2. ✅ 安装 Python 依赖（requests、beautifulsoup4 等）
3. ✅ 同步代码仓库
4. ✅ 配置输出目录
5. ✅ 生成初始简报（演示数据）
6. ✅ 配置 Nginx（带认证保护）
7. ✅ 配置定时任务（每周一早上 8:00）
8. ✅ 创建管理脚本

### 步骤 5：验证部署
```bash
# 查看输出的访问地址
# 例如：http://your-vps-ip/insurance-briefing/

# 测试访问
curl -u admin:admin123 http://localhost/insurance-briefing/weekly.html
```

---

## 🛠️ 方式二：手动部署（自定义）

### 1. 安装系统依赖
```bash
apt-get update
apt-get install -y python3 python3-pip nginx git apache2-utils certbot python3-certbot-nginx
```

### 2. 安装 Python 依赖
```bash
pip3 install requests feedparser beautifulsoup4 lxml
```

### 3. 克隆代码
```bash
mkdir -p /app
cd /app
git clone https://github.com/pennyqiu/telegram.git
```

### 4. 生成初始简报
```bash
cd /app/telegram/insurance-guide/insurance_briefing

# 使用演示数据生成
mkdir -p /var/www/insurance-briefing
python3 demo.py --output /var/www/insurance-briefing
cp /var/www/insurance-briefing/demo_weekly.html /var/www/insurance-briefing/weekly.html
```

### 5. 配置 Nginx
```bash
# 创建配置文件
cat > /etc/nginx/sites-available/insurance-briefing << 'EOF'
server {
    listen 80;
    server_name _;
    
    location /insurance-briefing/ {
        alias /var/www/insurance-briefing/;
        index weekly.html index.html;
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime on;
        
        auth_basic "保险资讯周报";
        auth_basic_user_file /etc/nginx/.htpasswd_insurance;
        
        try_files $uri $uri/ =404;
    }
}
EOF

# 创建认证用户
htpasswd -bc /etc/nginx/.htpasswd_insurance admin admin123
htpasswd -b /etc/nginx/.htpasswd_insurance demo demo2024

# 启用站点
ln -s /etc/nginx/sites-available/insurance-briefing /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 6. 配置定时任务
```bash
# 创建更新脚本
cat > /usr/local/bin/update-insurance-briefing.sh << 'EOF'
#!/bin/bash
cd /app/telegram
git pull -q
cd /app/telegram/insurance-guide/insurance_briefing
python3 briefing_generator.py --output /var/www/insurance-briefing >> /var/log/insurance-briefing.log 2>&1
EOF

chmod +x /usr/local/bin/update-insurance-briefing.sh

# 添加 cron 任务（每周一 08:00）
(crontab -l 2>/dev/null; echo "0 8 * * 1 /usr/local/bin/update-insurance-briefing.sh") | crontab -
```

### 7. 创建快捷命令
```bash
# 手动生成简报
cat > /usr/local/bin/generate-briefing << 'EOF'
#!/bin/bash
cd /app/telegram/insurance-guide/insurance_briefing
python3 briefing_generator.py --output /var/www/insurance-briefing
echo "✅ 完成！"
EOF

chmod +x /usr/local/bin/generate-briefing
```

---

## 🔐 配置 HTTPS（可选）

### 如果有域名
```bash
# 方式 1：部署时指定域名
DOMAIN=insurance.yourdomain.com bash insurance-guide/insurance_briefing/vps-setup.sh

# 方式 2：手动配置
# 1. 更新 Nginx 配置中的 server_name
sed -i 's/server_name _;/server_name insurance.yourdomain.com;/' /etc/nginx/sites-available/insurance-briefing
nginx -t && systemctl reload nginx

# 2. 申请 SSL 证书
certbot --nginx -d insurance.yourdomain.com
```

---

## 📊 验证部署

### 1. 检查服务状态
```bash
# 检查 Nginx
systemctl status nginx

# 检查定时任务
crontab -l | grep insurance

# 查看输出文件
ls -lh /var/www/insurance-briefing/
```

### 2. 测试访问
```bash
# 获取服务器 IP
SERVER_IP=$(hostname -I | awk '{print $1}')

# 测试 HTTP 访问
curl -u admin:admin123 http://$SERVER_IP/insurance-briefing/weekly.html | head -20

# 或在浏览器中访问
echo "访问：http://$SERVER_IP/insurance-briefing/"
```

### 3. 查看日志
```bash
# 查看 Nginx 日志
tail -f /var/log/nginx/access.log | grep insurance-briefing

# 查看简报生成日志
tail -f /var/log/insurance-briefing.log
```

---

## 🎯 日常管理命令

### 手动生成简报
```bash
generate-briefing
```

### 手动添加优质内容
```bash
add-insurance-article
```

### 更新代码并重新生成
```bash
/usr/local/bin/update-insurance-briefing.sh
```

### 查看定时任务日志
```bash
tail -f /var/log/insurance-briefing.log
```

### 修改数据源配置
```bash
vim /app/telegram/insurance-guide/insurance_briefing/config.py
```

### 重新加载 Nginx
```bash
nginx -t && systemctl reload nginx
```

---

## 🔧 常见问题排查

### 1. 无法访问简报页面
```bash
# 检查 Nginx 状态
systemctl status nginx

# 查看 Nginx 错误日志
tail -f /var/log/nginx/error.log

# 检查文件权限
ls -la /var/www/insurance-briefing/
chmod 755 /var/www/insurance-briefing/
chmod 644 /var/www/insurance-briefing/*.html
```

### 2. 定时任务未执行
```bash
# 查看 cron 日志
grep CRON /var/log/syslog | tail -20

# 手动执行测试
/usr/local/bin/update-insurance-briefing.sh

# 查看生成日志
cat /var/log/insurance-briefing.log
```

### 3. Python 依赖安装失败
```bash
# 使用虚拟环境
cd /app/telegram/insurance-guide/insurance_briefing
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 修改更新脚本使用虚拟环境
vim /usr/local/bin/update-insurance-briefing.sh
# 添加：source /app/telegram/insurance-guide/insurance_briefing/venv/bin/activate
```

### 4. 爬虫无法获取数据
```bash
# 检查网络连接
curl -I https://www.ia.org.hk

# 查看详细错误
cd /app/telegram/insurance-guide/insurance_briefing
python3 briefing_generator.py --days 7 --output /tmp/test

# 使用手动添加工具
add-insurance-article
```

---

## 📂 文件路径速查

| 项目 | 路径 |
|------|------|
| 代码仓库 | `/app/telegram` |
| 简报系统 | `/app/telegram/insurance-guide/insurance_briefing` |
| 输出目录 | `/var/www/insurance-briefing` |
| Nginx 配置 | `/etc/nginx/sites-available/insurance-briefing` |
| 认证文件 | `/etc/nginx/.htpasswd_insurance` |
| 更新脚本 | `/usr/local/bin/update-insurance-briefing.sh` |
| 管理脚本 | `/usr/local/bin/generate-briefing` |
| 日志文件 | `/var/log/insurance-briefing.log` |
| 数据源配置 | `/app/telegram/insurance-guide/insurance_briefing/config.py` |

---

## 🔄 更新系统

### 更新代码
```bash
cd /app/telegram
git pull
```

### 更新配置后重新生成
```bash
vim /app/telegram/insurance-guide/insurance_briefing/config.py
generate-briefing
```

### 更新 Python 依赖
```bash
cd /app/telegram/insurance-guide/insurance_briefing
pip3 install -U -r requirements.txt
```

---

## 🌐 多服务器部署

### 在新 VPS 上快速部署
```bash
ssh root@new-vps-ip

# 一行命令完成部署
git clone https://github.com/pennyqiu/telegram.git && bash telegram/insurance-guide/insurance_briefing/vps-setup.sh
```

### 同步配置到新服务器
```bash
# 从旧服务器导出配置
scp /app/telegram/insurance-guide/insurance_briefing/config.py root@new-vps:/tmp/

# 在新服务器上应用
ssh root@new-vps
cp /tmp/config.py /app/telegram/insurance-guide/insurance_briefing/
generate-briefing
```

---

## 📱 访问信息

### 默认访问地址
- **URL**: `http://your-vps-ip/insurance-briefing/`
- **最新周报**: `http://your-vps-ip/insurance-briefing/weekly.html`
- **历史归档**: `http://your-vps-ip/insurance-briefing/index.html`

### 默认账号
- **管理员**: `admin` / `admin123`
- **演示账号**: `demo` / `demo2024`

### 修改密码
```bash
# 删除旧密码文件
rm /etc/nginx/.htpasswd_insurance

# 创建新密码
htpasswd -c /etc/nginx/.htpasswd_insurance admin
htpasswd /etc/nginx/.htpasswd_insurance demo

# 重新加载 Nginx
systemctl reload nginx
```

---

## 📞 技术支持

遇到问题？
1. 查看本文档的「常见问题排查」章节
2. 查看日志：`/var/log/insurance-briefing.log`
3. 查看项目文档：`/app/telegram/insurance-guide/insurance_briefing/README.md`
4. 查看架构说明：`/app/telegram/insurance-guide/insurance_briefing/ARCHITECTURE.md`

---

**部署完成后，记得保存此文档以便后续管理！**
