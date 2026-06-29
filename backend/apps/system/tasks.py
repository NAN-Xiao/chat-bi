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
    if not value:
        return []
    return [int(item) for item in value]


@task_handler("system.ping")
async def ping_task(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": payload.get("message") or "pong",
        "echo": payload,
        "finished_at": utc_now(),
    }


@task_handler("custom_prompt.skill_embedding")
def custom_prompt_skill_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    count = save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": count, "tenant_id": tenant_id}


@task_handler("custom_prompt.fill_empty_skill_embedding")
def fill_empty_custom_prompt_skill_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    count = run_fill_empty_custom_prompt_skill_embedding(session_maker, tenant_id=tenant_id)
    return {"count": count, "tenant_id": tenant_id}
