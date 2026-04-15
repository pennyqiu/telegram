# 保险指南系统

## 用途
保险知识科普与决策辅助工具，包含大陆/香港/台湾保险产品分析。

## 模块构成
- **静态内容站**：`public/index.html` + `articles/` + `wechat-copy/`
- **FastAPI 服务**：`fastapi_app/` - 简单后端API
- **简报生成器**：`insurance_briefing/` - 自动化内容爬取与整理

## 本地开发
```bash
cd insurance-guide/

# 静态站 - 直接打开
open public/index.html

# FastAPI 服务
cd fastapi_app/
pip install -r requirements.txt
python main.py

# 简报系统
cd insurance_briefing/  
pip install -r requirements.txt
python briefing_generator.py
```

## 部署
- 静态站：任意静态托管（Vercel/Netlify）
- 简报系统：见 `insurance_briefing/DEPLOY.md`