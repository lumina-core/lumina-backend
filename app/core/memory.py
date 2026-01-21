"""LangGraph Memory/Checkpointer 配置"""

from pathlib import Path
from typing import Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger

_checkpointer: Optional[AsyncSqliteSaver] = None


def get_memory_db_path() -> str:
    """获取 memory 数据库路径"""
    data_dir = Path("./data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "langgraph_memory.db")


async def get_checkpointer() -> AsyncSqliteSaver:
    """获取或创建 checkpointer 单例"""
    global _checkpointer

    if _checkpointer is None:
        db_path = get_memory_db_path()
        logger.info(f"初始化 LangGraph Checkpointer: {db_path}")
        _checkpointer = AsyncSqliteSaver.from_conn_string(
            f"sqlite+aiosqlite:///{db_path}"
        )
        # 确保表创建
        async with _checkpointer:
            pass  # 连接时会自动创建表
        logger.info("✓ LangGraph Checkpointer 初始化完成")

    return _checkpointer


async def close_checkpointer():
    """关闭 checkpointer 连接"""
    global _checkpointer
    if _checkpointer is not None:
        # AsyncSqliteSaver 会自动管理连接
        _checkpointer = None
        logger.info("LangGraph Checkpointer 已关闭")
