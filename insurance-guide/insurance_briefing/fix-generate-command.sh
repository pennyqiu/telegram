#!/bin/bash
# 快速修复脚本 - 重新生成 generate-briefing 命令
# 直接在服务器上运行此脚本来修复问题

echo "🔧 正在修复 generate-briefing 脚本..."

# 重新创建 generate-briefing 脚本（使用演示数据）
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

chmod +x /usr/local/bin/generate-briefing

echo "✅ 修复完成！"
echo ""
echo "现在运行："
echo "  generate-briefing"
echo ""
