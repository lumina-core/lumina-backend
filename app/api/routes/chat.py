"""聊天路由 - 流式SSE接口"""

import json
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.news_agent import stream_agent_response

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求"""

    query: str
    chat_history: Optional[list] = None


async def _sse_generator(query: str, chat_history: Optional[list] = None):
    """SSE事件生成器"""
    async for event in stream_agent_response(query, chat_history):
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"


@router.get("/stream")
async def chat_stream_get(
    query: str = Query(..., description="用户查询"),
):
    """
    GET方式流式聊天接口

    使用 Server-Sent Events (SSE) 流式返回响应

    事件类型:
    - token: 模型输出的文本片段
    - tool_start: 工具调用开始
    - tool_end: 工具调用结束
    - done: 响应完成
    - error: 发生错误
    """
    return StreamingResponse(
        _sse_generator(query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stream")
async def chat_stream_post(request: ChatRequest):
    """
    POST方式流式聊天接口

    支持传入聊天历史记录
    """
    return StreamingResponse(
        _sse_generator(request.query, request.chat_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("")
async def chat(request: ChatRequest):
    """
    非流式聊天接口

    返回完整响应
    """
    from app.agents.news_agent import invoke_agent

    result = await invoke_agent(request.query, request.chat_history)
    messages = result.get("messages", [])
    response = messages[-1].content if messages else ""
    return {"response": response}
