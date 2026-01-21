"""新闻分析Agent - 支持流式输出和会话持久化"""

import os
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from dotenv import load_dotenv
from httpx import Timeout
from langchain.agents import create_agent
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph

from app.agents.rag.news_rag import list_news, search_news
from app.core.memory import get_checkpointer

load_dotenv()

_agent: Optional[CompiledStateGraph] = None
_checkpointer: Optional[AsyncSqliteSaver] = None

MAX_DISPLAY_COUNT = 20


def _format_results(results: list, total_count: int) -> list[dict]:
    """格式化搜索结果，超过数量限制时添加提示"""
    display_results = results[:MAX_DISPLAY_COUNT]

    formatted = [
        {
            "title": doc.metadata.get("title"),
            "news_date": doc.metadata.get("news_date"),
            "url": doc.metadata.get("url"),
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
            k=k or 15,
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
    timeout = Timeout(
        connect=10.0,
        read=180.0,  # 流式响应需要更长的读取超时
        write=30.0,
        pool=30.0,
    )
    return ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.6")),
        max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "8192")),
        timeout=timeout,
        max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "3")),
        streaming=True,
    )


def _create_tavily_tool() -> TavilySearchResults:
    """创建Tavily联网搜索工具"""
    return TavilySearchResults(
        max_results=5,
        search_depth="advanced",
        include_answer=True,
        include_raw_content=False,
        name="web_search",
        description="""【仅作为最后手段使用】联网搜索工具。
严格限制：只有在满足以下全部条件时才可使用：
1. 已使用 search_news_tool 进行至少2次不同策略的搜索（语义搜索+关键词搜索）
2. 本地新闻库确实没有相关信息，或用户明确要求查询外部信息（如公司官网、维基百科）
3. 用户问题涉及非新闻联播覆盖的内容（如国外实时新闻、技术文档等）

禁止场景：不要因为本地搜索结果"不够多"或"不够理想"就直接使用联网搜索，应先尝试不同关键词重新搜索本地库。""",
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
    )


def _get_system_prompt(current_time: str) -> str:
    """生成系统提示词"""
    # 解析当前时间以获取年份
    current_year = current_time.split("-")[0]
    return f"""你是一位专业的新闻联播分析专家，专注于挖掘央视新闻联播数据的深层价值。

【⚠️ 关键时间信息 - 请牢记】
**当前时间：{current_time}**
**当前年份：{current_year}年**

时间认知要求：
- 你必须始终以 {current_year} 年为基准进行思考和回答
- "今年"指的是 {current_year} 年，"去年"指的是 {int(current_year) - 1} 年
- "最近"、"近期"的新闻应优先搜索 {current_year} 年的数据
- 在搜索和分析时，确保日期参数与用户询问的时间范围一致
- 回答中提及日期时，确认年份是否正确，避免错误引用过去年份的信息
- 如果用户没有指定时间范围，默认查询最近的新闻（{current_year}年）

【核心定位】
你的主要数据来源是**新闻联播**，这是中国最权威的官方新闻发布平台。你的价值在于：
- 从官方报道中解读政策信号和国家战略方向
- 分析新闻联播的报道频次、篇幅、措辞变化背后的意义
- 帮助用户理解"新闻联播说了什么"以及"为什么这么说"
- 识别政策趋势、行业风向、区域发展重点

【数据来源说明】
本地新闻库存储的是**央视新闻联播**的文稿数据。新闻联播的特点：
- 权威性高：代表官方立场和政策导向
- 覆盖面广：涵盖政治、经济、科技、民生、国际等领域
- 信息密度大：措辞精炼，每个用词都有深意
- 时效性：反映当前国家工作重点和政策方向

【⚠️ 工具使用铁律 - 本地优先，深度挖掘】

**第一原则：必须优先且充分使用 search_news_tool**

每次搜索都应该尝试多种策略以最大化召回率：

搜索策略组合（按需并行调用）：
1. **关键词精确搜索**：content_contains="具体关键词"
2. **同义词/相关词搜索**：用不同表述再搜一次
3. **语义搜索**：query="概念性描述"（适合模糊查询）
4. **扩大范围搜索**：增加 k 值，或调整日期范围

示例 - 用户问"低空经济相关政策"：
→ 并行调用：
  - search_news_tool(content_contains="低空经济", k=10)
  - search_news_tool(content_contains="无人机", k=10)
  - search_news_tool(content_contains="通用航空", k=10)
  - search_news_tool(query="低空经济 无人机 通航产业发展", k=10)

示例 - 用户问"人工智能发展"：
→ 并行调用：
  - search_news_tool(content_contains="人工智能", k=10)
  - search_news_tool(content_contains="AI", k=10)
  - search_news_tool(content_contains="大模型", k=10)
  - search_news_tool(query="人工智能 数字经济 科技创新", k=10)

**第二原则：web_search 仅作为补充，不是替代**

只有在以下情况才可使用 web_search：
- 用户明确要求查询外部信息（如某公司官网、维基百科）
- 需要查询新闻联播不会报道的内容（如国外小众新闻、技术文档）
- 本地搜索多次尝试后确实没有任何相关内容（需先尝试至少2-3种不同关键词）

❌ 禁止：因为本地搜索"结果少"或"相关度不高"就直接用联网搜索
✅ 正确：换关键词、换表述、扩大范围，充分挖掘本地数据

【搜索技巧】

新闻联播的语言特点（搜索时注意）：
- 官方表述往往比日常用语更正式，如"数字经济"而非"互联网经济"
- 政策类常用词：高质量发展、新质生产力、现代化产业体系、乡村振兴
- 尝试核心关键词的多种变体

关键词提取技巧：
- 从用户问题中提取2-3个核心词
- 思考同义词、上位词、相关词
- 官方表述 vs 民间表述的转换

【输出格式规范 - 简洁易读】

根据内容类型选择最合适的展示方式：

**1. 新闻列表展示 - 使用表格**
| 日期 | 标题 | 关键信息 |
|------|------|----------|
| 2025-01-15 | 《xxx》 | 要点摘要 |

**2. 对比分析 - 使用对照表格**
| 维度 | A | B |
|------|---|---|
| xxx | ... | ... |

**3. 趋势分析 - 使用时间线或分点**
- **2024年Q1**：xxx
- **2024年Q2**：xxx

**4. 政策解读 - 使用分层结构**
**核心政策**：一句话概括
- 要点1
- 要点2

**影响分析**：
- 对行业：...
- 对企业：...

【输出原则】
- 简洁：不堆砌原文，提炼关键信息
- 结构化：善用表格、分点、层级
- 有洞察：不只是罗列，要有分析和解读
- 标注来源：使用 [1][2] 引用，末尾列出参考新闻

【引用格式】
正文中：根据报道，xxx[1]，同时xxx[2]...

---

**参考来源：**

[1] [《新闻标题》](url链接) - 2025-01-18
[2] [《新闻标题》](url链接) - 2025-01-17

注意：搜索结果中包含 url 字段，请务必使用 Markdown 链接语法 `[标题](url)` 让用户可以点击查看原文。参考来源标题后、列表前各空一行。

【分析框架】（灵活使用）
- **信号解读**：新闻联播报道这个意味着什么？
- **频次分析**：这个话题最近被提及多少次？趋势如何？
- **措辞变化**：官方表述有什么变化？
- **政策关联**：与哪些政策/会议/领导讲话相关？
- **行业影响**：对相关行业/企业/地区有何启示？"""


def create_news_agent() -> CompiledStateGraph:
    """创建新闻分析Agent（无持久化）"""
    model = _create_model()
    tavily_tool = _create_tavily_tool()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_prompt = _get_system_prompt(current_time)

    return create_agent(
        model=model,
        tools=[search_news_tool, tavily_tool],
        system_prompt=system_prompt,
    )


def get_news_agent() -> CompiledStateGraph:
    """获取单例Agent实例（无持久化）"""
    global _agent
    if _agent is None:
        _agent = create_news_agent()
    return _agent


async def get_news_agent_with_memory() -> CompiledStateGraph:
    """获取带 memory 持久化的 Agent 实例"""
    global _checkpointer

    if _checkpointer is None:
        _checkpointer = await get_checkpointer()

    model = _create_model()
    tavily_tool = _create_tavily_tool()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 使用与 create_news_agent 相同的 system_prompt
    system_prompt = _get_system_prompt(current_time)

    return create_agent(
        model=model,
        tools=[search_news_tool, tavily_tool],
        system_prompt=system_prompt,
        checkpointer=_checkpointer,
    )


async def stream_agent_response(
    query: str,
    chat_history: Optional[list] = None,
    thread_id: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    流式生成Agent响应

    Args:
        query: 用户查询
        chat_history: 聊天历史（仅在无 thread_id 时使用）
        thread_id: LangGraph 会话ID，如果提供则使用 checkpointer 自动管理历史

    Yields:
        dict: 事件类型和数据
            - {"type": "token", "content": "..."}  # 模型输出token
            - {"type": "tool_start", "name": "...", "input": {...}}  # 工具调用开始
            - {"type": "tool_end", "name": "...", "output": "..."}  # 工具调用结束
            - {"type": "usage", "input_tokens": N, "output_tokens": N}  # token用量
            - {"type": "done"}  # 完成
            - {"type": "error", "message": "..."}  # 错误
    """
    # 如果有 thread_id，使用带 memory 的 agent
    if thread_id:
        agent = await get_news_agent_with_memory()
        config = {"configurable": {"thread_id": thread_id}}
        messages = [{"role": "user", "content": query}]
    else:
        agent = get_news_agent()
        config = {}
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
            config=config,
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
