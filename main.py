import uvicorn


def main():
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,      # 生产环境关闭热重载
        workers=2,         # 多进程提高并发和容错
        access_log=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
