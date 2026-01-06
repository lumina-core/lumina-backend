"""新闻分析Agent - 支持流式输出"""

import os
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.rag.news_rag import search_news

load_dotenv()

_agent: Optional[CompiledStateGraph] = None


@tool
def search_news_tool(
    query: str,
    k: int = 5,
    start_date_int: Optional[int] = None,
    end_date_int: Optional[int] = None,
    title_contains: Optional[str] = None,
    content_contains: Optional[str] = None,
) -> list[dict]:
    """
    语义搜索新闻文章，支持多种过滤条件。

    Args:
        query: 搜索查询文本，用于语义相似度匹配（embedding搜索）
        k: 返回结果数量，默认5条
        start_date_int: 开始日期筛选，格式YYYYMMDD（如20250101），可选
        end_date_int: 结束日期筛选，格式YYYYMMDD（如20251231），可选
        title_contains: 标题必须包含的关键词（不区分大小写），可选
        content_contains: 内容必须包含的关键词（不区分大小写），可选

    Returns:
        新闻列表，每条包含 title, news_date, content 字段
    """
    results = search_news(
        query=query,
        k=k,
        start_date_int=start_date_int,
        end_date_int=end_date_int,
        title_contains=title_contains,
        content_contains=content_contains,
    )
    return [
        {
            "title": doc.metadata.get("title"),
            "news_date": doc.metadata.get("news_date"),
            "content": doc.page_content[:1000],
        }
        for doc in results
    ]


def _create_model() -> ChatOpenAI:
    """创建LLM模型实例"""
    return ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.6")),
        max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "8192")),
        timeout=int(os.getenv("OPENROUTER_TIMEOUT", "30")),
        max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "3")),
        streaming=True,
    )


def create_news_agent() -> CompiledStateGraph:
    """创建新闻分析Agent"""
    model = _create_model()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return create_agent(
        model=model,
        tools=[search_news_tool],
        system_prompt=f"你是一个新闻分析助手，可以通过语义搜索查找相关新闻并进行分析。当前时间：{current_time}",
    )


def get_news_agent() -> CompiledStateGraph:
    """获取单例Agent实例"""
    global _agent
    if _agent is None:
        _agent = create_news_agent()
    return _agent


async def stream_agent_response(
    query: str, chat_history: Optional[list] = None
) -> AsyncGenerator[dict, None]:
    """
    流式生成Agent响应

    Yields:
        dict: 事件类型和数据
            - {"type": "token", "content": "..."}  # 模型输出token
            - {"type": "tool_start", "name": "...", "input": {...}}  # 工具调用开始
            - {"type": "tool_end", "name": "...", "output": "..."}  # 工具调用结束
            - {"type": "done"}  # 完成
            - {"type": "error", "message": "..."}  # 错误
    """
    agent = get_news_agent()

    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": query})

    try:
        async for event in agent.astream_events(
            {"messages": messages},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield {"type": "token", "content": chunk.content}

            elif kind == "on_tool_start":
                yield {
                    "type": "tool_start",
                    "name": event["name"],
                    "input": event["data"].get("input", {}),
                }

            elif kind == "on_tool_end":
                output = event["data"].get("output", "")
                if isinstance(output, list):
                    output = f"找到 {len(output)} 条相关新闻"
                yield {
                    "type": "tool_end",
                    "name": event["name"],
                    "output": str(output)[:500],
                }

        yield {"type": "done"}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def invoke_agent(query: str, chat_history: Optional[list] = None) -> dict[str, Any]:
    """非流式调用Agent"""
    agent = get_news_agent()

    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": query})

    result = await agent.ainvoke({"messages": messages})
    return result
