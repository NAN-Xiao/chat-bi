from typing import Any

from common.core.task_queue import enqueue_task_detached
from common.core.task_registry import register_builtin_tasks
from common.utils.utils import AppLogUtil


def _int_list(value: list[int] | None) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value]


def _with_tenant(payload: dict[str, Any], tenant_id: int | None = None) -> dict[str, Any]:
    if tenant_id is None:
        return payload
    return {**payload, "tenant_id": int(tenant_id)}


def _enqueue_embedding_task(name: str, payload: dict[str, Any], tenant_id: int | None = None) -> None:
    try:
        register_builtin_tasks()
        task = enqueue_task_detached(name, _with_tenant(payload, tenant_id), tenant_id=tenant_id)
        if task:
            AppLogUtil.info(f"Queued embedding task: {name} task_id={task.get('id')}")
    except Exception:
        AppLogUtil.exception(f"Failed to queue embedding task: {name}")


def run_save_terminology_embeddings(ids: list[int], tenant_id: int | None = None):
    _enqueue_embedding_task("terminology.embedding", {"ids": _int_list(ids)}, tenant_id)


def fill_empty_terminology_embeddings(tenant_id: int | None = None):
    _enqueue_embedding_task("terminology.fill_empty_embedding", {}, tenant_id)


def run_save_data_training_embeddings(ids: list[int], tenant_id: int | None = None):
    _enqueue_embedding_task("data_training.embedding", {"ids": _int_list(ids)}, tenant_id)


def fill_empty_data_training_embeddings(tenant_id: int | None = None):
    _enqueue_embedding_task("data_training.fill_empty_embedding", {}, tenant_id)


def run_save_table_embeddings(ids: list[int], tenant_id: int | None = None):
    _enqueue_embedding_task("datasource.table_embedding", {"ids": _int_list(ids)}, tenant_id)


def run_save_ds_embeddings(ids: list[int], tenant_id: int | None = None):
    _enqueue_embedding_task("datasource.datasource_embedding", {"ids": _int_list(ids)}, tenant_id)


def fill_empty_table_and_ds_embeddings(tenant_id: int | None = None):
    _enqueue_embedding_task("datasource.fill_empty_table_and_ds_embedding", {}, tenant_id)
