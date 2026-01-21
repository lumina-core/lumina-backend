"""聊天路由 - 流式SSE接口，集成积分系统"""

import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.news_agent import stream_agent_response
from app.core.database import get_session, async_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.services.user_credit_service import (
    validate_user_can_chat,
    deduct_user_credits,
)

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求"""

    query: str
    chat_history: Optional[list] = None


async def _sse_generator(
    query: str,
    user_id: int,
    chat_history: Optional[list] = None,
):
    """SSE事件生成器，支持用户积分扣除"""
    input_tokens = 0
    output_tokens = 0

    async for event in stream_agent_response(query, chat_history):
        # 捕获 usage 事件用于积分计算
        if event.get("type") == "usage":
            input_tokens = event.get("input_tokens", 0)
            output_tokens = event.get("output_tokens", 0)

            # 在 generator 内部创建新的 session 来扣除积分
            try:
                async with async_session() as db_session:
                    credits_deducted, remaining = await deduct_user_credits(
                        db_session,
                        user_id,
                        input_tokens,
                        output_tokens,
                        model=os.getenv("OPENROUTER_MODEL", "unknown"),
                    )
                    event["credits_deducted"] = credits_deducted
                    event["credits_remaining"] = remaining
                    logger.info(
                        f"用户 {user_id} 扣除 {credits_deducted} 积分，剩余 {remaining}"
                    )
            except Exception as e:
                logger.error(f"积分扣除失败: {e}")
                event["credit_error"] = str(e)

        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"


async def _validate_user_can_chat(user: User, session: AsyncSession) -> None:
    """验证用户是否可以聊天"""
    can_chat, error = await validate_user_can_chat(session, user.id)
    if not can_chat:
        raise HTTPException(status_code=403, detail=error)


@router.get("/stream")
async def chat_stream_get(
    query: str = Query(..., description="用户查询"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    GET方式流式聊天接口

    使用 Server-Sent Events (SSE) 流式返回响应
    Header: Authorization: Bearer <token> - 用户登录Token（必填）

    事件类型:
    - token: 模型输出的文本片段
    - tool_start: 工具调用开始
    - tool_end: 工具调用结束
    - usage: token用量和积分消耗
    - done: 响应完成
    - error: 发生错误
    """
    await _validate_user_can_chat(user, session)

    return StreamingResponse(
        _sse_generator(query, user.id, None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stream")
async def chat_stream_post(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    POST方式流式聊天接口

    支持传入聊天历史记录
    Header: Authorization: Bearer <token> - 用户登录Token（必填）
    """
    await _validate_user_can_chat(user, session)

    return StreamingResponse(
        _sse_generator(request.query, user.id, request.chat_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("")
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    非流式聊天接口

    返回完整响应
    Header: Authorization: Bearer <token> - 用户登录Token（必填）
    """
    from app.agents.news_agent import invoke_agent

    await _validate_user_can_chat(user, session)

    result = await invoke_agent(request.query, request.chat_history)
    messages = result.get("messages", [])
    response_msg = messages[-1] if messages else None
    response = response_msg.content if response_msg else ""

    # 从最后一条消息获取 usage 信息并扣除积分
    usage_info = {}
    if response_msg and hasattr(response_msg, "usage_metadata"):
        usage = response_msg.usage_metadata or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        if input_tokens or output_tokens:
            credits_deducted, remaining = await deduct_user_credits(
                session,
                user.id,
                input_tokens,
                output_tokens,
                model=os.getenv("OPENROUTER_MODEL", "unknown"),
            )
            usage_info = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "credits_deducted": credits_deducted,
                "credits_remaining": remaining,
            }

    return {"response": response, "usage": usage_info}
