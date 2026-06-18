from typing import Any

from sqlalchemy.orm import scoped_session, sessionmaker
from sqlmodel import Session

from apps.datasource.crud.datasource import sync_single_fields
from apps.datasource.crud.table import (
    run_fill_empty_table_and_ds_embedding,
    save_ds_embedding,
    save_table_embedding,
)
from common.core.db import engine
from common.core.task_queue import current_task_tenant_id, task_handler
from common.utils.embedding_threads import (
    run_save_ds_embeddings,
    run_save_table_embeddings,
)
from common.utils.locale import I18n

session_maker = scoped_session(sessionmaker(bind=engine))
i18n = I18n()


def _int_list(value: Any) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value]


@task_handler("datasource.sync_fields")
def sync_fields_task(payload: dict[str, Any]) -> dict[str, Any]:
    table_id = int(payload["table_id"])
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    lang = payload.get("lang") or "zh-CN"
    trans = i18n(lang=lang)
    with Session(engine) as session:
        result = sync_single_fields(session, trans, table_id, schedule_embeddings=False, tenant_id=tenant_id)
        table = result.get("table") if isinstance(result, dict) else None
        datasource = result.get("datasource") if isinstance(result, dict) else None
    run_save_table_embeddings([table_id], tenant_id=tenant_id)
    if datasource:
        run_save_ds_embeddings([datasource], tenant_id=tenant_id)
    return {
        "table_id": table_id,
        "table_name": table,
        "datasource_id": datasource,
        "tenant_id": tenant_id,
    }


@task_handler("datasource.table_embedding")
def table_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    save_table_embedding(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": len(ids), "tenant_id": tenant_id}


@task_handler("datasource.datasource_embedding")
def datasource_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    save_ds_embedding(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": len(ids), "tenant_id": tenant_id}


@task_handler("datasource.fill_empty_table_and_ds_embedding")
def fill_empty_table_and_ds_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    run_fill_empty_table_and_ds_embedding(session_maker, tenant_id=tenant_id)
    return {"status": "completed", "tenant_id": tenant_id}
