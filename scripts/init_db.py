"""数据库初始化脚本

用途：
- 检查并创建数据库
- 创建所有数据表
- 可在项目启动前独立运行

运行方式：
    uv run python scripts/init_db.py
"""

import asyncio
import sys

from loguru import logger

from app.core.database import init_database


async def main():
    """主函数：初始化数据库"""
    try:
        logger.info("开始数据库初始化流程...")
        await init_database()
        logger.info("✓ 数据库初始化成功")

    except Exception as e:
        logger.error(f"✗ 数据库初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
