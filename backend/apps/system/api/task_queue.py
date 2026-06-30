from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.system.crud.user import is_system_admin
from apps.system.schemas.access_context import require_current_tenant_id
from apps.system.schemas.permission import AppPermission, require_permissions
from common.core.deps import CurrentUser
from common.core.task_queue import enqueue_task, get_task, task_queue_health
from common.core.task_registry import register_builtin_tasks

register_builtin_tasks()

router = APIRouter(tags=["system/task"], prefix="/system/tasks", include_in_schema=False)


class PingTaskRequest(BaseModel):
    message: str | None = Field(default=None, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


def _current_tenant_id(current_user) -> int:
    """
    是什么：_current_tenant_id 是 backend/apps/system/api/task_queue.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _current_tenant_id 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return require_current_tenant_id(current_user)


def _can_read_task(task: dict[str, Any], current_user) -> bool:
    """
    是什么：_can_read_task 是 backend/apps/system/api/task_queue.py 中的同步函数。
    谁调用：由 FastAPI 路由处理函数或同模块业务辅助流程调用。
    做了什么：围绕 _can_read_task 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    if int(task.get("tenant_id")) != _current_tenant_id(current_user):
        return False
    if is_system_admin(current_user):
        return True
    return task.get("created_by") == current_user.id


@router.get("/health")
@require_permissions(permission=AppPermission(role=["admin"]))
async def task_health():
    """
    是什么：task_health 是 backend/apps/system/api/task_queue.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 task_health 的语义处理系统管理相关逻辑，并把结果返回或写入状态。
    """
    return await task_queue_health()


@router.post("/ping")
@require_permissions(permission=AppPermission(role=["admin"]))
async def create_ping_task(req: PingTaskRequest, current_user: CurrentUser):
    """
    是什么：create_ping_task 是 backend/apps/system/api/task_queue.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：创建、初始化或组装系统管理相关对象和数据，并返回或写入对应状态。
    """
    payload = {"message": req.message, **req.payload}
    return await enqueue_task(
        "system.ping",
        payload,
        created_by=current_user.id,
        tenant_id=_current_tenant_id(current_user),
    )


@router.get("/{task_id}")
async def get_task_info(task_id: str, current_user: CurrentUser):
    """
    是什么：get_task_info 是 backend/apps/system/api/task_queue.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询系统管理相关数据，整理后返回给调用方。
    """
    task = await get_task(task_id, tenant_id=_current_tenant_id(current_user))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _can_read_task(task, current_user):
        raise HTTPException(status_code=403, detail="Task access denied")
    return task
