from typing import Any

from sqlalchemy.orm import scoped_session, sessionmaker

from apps.data_training.curd.data_training import (
    run_fill_empty_embeddings,
    save_embeddings,
)
from common.core.db import engine
from common.core.task_queue import task_handler

session_maker = scoped_session(sessionmaker(bind=engine))


def _int_list(value: Any) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value]


@task_handler("data_training.embedding")
def data_training_embedding_task(payload: dict[str, Any]) -> dict[str, Any]:
    ids = _int_list(payload.get("ids"))
    save_embeddings(session_maker, ids)
    return {"ids": ids, "count": len(ids)}


@task_handler("data_training.fill_empty_embedding")
def fill_empty_data_training_embedding_task(_payload: dict[str, Any]) -> dict[str, Any]:
    run_fill_empty_embeddings(session_maker)
    return {"status": "completed"}
