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
from common.core.task_queue import task_handler
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
    lang = payload.get("lang") or "zh-CN"
    trans = i18n(lang=lang)
    with Session(engine) as session:
        result = sync_single_fields(session, trans, table_id, schedule_embeddings=False)
        table = result.get("table") if isinstance(result, dict) else None
        datasource = result.get("datasource") if isinstance(result, dict) else None
    run_save_table_embeddings([table_id])
    if datasource:
        run_save_ds_embeddings([datasource])
    return {
        "table_id": table_id,
        "table_name": table,
        "datasource_id": datasource,
    }


@task_handler("datasource.table_embedding")
def table_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    save_table_embedding(session_maker, ids)
    return {"ids": ids, "count": len(ids)}


@task_handler("datasource.datasource_embedding")
def datasource_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    save_ds_embedding(session_maker, ids)
    return {"ids": ids, "count": len(ids)}


@task_handler("datasource.fill_empty_table_and_ds_embedding")
def fill_empty_table_and_ds_embedding_task(_payload: dict[str, Any]) -> dict[str, Any]:
    run_fill_empty_table_and_ds_embedding(session_maker)
    return {"status": "completed"}
