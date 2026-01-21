"""全局异常处理"""

from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """统一错误响应格式"""

    code: int
    message: str
    detail: Optional[Any] = None


class AppException(Exception):
    """应用基础异常类"""

    def __init__(
        self,
        code: int = 500,
        message: str = "服务器内部错误",
        detail: Optional[Any] = None,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


class BadRequestException(AppException):
    """400 错误请求"""

    def __init__(self, message: str = "请求参数错误", detail: Optional[Any] = None):
        super().__init__(code=400, message=message, detail=detail)


class UnauthorizedException(AppException):
    """401 未授权"""

    def __init__(self, message: str = "未登录或Token已过期", detail: Optional[Any] = None):
        super().__init__(code=401, message=message, detail=detail)


class ForbiddenException(AppException):
    """403 禁止访问"""

    def __init__(self, message: str = "没有权限访问", detail: Optional[Any] = None):
        super().__init__(code=403, message=message, detail=detail)


class NotFoundException(AppException):
    """404 资源不存在"""

    def __init__(self, message: str = "资源不存在", detail: Optional[Any] = None):
        super().__init__(code=404, message=message, detail=detail)


class ConflictException(AppException):
    """409 资源冲突"""

    def __init__(self, message: str = "资源冲突", detail: Optional[Any] = None):
        super().__init__(code=409, message=message, detail=detail)


class TooManyRequestsException(AppException):
    """429 请求过于频繁"""

    def __init__(self, message: str = "请求过于频繁，请稍后再试", detail: Optional[Any] = None):
        super().__init__(code=429, message=message, detail=detail)


class InternalServerException(AppException):
    """500 服务器内部错误"""

    def __init__(self, message: str = "服务器内部错误", detail: Optional[Any] = None):
        super().__init__(code=500, message=message, detail=detail)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """处理应用自定义异常"""
        logger.warning(
            f"AppException: {exc.message} | path={request.url.path} | detail={exc.detail}"
        )
        return JSONResponse(
            status_code=exc.code,
            content=ErrorResponse(
                code=exc.code, message=exc.message, detail=exc.detail
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """处理未捕获的异常"""
        logger.exception(f"Unhandled exception: {exc} | path={request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                code=500,
                message="服务器内部错误",
                detail=str(exc) if app.debug else None,
            ).model_dump(),
        )
