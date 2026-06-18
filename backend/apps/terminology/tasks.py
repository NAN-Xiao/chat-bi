from typing import Any

from sqlalchemy.orm import scoped_session, sessionmaker

from apps.terminology.curd.terminology import run_fill_empty_embeddings, save_embeddings
from common.core.db import engine
from common.core.task_queue import current_task_tenant_id, task_handler

session_maker = scoped_session(sessionmaker(bind=engine))


def _int_list(value: Any) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value]


@task_handler("terminology.embedding")
def terminology_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    save_embeddings(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": len(ids), "tenant_id": tenant_id}


@task_handler("terminology.fill_empty_embedding")
def fill_empty_terminology_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    run_fill_empty_embeddings(session_maker, tenant_id=tenant_id)
    return {"status": "completed", "tenant_id": tenant_id}
