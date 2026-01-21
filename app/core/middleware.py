"""中间件"""

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        # 添加 request_id 到 request.state
        request.state.request_id = request_id

        # 请求日志
        logger.info(
            f"[{request_id}] --> {request.method} {request.url.path}"
            f"{('?' + str(request.url.query)) if request.url.query else ''}"
        )

        try:
            response = await call_next(request)
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error(f"[{request_id}] <-- 500 | {duration:.2f}ms | Error: {e}")
            raise

        duration = (time.perf_counter() - start_time) * 1000

        # 响应日志
        log_level = "info" if response.status_code < 400 else "warning"
        getattr(logger, log_level)(
            f"[{request_id}] <-- {response.status_code} | {duration:.2f}ms"
        )

        # 添加响应头
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.2f}ms"

        return response


def register_middlewares(app: FastAPI) -> None:
    """注册中间件"""
    app.add_middleware(RequestLoggingMiddleware)
