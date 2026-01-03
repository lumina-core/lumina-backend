"""定时任务管理 API"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.scheduler import scheduler_manager

router = APIRouter()


class JobInfo(BaseModel):
    """任务信息模型"""

    id: str
    name: str
    next_run_time: datetime | None
    trigger: str


class JobListResponse(BaseModel):
    """任务列表响应模型"""

    total: int
    jobs: List[JobInfo]


@router.get("/", response_model=JobListResponse, summary="获取所有定时任务")
async def get_all_jobs():
    """获取所有已注册的定时任务列表"""
    jobs = scheduler_manager.get_jobs()

    job_list = [
        JobInfo(
            id=job.id,
            name=job.name,
            next_run_time=job.next_run_time,
            trigger=str(job.trigger),
        )
        for job in jobs
    ]

    return JobListResponse(total=len(job_list), jobs=job_list)


@router.get("/{job_id}", response_model=JobInfo, summary="获取指定任务详情")
async def get_job(job_id: str):
    """获取指定 ID 的定时任务详情"""
    job = scheduler_manager.scheduler.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

    return JobInfo(
        id=job.id,
        name=job.name,
        next_run_time=job.next_run_time,
        trigger=str(job.trigger),
    )


@router.post("/{job_id}/run", summary="手动触发任务执行")
async def run_job(job_id: str):
    """手动触发指定任务立即执行（不影响原定时计划）"""
    job = scheduler_manager.scheduler.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

    # 立即执行任务（异步）
    job.func()

    return {"message": f"任务 {job_id} 已触发执行", "job_name": job.name}


@router.post("/{job_id}/pause", summary="暂停任务")
async def pause_job(job_id: str):
    """暂停指定任务（不会删除任务，可以恢复）"""
    job = scheduler_manager.scheduler.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

    scheduler_manager.scheduler.pause_job(job_id)

    return {"message": f"任务 {job_id} 已暂停", "job_name": job.name}


@router.post("/{job_id}/resume", summary="恢复任务")
async def resume_job(job_id: str):
    """恢复已暂停的任务"""
    job = scheduler_manager.scheduler.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

    scheduler_manager.scheduler.resume_job(job_id)

    return {"message": f"任务 {job_id} 已恢复", "job_name": job.name}


@router.get("/status/scheduler", summary="获取调度器状态")
async def get_scheduler_status():
    """获取调度器运行状态"""
    is_running = scheduler_manager.scheduler.running

    return {
        "running": is_running,
        "timezone": str(scheduler_manager.scheduler.timezone),
        "total_jobs": len(scheduler_manager.get_jobs()),
    }
