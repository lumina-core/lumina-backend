"""统一日志配置 - 基于 loguru"""

import logging
import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

LOG_FORMAT_FILE = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
)


class InterceptHandler(logging.Handler):
    """将标准 logging 日志转发到 loguru（拦截 uvicorn / sqlalchemy 等）"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(log_level: str = "INFO") -> None:
    """初始化日志配置，应在应用启动最早期调用"""

    # 移除 loguru 默认 handler
    logger.remove()

    # 控制台输出（带颜色）
    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=log_level,
        colorize=True,
    )

    # 常规日志文件（按天轮转，保留 30 天）
    logger.add(
        LOG_DIR / "app_{time:YYYY-MM-DD}.log",
        format=LOG_FORMAT_FILE,
        level=log_level,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,  # 多进程安全
    )

    # 错误日志单独文件
    logger.add(
        LOG_DIR / "error_{time:YYYY-MM-DD}.log",
        format=LOG_FORMAT_FILE,
        level="ERROR",
        rotation="00:00",
        retention="60 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
    )

    # 拦截标准 logging（uvicorn / sqlalchemy / apscheduler 等）
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy",
        "apscheduler",
    ]:
        logging.getLogger(name).handlers = [InterceptHandler()]

    logger.info("Logging initialized | level={} | dir={}", log_level, LOG_DIR.resolve())
