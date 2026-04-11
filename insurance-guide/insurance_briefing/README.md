# 保险资讯周报系统

参考 `investment_tracker` 架构，为保险从业者打造的自动化资讯聚合系统。

## 📁 项目结构

```
insurance_briefing/
├── config.py              # 数据源和关键词配置
├── crawler.py             # 网络爬虫模块（RSS、HTML解析）
├── analyzer.py            # 内容分析与分类
├── briefing_generator.py  # 简报生成器（主程序）
├── requirements.txt       # Python依赖
└── output/               # 生成的简报输出目录
    ├── weekly.html       # 最新一期周报
    ├── index.html        # 历史归档索引
    └── briefing_weekly_YYYYMMDD.html  # 历史快照
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd insurance-guide/insurance_briefing
pip install -r requirements.txt
```

### 2. 本地运行

```bash
# 生成最近7天的周报
python briefing_generator.py

# 生成最近14天的周报
python briefing_generator.py --days 14

# 指定输出目录
python briefing_generator.py --output /var/www/insurance-briefing

# 指定兴趣关键词（过滤相关内容）
python briefing_generator.py --interests 储蓄险 医疗险 跨境保险
```

### 3. 查看简报

```bash
open output/weekly.html
```

## 📊 数据源配置

当前已配置的数据源（在 `config.py` 中）：

### 监管机构
- 香港保险业监管局（IA）公告
- （待添加）内地银保监会

### 行业新闻
- （待添加）保险时报 RSS
- （待添加）其他行业媒体

### 社交内容
- 知乎保险话题热门回答
- 微信公众号精选（需手动收集）

### 添加新数据源

编辑 `config.py`，在相应的字典中添加：

```python
NEWS_SOURCES = {
    "your_source": {
        "name": "数据源名称",
        "rss": "https://example.com/feed",  # 如果是RSS
        "type": "rss",
        "priority": "high"
    }
}
```

## 🔧 自定义爬虫

如果需要爬取特定网站，在 `crawler.py` 中创建新的爬虫类：

```python
class YourCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("你的数据源名称")
    
    def crawl(self, days: int = 7) -> List[Article]:
        # 实现爬取逻辑
        articles = []
        # ...
        return articles
```

然后在 `crawl_all_sources()` 函数中调用：

```python
results['your_source'] = YourCrawler().crawl(days)
```

## 🤖 自动化部署

### 方案1：定时任务（Cron）

在服务器上设置每周一早上自动生成：

```bash
# 编辑 crontab
crontab -e

# 添加任务（每周一上午8点）
0 8 * * 1 cd /app/telegram/insurance-guide/insurance_briefing && python3 briefing_generator.py --output /var/www/insurance-briefing
```

### 方案2：一键部署脚本

参考 `investment_tracker/vps-setup.sh`，创建类似的部署脚本：

```bash
#!/bin/bash
# deploy-insurance-briefing.sh

echo "安装依赖..."
pip install -r requirements.txt

echo "配置 Nginx..."
# 配置 Nginx 托管 /var/www/insurance-briefing

echo "配置定时任务..."
# 写入 crontab

echo "生成首期简报..."
python briefing_generator.py --output /var/www/insurance-briefing

echo "部署完成！"
echo "访问：http://your-domain.com/insurance-briefing/"
```

## 📈 进阶功能建议

### 1. 智能摘要（AI增强）

集成 OpenAI/Claude API 自动生成文章摘要：

```python
# 在 analyzer.py 中添加
def generate_summary_with_ai(article: Article) -> str:
    """使用大模型生成文章摘要"""
    # 调用 API...
    return summary
```

### 2. 情感分析

分析行业舆情（正面/中性/负面）：

```python
def analyze_sentiment(article: Article) -> str:
    """分析文章情感倾向"""
    # 实现情感分析...
    return "positive" | "neutral" | "negative"
```

### 3. 趋势洞察

统计高频关键词，发现行业趋势：

```python
def detect_trends(articles: List[Article]) -> Dict[str, int]:
    """检测热门话题趋势"""
    # 统计关键词频次...
    return {"储蓄险新规": 15, "医疗通胀": 8, ...}
```

### 4. 个性化推荐

根据用户历史阅读行为推荐相关内容：

```python
def recommend_articles(user_id: str, articles: List[Article]) -> List[Article]:
    """基于用户偏好推荐"""
    # 实现推荐算法...
    return recommended
```

## ⚠️ 注意事项

### 法律与合规
- **尊重版权**：仅爬取公开信息，注明原文链接
- **遵守 robots.txt**：检查目标网站的爬虫协议
- **频率限制**：设置合理的请求间隔，避免对服务器造成压力

### 反爬虫应对
- 使用随机 User-Agent
- 添加请求延迟（已在 `CRAWLER_CONFIG` 中配置）
- 对于需要登录的网站（如知乎），考虑：
  - 使用官方 API
  - 手动收集链接后解析
  - 购买数据服务

### 数据质量
- 定期检查爬虫是否失效（网站改版会导致选择器失效）
- 监控爬取成功率
- 人工审核关键内容

## 📞 扩展思路

### 整合到现有系统
可以将此系统与您的 `insurance-guide` 网站整合：

```
insurance-guide/
├── index.html              # 主网站
├── articles/               # 现有文章
├── briefing/              # 新增：每周资讯
│   ├── weekly.html
│   └── index.html
└── insurance_briefing/    # 后端系统
```

### 多渠道分发
- **Telegram Bot**：自动推送周报到 Telegram 频道
- **邮件订阅**：定期发送邮件给订阅用户
- **微信公众号**：同步发布到公众号

### 协作特性
- 团队成员可以点赞/收藏文章
- 添加评论和笔记功能
- 导出为 PDF 供线下阅读

## 🎯 下一步行动

1. **测试运行**：`python briefing_generator.py` 看看效果
2. **完善数据源**：在 `config.py` 中添加更多RSS源
3. **优化爬虫**：根据实际网站结构调整 HTML 解析逻辑
4. **部署上线**：配置服务器自动化运行
5. **持续迭代**：根据使用反馈优化分类和推荐算法

---

**有问题？** 查看代码注释或参考 `investment_tracker` 的实现方式。
