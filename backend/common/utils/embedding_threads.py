from typing import Any

from common.core.task_queue import enqueue_task_detached
from common.core.task_registry import register_builtin_tasks
from common.utils.utils import AppLogUtil


def _int_list(value: list[int] | None) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value]


def _enqueue_embedding_task(name: str, payload: dict[str, Any]) -> None:
    try:
        register_builtin_tasks()
        task = enqueue_task_detached(name, payload)
        if task:
            AppLogUtil.info(f"Queued embedding task: {name} task_id={task.get('id')}")
    except Exception:
        AppLogUtil.exception(f"Failed to queue embedding task: {name}")


def run_save_terminology_embeddings(ids: list[int]):
    _enqueue_embedding_task("terminology.embedding", {"ids": _int_list(ids)})


def fill_empty_terminology_embeddings():
    _enqueue_embedding_task("terminology.fill_empty_embedding", {})


def run_save_data_training_embeddings(ids: list[int]):
    _enqueue_embedding_task("data_training.embedding", {"ids": _int_list(ids)})


def fill_empty_data_training_embeddings():
    _enqueue_embedding_task("data_training.fill_empty_embedding", {})


def run_save_table_embeddings(ids: list[int]):
    _enqueue_embedding_task("datasource.table_embedding", {"ids": _int_list(ids)})


def run_save_ds_embeddings(ids: list[int]):
    _enqueue_embedding_task("datasource.datasource_embedding", {"ids": _int_list(ids)})


def fill_empty_table_and_ds_embeddings():
    _enqueue_embedding_task("datasource.fill_empty_table_and_ds_embedding", {})
