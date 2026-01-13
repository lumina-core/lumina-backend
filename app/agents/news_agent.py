"""新闻分析Agent - 支持流式输出"""

import os
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.rag.news_rag import list_news, search_news

load_dotenv()

_agent: Optional[CompiledStateGraph] = None

MAX_DISPLAY_COUNT = 20


def _format_results(results: list, total_count: int) -> list[dict]:
    """格式化搜索结果，超过数量限制时添加提示"""
    display_results = results[:MAX_DISPLAY_COUNT]

    formatted = [
        {
            "title": doc.metadata.get("title"),
            "news_date": doc.metadata.get("news_date"),
            # "url": doc.metadata.get("url"),
            # "content": doc.page_content[:1000],
            "content": doc.page_content,
        }
        for doc in display_results
    ]

    if total_count > MAX_DISPLAY_COUNT:
        formatted.append(
            {
                "notice": f"共找到 {total_count} 条结果，由于数量较多，仅展示前 {MAX_DISPLAY_COUNT} 条。如需查看更多，请缩小日期范围或添加更多筛选条件。"
            }
        )

    return formatted


@tool
def search_news_tool(
    query: Optional[str] = None,
    k: Optional[int] = None,
    start_date_int: Optional[int] = None,
    end_date_int: Optional[int] = None,
    title_contains: Optional[str] = None,
    content_contains: Optional[str] = None,
) -> list[dict]:
    """
    搜索新闻文章，支持两种独立的搜索策略。

    【重要：搜索策略选择】
    本工具支持两种搜索策略，请根据需求选择其一，避免混用：

    策略1 - 语义搜索（推荐用于模糊/概念性查询）：
      - 使用 query 参数进行向量相似度匹配
      - 适合：查找某个话题、概念、事件相关的新闻
      - 示例：query="人工智能对就业市场的影响"

    策略2 - 关键词匹配（推荐用于精确查找）：
      - 使用 title_contains 或 content_contains 参数
      - 适合：查找包含特定词汇、名称、术语的新闻
      - 示例：title_contains="OpenAI"

    【最佳实践】
    - 不要同时使用 query 和 *_contains 参数，除非用户明确要求
    - 复杂查询建议分多次调用：先用语义搜索找相关内容，再用关键词精确筛选
    - 日期参数可与任一策略组合使用

    Args:
        query: 语义搜索查询文本（向量匹配），与 *_contains 参数互斥使用
        k: 返回结果数量。语义搜索默认5条，关键词匹配默认100条
        start_date_int: 开始日期，格式YYYYMMDD（如20250101）
        end_date_int: 结束日期，格式YYYYMMDD（如20251231）
        title_contains: 标题关键词匹配（不区分大小写），与 query 互斥使用
        content_contains: 内容关键词匹配（不区分大小写），与 query 互斥使用

    Returns:
        新闻列表，每条包含 title, news_date, url, content 字段。
        超过20条时仅展示前20条并附带提示。
    """
    if query:
        results = search_news(
            query=query,
            k=k or 5,
            start_date_int=start_date_int,
            end_date_int=end_date_int,
            title_contains=title_contains,
            content_contains=content_contains,
        )
    else:
        results = list_news(
            start_date_int=start_date_int,
            end_date_int=end_date_int,
            title_contains=title_contains,
            content_contains=content_contains,
            limit=k or 100,
        )

    return _format_results(results, len(results))


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

    system_prompt = f"""你是一个专业的新闻分析助手。当前时间：{current_time}

【工具使用指南】
你可以使用 search_news_tool 搜索新闻，该工具支持两种独立的搜索策略：

1. 语义搜索（query参数）：基于向量相似度匹配，适合概念性、话题性查询
2. 关键词匹配（content_contains参数）：精确匹配特定词汇

【技术实现原理】
- 语义搜索：使用 embedding 向量在 Chroma 向量数据库中进行相似度检索，能找到语义相关但措辞不同的内容
- 关键词匹配：直接在 SQLite 数据库中使用 SQL LIKE 查询，精确匹配包含指定词汇的文章
- 混用时的问题：如果同时传入 query 和 *_contains，系统会先做向量搜索取 k*3 条结果，再在内存中过滤关键词，可能导致召回不全

【重要原则】
- 这两种策略应分开使用，不要在同一次调用中混用
- 一般情况下优先使用 query 或 content_contains，不要使用 title_contains
- title_contains 仅在用户明确要求"标题包含XX"时才使用
- 对于复杂需求，可多次调用工具获取更全面的结果
- 日期筛选可与任一策略组合

【调用示例】
用户："帮我搜索低空经济相关的新闻"
✅ 正确：search_news_tool(query="低空经济")
✅ 正确：search_news_tool(content_contains="低空经济")
❌ 错误：search_news_tool(query="低空经济", content_contains="低空经济")  # 不要混用

用户："找一下最近关于AI芯片的报道"
✅ 正确：search_news_tool(query="AI芯片 人工智能芯片")
✅ 正确：search_news_tool(content_contains="AI芯片")

用户："找标题里带有'特斯拉'的新闻"
✅ 正确：search_news_tool(title_contains="特斯拉")  # 用户明确要求标题包含

用户："查找2025年1月关于新能源汽车的深度分析"
✅ 正确：search_news_tool(query="新能源汽车行业分析", start_date_int=20250101, end_date_int=20250131)"""

    return create_agent(
        model=model,
        tools=[search_news_tool],
        system_prompt=system_prompt,
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
            - {"type": "usage", "input_tokens": N, "output_tokens": N}  # token用量
            - {"type": "done"}  # 完成
            - {"type": "error", "message": "..."}  # 错误
    """
    agent = get_news_agent()

    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": query})

    total_input_tokens = 0
    total_output_tokens = 0

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

            elif kind == "on_chat_model_end":
                # 获取 token 用量
                output = event["data"].get("output")
                if (
                    output
                    and hasattr(output, "usage_metadata")
                    and output.usage_metadata
                ):
                    usage = output.usage_metadata
                    total_input_tokens += usage.get("input_tokens", 0)
                    total_output_tokens += usage.get("output_tokens", 0)

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

        # 返回 token 用量统计
        yield {
            "type": "usage",
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        }
        yield {"type": "done"}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def invoke_agent(
    query: str, chat_history: Optional[list] = None
) -> dict[str, Any]:
    """非流式调用Agent"""
    agent = get_news_agent()

    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": query})

    result = await agent.ainvoke({"messages": messages})
    return result


langgraph_agent = create_news_agent()
