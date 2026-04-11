#!/bin/bash
# 快速启动脚本

echo "=================================="
echo "  保险资讯周报系统 - 快速启动"
echo "=================================="
echo ""

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python 3，请先安装"
    exit 1
fi

echo "✓ Python 3 已安装"

# 安装依赖
echo ""
echo "📦 正在安装依赖..."
pip3 install -q -r requirements.txt

if [ $? -ne 0 ]; then
    echo "⚠️  全局安装失败，尝试使用虚拟环境..."
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install -q -r requirements.txt
fi

echo "✓ 依赖安装完成"

# 运行演示
echo ""
echo "🎬 运行演示（使用模拟数据）..."
echo ""
python3 demo.py

# 打开浏览器查看
if [ -f "demo_output/demo_weekly.html" ]; then
    echo ""
    echo "✅ 简报已生成！正在打开浏览器..."
    
    if command -v open &> /dev/null; then
        open demo_output/demo_weekly.html
    elif command -v xdg-open &> /dev/null; then
        xdg-open demo_output/demo_weekly.html
    else
        echo "   请手动打开：$(pwd)/demo_output/demo_weekly.html"
    fi
fi

echo ""
echo "=================================="
echo "  下一步："
echo "  1. 编辑 config.py 配置数据源"
echo "  2. 运行 python3 briefing_generator.py"
echo "  3. 查看 output/weekly.html"
echo "=================================="
