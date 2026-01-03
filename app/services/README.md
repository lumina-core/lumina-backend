# Services 服务层

本目录包含应用的核心业务逻辑服务。

## 目录结构

```
services/
├── __init__.py
├── news_scraper.py      # 新闻爬虫服务
└── README.md            # 本文档
```

## 服务说明

### NewsScraperService (新闻爬虫服务)

**功能：** 从 CCTV 新闻联播网站抓取新闻数据

**特性：**
- 单例模式设计，全局共享 HTTP 客户端
- 支持获取指定日期的新闻列表
- 支持批量抓取新闻详细内容
- 自动添加随机延迟，避免请求过于频繁
- 完全独立于数据库层，仅负责数据抓取

**使用方式：**

```python
from datetime import date
from app.services.news_scraper import news_scraper_service

# 方式 1: 仅获取新闻列表
news_list = await news_scraper_service.fetch_news_list(date(2025, 11, 5))

# 方式 2: 获取单条新闻内容
content = await news_scraper_service.fetch_news_content("https://...")

# 方式 3: 完整抓取（包含详细内容）
articles = await news_scraper_service.scrape_daily_news(date(2025, 11, 5))

# 使用完毕后关闭客户端
await news_scraper_service.close()
```

**完整示例：** 参考 `examples/news_scraper_example.py`

## 设计原则

1. **单一职责：** 每个服务类只负责一个特定的业务领域
2. **依赖解耦：** 服务层不依赖数据库，数据持久化由上层调用者决定
3. **可测试性：** 便于编写单元测试和集成测试
4. **可复用性：** 服务可在不同的上下文中被复用
