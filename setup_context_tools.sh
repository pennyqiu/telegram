#!/bin/bash
# Telegram 项目 Token-Friendly 上下文工具安装脚本
# 支持 macOS, Linux, Windows (Git Bash)

set -e  # 遇到错误退出

echo "🚀 设置 Telegram Token-Friendly 上下文工具..."

# 检测操作系统
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    OS="windows"
fi

echo "🖥️  检测到操作系统: $OS"

# 检查 Python 3
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    # 检查是否是 Python 3
    if python -c "import sys; exit(0 if sys.version_info.major >= 3 else 1)" 2>/dev/null; then
        PYTHON_CMD="python"
    fi
fi

if [[ -z "$PYTHON_CMD" ]]; then
    echo "❌ 错误: 需要 Python 3.6+才能使用上下文工具"
    echo "   请安装 Python 3: https://www.python.org/downloads/"
    exit 1
fi

echo "✅ 找到 Python: $($PYTHON_CMD --version)"

# 设置可执行权限（Linux/macOS）
if [[ "$OS" != "windows" ]]; then
    chmod +x context_switch.py
    chmod +x status_bar.py
    echo "✅ 设置脚本可执行权限"
fi

# 测试核心功能
echo "🧪 测试上下文切换功能..."
$PYTHON_CMD context_switch.py help > /dev/null
if [[ $? -eq 0 ]]; then
    echo "✅ 上下文切换工具测试通过"
else
    echo "❌ 上下文切换工具测试失败"
    exit 1
fi

# 生成适合当前环境的别名文件
ALIASES_FILE=".context_aliases_local"
TELEGRAM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat > "$ALIASES_FILE" << EOF
# Telegram 项目上下文切换别名 (自动生成)
# 项目路径: $TELEGRAM_ROOT

# 快捷切换命令
alias ctx="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py'"
alias ctx-status="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' status"
alias ctx-help="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' help"

# 各模式快捷切换
alias ctx-sub="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' subscription"
alias ctx-club="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' club" 
alias ctx-ins="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' insurance"
alias ctx-inv="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' investment"
alias ctx-all="$PYTHON_CMD '$TELEGRAM_ROOT/context_switch.py' all"

# 状态显示（可用于 prompt）
alias ctx-emoji="$PYTHON_CMD '$TELEGRAM_ROOT/status_bar.py' emoji"
alias ctx-short="$PYTHON_CMD '$TELEGRAM_ROOT/status_bar.py' short"

# 便捷函数：切换 + 显示状态
function ctx-switch() {
    if [ -z "\$1" ]; then
        echo "用法: ctx-switch <模式>"
        echo "可用模式: subscription, club, insurance, investment, all"
        return 1
    fi
    
    $PYTHON_CMD "$TELEGRAM_ROOT/context_switch.py" "\$1"
    
    if [ \$? -eq 0 ]; then
        echo ""
        echo "🎯 当前上下文: \$($PYTHON_CMD '$TELEGRAM_ROOT/status_bar.py' full)"
    fi
}

echo "🗺️  Telegram 项目上下文工具已加载"
echo "💡 使用 'ctx-help' 查看所有命令"
echo "🎯 当前模式: \$($PYTHON_CMD '$TELEGRAM_ROOT/status_bar.py' full)"
EOF

echo "✅ 生成本地别名文件: $ALIASES_FILE"

# 检查 Cursor/VSCode 配置
if [[ -d ".vscode" ]]; then
    echo "✅ 检测到 .vscode 目录，Cursor/VSCode 集成已就绪"
else
    echo "💡 提示: 如需 Cursor/VSCode 集成，请在项目中运行:"
    echo "   mkdir -p .vscode"
    echo "   然后重新运行此脚本"
fi

# 显示使用说明
echo ""
echo "🎉 安装完成！使用方法："
echo ""
echo "1️⃣  激活别名（在此目录下运行）:"
echo "   source $ALIASES_FILE"
echo ""
echo "2️⃣  快速切换上下文:"
echo "   ctx-sub     # 订阅系统"  
echo "   ctx-club    # 俱乐部系统"
echo "   ctx-ins     # 保险系统"
echo "   ctx-inv     # 投资工具"
echo "   ctx-all     # 全部模块"
echo ""
echo "3️⃣  查看状态:"
echo "   ctx-status  # 当前模式详情"
echo ""
echo "4️⃣  Cursor 集成 (如果可用):"
echo "   Cmd+Shift+P → Tasks: Run Task → 选择 Context 模式"
echo ""
echo "📖 详细文档: CONTEXT_AUTOMATION.md"

# 可选：添加到 shell 配置文件
echo ""
read -p "是否要将别名自动添加到 ~/.bashrc 或 ~/.zshrc? (y/N): " AUTO_ADD
if [[ "$AUTO_ADD" =~ ^[Yy]$ ]]; then
    SHELL_CONFIG=""
    if [[ "$SHELL" == *"zsh"* && -f "$HOME/.zshrc" ]]; then
        SHELL_CONFIG="$HOME/.zshrc"
    elif [[ -f "$HOME/.bashrc" ]]; then
        SHELL_CONFIG="$HOME/.bashrc"
    elif [[ -f "$HOME/.bash_profile" ]]; then
        SHELL_CONFIG="$HOME/.bash_profile"
    fi
    
    if [[ -n "$SHELL_CONFIG" ]]; then
        echo "" >> "$SHELL_CONFIG"
        echo "# Telegram 项目上下文工具" >> "$SHELL_CONFIG"
        echo "if [ -f \"$TELEGRAM_ROOT/$ALIASES_FILE\" ]; then" >> "$SHELL_CONFIG"
        echo "    source \"$TELEGRAM_ROOT/$ALIASES_FILE\"" >> "$SHELL_CONFIG"
        echo "fi" >> "$SHELL_CONFIG"
        echo "✅ 已添加到 $SHELL_CONFIG"
        echo "   重启终端或运行 'source $SHELL_CONFIG' 生效"
    else
        echo "❌ 无法找到 shell 配置文件"
    fi
fi

echo ""
echo "🎯 现在可以使用 ctx-help 查看所有可用命令!"