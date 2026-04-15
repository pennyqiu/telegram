# 🤖 上下文自动化切换系统

> **解决问题**：告别手动改 `.cursorignore`，一键切换 AI 上下文，永不忘记！

## 🚀 **快速开始**

### **方式一：Cursor 命令面板（推荐）**
1. 按 `Cmd+Shift+P` 打开命令面板
2. 输入 "Tasks: Run Task"
3. 选择对应的上下文模式：
   - 🎯 Context: 查看当前模式
   - 📱 Context: 订阅系统模式  
   - ⚽ Context: 俱乐部系统模式
   - 🏥 Context: 保险指南模式
   - 💰 Context: 投资工具模式
   - 🌍 Context: 全部模块模式

### **方式二：终端命令**
```bash
# 激活别名（仅需一次）
source .context_aliases

# 快速切换
ctx-sub        # 切换到订阅系统
ctx-club       # 切换到俱乐部系统  
ctx-ins        # 切换到保险系统
ctx-inv        # 切换到投资工具
ctx-all        # 显示所有模块

# 查看状态
ctx-status     # 详细状态信息
ctx-help       # 帮助信息
```

### **方式三：直接执行脚本**
```bash
python3 context_switch.py subscription
python3 context_switch.py status
```

## 🎯 **各模式说明**

| 模式 | 命令 | AI 可见范围 | 使用场景 |
|------|------|-------------|----------|
| **订阅系统** | `ctx-sub` | `tg-subscription/` + `docs/` | 开发 Telegram Bot、支付流程 |
| **俱乐部系统** | `ctx-club` | `tg-club/` + `tg-subscription/`（API依赖） | 开发足球队管理功能 |
| **保险指南** | `ctx-ins` | `insurance-guide/` | 编辑保险内容、配置爬虫 |  
| **投资工具** | `ctx-inv` | 投资相关 HTML + `investment_tracker/` | 开发估值计算器、追踪工具 |
| **全部模块** | `ctx-all` | 所有文件 | 跨模块重构、全局配置 |

## 💡 **智能提示集成**

### **终端 Prompt 显示当前模式**
添加到 `~/.zshrc`：
```bash
# 加载 Telegram 项目别名
if [ -f ~/telegram/.context_aliases ]; then
    source ~/telegram/.context_aliases
fi

# 在 prompt 中显示模式（可选）
function telegram_context_prompt() {
    if [ -f ~/telegram/status_bar.py ]; then
        echo " $(python3 ~/telegram/status_bar.py emoji)"
    fi
}

# 集成到 prompt（示例）  
PS1='%~ $(telegram_context_prompt) $ '
```

### **Cursor 状态栏显示（高级）**
可以通过 Cursor 插件 API 在状态栏显示当前模式，但需要自定义插件开发。

## 🔧 **工作流程示例**

### **场景1：开发订阅系统功能**
```bash
# 1. 切换上下文
ctx-sub
# ✅ 已切换到：📱 Telegram 订阅系统  
# 📝 专注 tg-subscription/ + docs/

# 2. 现在问 AI 问题，只会看到订阅相关代码
# 3. 完成后可以切回全部模式
ctx-all
```

### **场景2：改保险内容时不想看到 Telegram 代码**
```bash  
# 1. 切换到保险模式
ctx-ins
# ✅ 已切换到：🏥 保险指南系统
# 📝 专注 insurance-guide/

# 2. AI 现在专注保险内容，不会被 Telegram 代码干扰
```

### **场景3：跨模块重构**
```bash
# 全部模式，查看所有文件依赖关系
ctx-all
# ✅ 已切换到：🌍 全部模块
# 📝 显示所有文件 (仅保留通用忽略)
```

## 🎨 **自定义配置**

### **添加新的上下文模式**
编辑 `context_switch.py` 中的 `CONTEXT_MODES`：
```python
CONTEXT_MODES = {
    'mymode': {
        'name': '🎯 我的自定义模式',
        'description': '专注特定文件',
        'ignore_patterns': [
            'unwanted-dir/',
            '*.unwanted'
        ]
    }
}
```

### **修改忽略规则**
直接修改各模式的 `ignore_patterns` 数组即可。

## 🐛 **故障排除**

### **Python3 未找到**
```bash
# macOS 使用 Homebrew 安装
brew install python3

# 或使用系统 Python
python context_switch.py subscription
```

### **脚本权限问题**  
```bash
chmod +x context_switch.py
chmod +x status_bar.py
```

### **查看当前 .cursorignore 状态**
```bash
ctx-status
# 或
cat .cursorignore | grep -v "^#" | grep -v "^$"
```

## 🔄 **工作流程建议**

1. **开始工作前**：`ctx-status` 检查当前模式
2. **切换任务时**：使用对应的 `ctx-xxx` 命令
3. **需要全局视野时**：`ctx-all`  
4. **完成工作后**：可选择保持当前模式或切回 `all`

---

**🎯 核心价值**：
- ⚡ **效率提升**：一键切换，无需记忆复杂的忽略规则
- 🧠 **认知减负**：AI 只看相关代码，回答更精准
- 🔄 **可逆操作**：随时切换，不会丢失配置
- 💡 **可视化**：随时知道当前处于什么模式

---

*在 Cursor 中，建议把这个文档加入书签，方便随时查阅命令。*