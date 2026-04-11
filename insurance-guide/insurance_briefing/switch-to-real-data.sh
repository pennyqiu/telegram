#!/bin/bash
# 切换到真实数据源的部署脚本
# 在服务器上运行此脚本即可启用真实数据抓取

echo "🔄 正在切换到真实数据源..."
echo ""

# 步骤 1: 更新 generate-briefing 命令（智能版本）
echo "[1/3] 更新 generate-briefing 命令..."
cat > /usr/local/bin/generate-briefing << 'EOF'
#!/bin/bash
# 保险简报生成脚本（智能版本）
# 会尝试爬取真实数据，如果失败则回退到演示数据

BRIEFING_DIR="/app/telegram/insurance-guide/insurance_briefing"
OUTPUT_DIR="/var/www/insurance-briefing"
LOG_FILE="/var/log/insurance-briefing.log"

cd "$BRIEFING_DIR"

echo "🔄 正在生成保险资讯周报..."
echo "$(date '+%Y-%m-%d %H:%M:%S') - 开始生成简报" >> "$LOG_FILE"

# 尝试使用真实数据源
python3 briefing_generator.py --output "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ] && [ -f "$OUTPUT_DIR/weekly.html" ]; then
    echo "✅ 简报已生成（使用真实数据）"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 简报生成成功（真实数据）" >> "$LOG_FILE"
else
    echo "⚠️  真实数据获取失败，使用演示数据..."
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 真实数据失败，使用演示数据" >> "$LOG_FILE"
    
    python3 demo.py --output "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"
    
    if [ -f "$OUTPUT_DIR/demo_weekly.html" ]; then
        cp "$OUTPUT_DIR/demo_weekly.html" "$OUTPUT_DIR/weekly.html"
        echo "✅ 简报已生成（演示数据）"
        echo "$(date '+%Y-%m-%d %H:%M:%S') - 简报生成成功（演示数据）" >> "$LOG_FILE"
    else
        echo "❌ 简报生成失败"
        echo "$(date '+%Y-%m-%d %H:%M:%S') - 简报生成失败" >> "$LOG_FILE"
    fi
fi

echo "访问：http://$(hostname -I | awk '{print $1}')/insurance-briefing/"
EOF

chmod +x /usr/local/bin/generate-briefing
echo "  ✓ generate-briefing 命令已更新"

# 步骤 2: 更新定时任务脚本
echo "[2/3] 更新定时任务脚本..."
cat > /usr/local/bin/update-insurance-briefing.sh << 'EOF'
#!/bin/bash
# 保险资讯周报自动更新脚本

cd /app/telegram
git pull -q

cd /app/telegram/insurance-guide/insurance_briefing

# 尝试使用真实数据源
python3 briefing_generator.py --output /var/www/insurance-briefing >> /var/log/insurance-briefing.log 2>&1

if [ $? -ne 0 ] || [ ! -f /var/www/insurance-briefing/weekly.html ]; then
    # 失败则使用演示数据
    python3 demo.py --output /var/www/insurance-briefing >> /var/log/insurance-briefing.log 2>&1
    if [ -f /var/www/insurance-briefing/demo_weekly.html ]; then
        cp /var/www/insurance-briefing/demo_weekly.html /var/www/insurance-briefing/weekly.html
    fi
fi
EOF

chmod +x /usr/local/bin/update-insurance-briefing.sh
echo "  ✓ 定时任务脚本已更新"

# 步骤 3: 测试生成简报
echo "[3/3] 测试生成简报..."
echo ""
/usr/local/bin/generate-briefing

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  切换完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 当前配置："
echo "  - 数据源：真实 RSS + 手动添加（优先）"
echo "  - 回退机制：如果真实数据失败，自动使用演示数据"
echo "  - 定时任务：每周一 08:00 自动更新"
echo ""
echo "📝 管理命令："
echo "  - 生成简报：generate-briefing"
echo "  - 手动添加：add-insurance-article"
echo "  - 查看日志：tail -f /var/log/insurance-briefing.log"
echo ""
echo "🔧 数据源配置："
echo "  - 编辑配置：vim /app/telegram/insurance-guide/insurance_briefing/config.py"
echo "  - 在 ENABLED_RSS_SOURCES 中启用/禁用数据源"
echo ""
