@echo off
REM Telegram 项目 Token-Friendly 上下文工具安装脚本 (Windows)
echo 🚀 设置 Telegram Token-Friendly 上下文工具...

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 需要 Python 3.6+ 才能使用上下文工具
    echo    请安装 Python 3: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✅ 找到 Python: %PYTHON_VERSION%

REM 测试核心功能
echo 🧪 测试上下文切换功能...
python context_switch.py help >nul 2>&1
if errorlevel 1 (
    echo ❌ 上下文切换工具测试失败
    pause
    exit /b 1
)
echo ✅ 上下文切换工具测试通过

REM 生成 Windows 批处理别名
set TELEGRAM_ROOT=%~dp0
set ALIASES_FILE=context_aliases.bat

echo @echo off > %ALIASES_FILE%
echo REM Telegram 项目上下文切换别名 (自动生成) >> %ALIASES_FILE%
echo REM 项目路径: %TELEGRAM_ROOT% >> %ALIASES_FILE%
echo. >> %ALIASES_FILE%
echo doskey ctx=python "%TELEGRAM_ROOT%context_switch.py" $* >> %ALIASES_FILE%
echo doskey ctx-status=python "%TELEGRAM_ROOT%context_switch.py" status >> %ALIASES_FILE%
echo doskey ctx-help=python "%TELEGRAM_ROOT%context_switch.py" help >> %ALIASES_FILE%
echo doskey ctx-sub=python "%TELEGRAM_ROOT%context_switch.py" subscription >> %ALIASES_FILE%
echo doskey ctx-club=python "%TELEGRAM_ROOT%context_switch.py" club >> %ALIASES_FILE%
echo doskey ctx-ins=python "%TELEGRAM_ROOT%context_switch.py" insurance >> %ALIASES_FILE%
echo doskey ctx-inv=python "%TELEGRAM_ROOT%context_switch.py" investment >> %ALIASES_FILE%
echo doskey ctx-all=python "%TELEGRAM_ROOT%context_switch.py" all >> %ALIASES_FILE%
echo. >> %ALIASES_FILE%
echo echo 🗺️  Telegram 项目上下文工具已加载 >> %ALIASES_FILE%
echo echo 💡 使用 'ctx-help' 查看所有命令 >> %ALIASES_FILE%
echo python "%TELEGRAM_ROOT%status_bar.py" full >> %ALIASES_FILE%

echo ✅ 生成 Windows 别名文件: %ALIASES_FILE%

echo.
echo 🎉 安装完成！使用方法：
echo.
echo 1️⃣  激活别名（在此目录下运行）:
echo    %ALIASES_FILE%
echo.
echo 2️⃣  快速切换上下文:
echo    ctx-sub     # 订阅系统
echo    ctx-club    # 俱乐部系统  
echo    ctx-ins     # 保险系统
echo    ctx-inv     # 投资工具
echo    ctx-all     # 全部模块
echo.
echo 3️⃣  查看状态:
echo    ctx-status  # 当前模式详情
echo.
echo 📖 详细文档: CONTEXT_AUTOMATION.md
echo.
echo 🎯 现在可以使用 ctx-help 查看所有可用命令!
pause