from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models.news import NewsArticleRead
from app.services.news_service import NewsService


router = APIRouter()


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
