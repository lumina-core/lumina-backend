"""聊天路由 - 流式SSE接口，集成积分系统"""

import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.news_agent import stream_agent_response
from app.core.database import get_session
from app.services.credit_service import deduct_credits, validate_invite_code

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求"""

    query: str
    chat_history: Optional[list] = None


async def _sse_generator(
    query: str,
    chat_history: Optional[list] = None,
    invite_code: Optional[str] = None,
    session: Optional[AsyncSession] = None,
):
    """SSE事件生成器，支持积分扣除"""
    input_tokens = 0
    output_tokens = 0

    async for event in stream_agent_response(query, chat_history):
        # 捕获 usage 事件用于积分计算
        if event.get("type") == "usage":
            input_tokens = event.get("input_tokens", 0)
            output_tokens = event.get("output_tokens", 0)

            # 如果有邀请码，扣除积分
            if invite_code and session:
                try:
                    credits_deducted, remaining = await deduct_credits(
                        session,
                        invite_code,
                        input_tokens,
                        output_tokens,
                        model=os.getenv("OPENROUTER_MODEL", "unknown"),
                    )
                    event["credits_deducted"] = credits_deducted
                    event["credits_remaining"] = remaining
                except Exception as e:
                    event["credit_error"] = str(e)

        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n"


async def _validate_code(
    x_invite_code: Optional[str], session: AsyncSession
) -> Optional[str]:
    """验证邀请码，返回有效的邀请码或 None"""
    if not x_invite_code:
        return None

    is_valid, error = await validate_invite_code(session, x_invite_code)
    if not is_valid:
        raise HTTPException(status_code=403, detail=error)

    return x_invite_code


@router.get("/stream")
async def chat_stream_get(
    query: str = Query(..., description="用户查询"),
    x_invite_code: Optional[str] = Header(None, alias="X-Invite-Code"),
    session: AsyncSession = Depends(get_session),
):
    """
    GET方式流式聊天接口

    使用 Server-Sent Events (SSE) 流式返回响应
    Header: X-Invite-Code - 邀请码（必填）

    事件类型:
    - token: 模型输出的文本片段
    - tool_start: 工具调用开始
    - tool_end: 工具调用结束
    - usage: token用量和积分消耗
    - done: 响应完成
    - error: 发生错误
    """
    invite_code = await _validate_code(x_invite_code, session)

    return StreamingResponse(
        _sse_generator(query, None, invite_code, session),
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
    x_invite_code: Optional[str] = Header(None, alias="X-Invite-Code"),
    session: AsyncSession = Depends(get_session),
):
    """
    POST方式流式聊天接口

    支持传入聊天历史记录
    Header: X-Invite-Code - 邀请码（必填）
    """
    invite_code = await _validate_code(x_invite_code, session)

    return StreamingResponse(
        _sse_generator(request.query, request.chat_history, invite_code, session),
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
    x_invite_code: Optional[str] = Header(None, alias="X-Invite-Code"),
    session: AsyncSession = Depends(get_session),
):
    """
    非流式聊天接口

    返回完整响应
    Header: X-Invite-Code - 邀请码（必填）
    """
    from app.agents.news_agent import invoke_agent

    invite_code = await _validate_code(x_invite_code, session)

    result = await invoke_agent(request.query, request.chat_history)
    messages = result.get("messages", [])
    response_msg = messages[-1] if messages else None
    response = response_msg.content if response_msg else ""

    # 从最后一条消息获取 usage 信息并扣除积分
    usage_info = {}
    if invite_code and response_msg and hasattr(response_msg, "usage_metadata"):
        usage = response_msg.usage_metadata or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        if input_tokens or output_tokens:
            credits_deducted, remaining = await deduct_credits(
                session,
                invite_code,
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
