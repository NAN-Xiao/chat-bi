"""
脚本说明：这个脚本放系统管理里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from typing import Any

from sqlalchemy.orm import scoped_session, sessionmaker

from apps.chat.curd.custom_prompt_embedding import (
    run_fill_empty_custom_prompt_skill_embedding,
    save_custom_prompt_skill_embedding,
)
from common.core.db import engine
from common.core.task_queue import current_task_tenant_id
from common.core.task_queue import task_handler, utc_now


session_maker = scoped_session(sessionmaker(bind=engine))


def _int_list(value: Any) -> list[int]:
    """
    是什么：_int_list 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not value:
        return []
    return [int(item) for item in value]


@task_handler("system.ping")
async def ping_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：ping_task 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return {
        "message": payload.get("message") or "pong",
        "echo": payload,
        "finished_at": utc_now(),
    }


@task_handler("custom_prompt.skill_embedding")
def custom_prompt_skill_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：custom_prompt_skill_embedding_task 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    count = save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": count, "tenant_id": tenant_id}


@task_handler("custom_prompt.fill_empty_skill_embedding")
def fill_empty_custom_prompt_skill_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：fill_empty_custom_prompt_skill_embedding_task 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    count = run_fill_empty_custom_prompt_skill_embedding(session_maker, tenant_id=tenant_id)
    return {"count": count, "tenant_id": tenant_id}
