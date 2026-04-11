#!/bin/bash
# 保险简报生成脚本（使用真实数据源）
# 会尝试爬取真实数据，如果失败则回退到演示数据

BRIEFING_DIR="/app/telegram/insurance-guide/insurance_briefing"
OUTPUT_DIR="/var/www/insurance-briefing"
LOG_FILE="/var/log/insurance-briefing.log"

cd "$BRIEFING_DIR"

echo "🔄 正在生成保险资讯周报..."
echo "$(date '+%Y-%m-%d %H:%M:%S') - 开始生成简报" >> "$LOG_FILE"

# 尝试使用真实数据源
python3 briefing_generator.py --output "$OUTPUT_DIR" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    # 成功生成
    echo "✅ 简报已生成（使用真实数据）"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 简报生成成功（真实数据）" >> "$LOG_FILE"
else
    # 失败，使用演示数据作为后备
    echo "⚠️  真实数据获取失败，使用演示数据..."
    echo "$(date '+%Y-%m-%d %H:%M:%S') - 真实数据失败，使用演示数据" >> "$LOG_FILE"
    
    python3 demo.py --output "$OUTPUT_DIR" >> "$LOG_FILE" 2>&1
    
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
