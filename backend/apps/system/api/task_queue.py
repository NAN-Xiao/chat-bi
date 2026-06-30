"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
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
    """
    类说明：PingTaskRequest 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    message: str | None = Field(default=None, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


def _current_tenant_id(current_user) -> int:
    """
    是什么：_current_tenant_id 是从当前用户里取租户 ID 的小工具。
    谁调用：需要知道当前用户属于哪个租户的接口会调用它。
    做了什么：把用户上下文里的租户 ID 取出来，方便后面做权限和数据隔离。
    """
    return require_current_tenant_id(current_user)


def _can_read_task(task: dict[str, Any], current_user) -> bool:
    """
    是什么：_can_read_task 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：task_health 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return await task_queue_health()


@router.post("/ping")
@require_permissions(permission=AppPermission(role=["admin"]))
async def create_ping_task(req: PingTaskRequest, current_user: CurrentUser):
    """
    是什么：create_ping_task 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
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
    是什么：get_task_info 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    task = await get_task(task_id, tenant_id=_current_tenant_id(current_user))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _can_read_task(task, current_user):
        raise HTTPException(status_code=403, detail="Task access denied")
    return task
