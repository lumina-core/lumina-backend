"""定时任务模块

此模块包含所有定时任务的定义和注册逻辑
"""

from app.tasks.news_tasks import register_news_tasks
from app.tasks.example_tasks import register_example_tasks

__all__ = ["register_news_tasks", "register_example_tasks"]
