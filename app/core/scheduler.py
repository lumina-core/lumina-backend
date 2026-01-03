"""APScheduler 调度器配置和管理"""

from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from loguru import logger


class SchedulerManager:
    """调度器管理器（单例模式）

    职责：
    - 创建和管理 APScheduler 实例
    - 提供统一的调度器访问接口
    - 处理调度器生命周期
    """

    _instance: Optional["SchedulerManager"] = None
    _scheduler: Optional[AsyncIOScheduler] = None

    def __new__(cls) -> "SchedulerManager":
        """单例模式：确保只有一个调度器实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化调度器管理器"""
        if self._scheduler is None:
            self._initialize_scheduler()

    def _initialize_scheduler(self):
        """初始化 APScheduler 实例"""
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {
            "coalesce": True,  # 合并堆积的任务
            "max_instances": 1,  # 同一任务最多同时运行 1 个实例
            "misfire_grace_time": 60,  # 任务错过时间容忍度（秒）
        }

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="Asia/Shanghai",  # 使用中国时区
        )

        logger.info("✓ 调度器初始化完成")

    def start(self):
        """启动调度器"""
        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("🕒 调度器已启动")
        else:
            logger.warning("调度器已经在运行中")

    def shutdown(self, wait: bool = True):
        """关闭调度器

        Args:
            wait: 是否等待正在执行的任务完成
        """
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("🔌 调度器已关闭")

    @property
    def scheduler(self) -> AsyncIOScheduler:
        """获取调度器实例"""
        if self._scheduler is None:
            raise RuntimeError("调度器尚未初始化")
        return self._scheduler

    def get_jobs(self):
        """获取所有已注册的任务"""
        return self._scheduler.get_jobs()

    def print_jobs(self):
        """打印所有已注册的任务信息"""
        jobs = self.get_jobs()
        if not jobs:
            logger.info("当前没有已注册的定时任务")
            return

        logger.info(f"已注册的定时任务（共 {len(jobs)} 个）：")
        for job in jobs:
            logger.info(f"  - {job.id}: {job.name} (下次运行: {job.next_run_time})")


# 创建全局单例实例
scheduler_manager = SchedulerManager()
