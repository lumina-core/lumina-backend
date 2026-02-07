import uvicorn

from app.core.logging import setup_logging

LOG_LEVEL = "INFO"


def main():
    # 在 uvicorn 启动前初始化日志，确保所有日志统一输出到 logs/
    setup_logging(log_level=LOG_LEVEL)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=2,
        access_log=True,
        log_level=LOG_LEVEL.lower(),
        log_config=None,  # 禁用 uvicorn 默认日志配置，由 loguru 接管
    )


if __name__ == "__main__":
    main()
