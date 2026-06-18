from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.system.crud.user import is_system_admin
from apps.system.schemas.permission import AppPermission, require_permissions
from apps.system.tasks import ping_task as _ping_task  # noqa: F401
from common.core.deps import CurrentUser
from common.core.task_queue import enqueue_task, get_task, task_queue_health

router = APIRouter(tags=["system/task"], prefix="/system/tasks", include_in_schema=False)


class PingTaskRequest(BaseModel):
    message: str | None = Field(default=None, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


def _can_read_task(task: dict[str, Any], current_user) -> bool:
    if is_system_admin(current_user):
        return True
    return task.get("created_by") == current_user.id


@router.get("/health")
@require_permissions(permission=AppPermission(role=["admin"]))
async def task_health():
    return await task_queue_health()


@router.post("/ping")
@require_permissions(permission=AppPermission(role=["admin"]))
async def create_ping_task(req: PingTaskRequest, current_user: CurrentUser):
    payload = {"message": req.message, **req.payload}
    return await enqueue_task("system.ping", payload, created_by=current_user.id)


@router.get("/{task_id}")
async def get_task_info(task_id: str, current_user: CurrentUser):
    task = await get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _can_read_task(task, current_user):
        raise HTTPException(status_code=403, detail="Task access denied")
    return task
