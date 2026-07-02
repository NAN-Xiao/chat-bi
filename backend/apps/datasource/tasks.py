"""
脚本说明：这个脚本放数据源里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from typing import Any

from sqlmodel import Session
from sqlalchemy.orm import scoped_session, sessionmaker

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

session_maker = scoped_session(sessionmaker(bind=engine, class_=Session))
i18n = I18n()


def _int_list(value: Any) -> list[int]:
    """
    是什么：_int_list 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not value:
        return []
    return [int(item) for item in value]


@task_handler("datasource.sync_fields")
def sync_fields_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：sync_fields_task 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源相关的信息改成最新状态，并保存这些变化。
    """
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
    """
    是什么：table_embedding_task 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    save_table_embedding(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": len(ids), "tenant_id": tenant_id}


@task_handler("datasource.datasource_embedding")
def datasource_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：datasource_embedding_task 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    ids = _int_list(payload.get("ids"))
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    save_ds_embedding(session_maker, ids, tenant_id=tenant_id)
    return {"ids": ids, "count": len(ids), "tenant_id": tenant_id}


@task_handler("datasource.fill_empty_table_and_ds_embedding")
def fill_empty_table_and_ds_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：fill_empty_table_and_ds_embedding_task 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    run_fill_empty_table_and_ds_embedding(session_maker, tenant_id=tenant_id)
    return {"status": "completed", "tenant_id": tenant_id}
