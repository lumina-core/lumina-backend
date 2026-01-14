from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models.news import NewsArticleRead
from app.services.news_service import NewsService


router = APIRouter()


class PromptExample(BaseModel):
    category: str
    prompts: List[str]


class PromptExamplesResponse(BaseModel):
    examples: List[PromptExample]


PROMPT_EXAMPLES = [
    PromptExample(
        category="投资视角",
        prompts=[
            "最近有什么关于新能源汽车的新闻？帮我分析下对产业链上下游的投资机会",
            "搜索AI芯片相关新闻，我是做半导体投资的，帮我分析下行业格局变化",
            "低空经济最近有什么政策动态？作为投资人我应该关注哪些方向",
        ],
    ),
    PromptExample(
        category="行业研究",
        prompts=[
            "帮我梳理一下最近大模型领域的重要进展，分析下技术发展趋势",
            "找下最近关于跨境电商的新闻，总结下行业面临的主要挑战和机遇",
            "搜索光伏产业相关报道，分析下产能过剩问题的走向",
        ],
    ),
    PromptExample(
        category="企业决策",
        prompts=[
            "我是做SaaS的，搜索下企业服务领域的新闻，帮我分析竞争态势",
            "找下关于出海的新闻，我们公司在考虑东南亚市场，有什么需要注意的",
        ],
    ),
    PromptExample(
        category="政策解读",
        prompts=[
            "最近有什么关于数据安全的政策新闻？帮我解读下对企业的影响",
            "搜索医疗改革相关新闻，分析下对医药行业的政策走向",
        ],
    ),
    PromptExample(
        category="综合分析",
        prompts=[
            "帮我看看最近一周科技领域有什么重大事件，给我一个简要的行业洞察",
            "搜索人工智能相关新闻，从技术、政策、市场三个角度帮我分析",
        ],
    ),
    PromptExample(
        category="快速查询",
        prompts=[
            "帮我搜一下华为的新闻",
            "最近有什么热点新闻",
            "找下关于机器人的报道",
        ],
    ),
]


@router.get(
    "/prompt-examples",
    response_model=PromptExamplesResponse,
    summary="获取新闻分析示例提示词",
)
async def get_prompt_examples():
    """返回新闻分析Agent的示例提示词，按分类组织"""
    return PromptExamplesResponse(examples=PROMPT_EXAMPLES)


class NewsListResponse(BaseModel):
    total: int
    items: List[NewsArticleRead]


class DailyCountResponse(BaseModel):
    date: date
    count: int


@router.get("/by-date", response_model=NewsListResponse, summary="按日期查询新闻联播")
async def get_news_by_date(
    date_value: date = Query(..., alias="date", description="新闻日期"),
    session: AsyncSession = Depends(get_session),
):
    service = NewsService(session)
    articles = await service.get_news_by_date(date_value)
    return NewsListResponse(total=len(articles), items=articles)


@router.get("/range", response_model=NewsListResponse, summary="按日期区间查询新闻联播")
async def get_news_by_range(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    session: AsyncSession = Depends(get_session),
):
    if end_date < start_date:
        raise HTTPException(
            status_code=400, detail="end_date must be on or after start_date"
        )

    service = NewsService(session)
    articles = await service.get_news_by_date_range(start_date, end_date)
    return NewsListResponse(total=len(articles), items=articles)


@router.get("/search", response_model=NewsListResponse, summary="按标题关键词搜索")
async def search_news(
    keyword: str = Query(..., min_length=1, description="标题关键词"),
    session: AsyncSession = Depends(get_session),
):
    service = NewsService(session)
    articles = await service.search_by_title(keyword)
    return NewsListResponse(total=len(articles), items=articles)


@router.get(
    "/stats/daily", response_model=DailyCountResponse, summary="查询指定日期新闻数量"
)
async def get_daily_stats(
    date_value: date = Query(..., alias="date", description="新闻日期"),
    session: AsyncSession = Depends(get_session),
):
    service = NewsService(session)
    count = await service.get_news_count_by_date(date_value)
    return DailyCountResponse(date=date_value, count=count)
