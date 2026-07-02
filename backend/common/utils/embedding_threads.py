"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import hashlib
import json
from typing import Any

from common.core.task_queue import enqueue_task_detached
from common.core.task_registry import register_builtin_tasks
from common.utils.utils import AppLogUtil


def _int_list(value: list[int] | None) -> list[int]:
    """
    是什么：_int_list 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not value:
        return []
    return sorted({int(item) for item in value})


def _with_tenant(payload: dict[str, Any], tenant_id: int | None = None) -> dict[str, Any]:
    """
    是什么：_with_tenant 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if tenant_id is None:
        return payload
    return {**payload, "tenant_id": int(tenant_id)}


def _enqueue_embedding_task(name: str, payload: dict[str, Any], tenant_id: int | None = None) -> None:
    """
    是什么：_enqueue_embedding_task 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        register_builtin_tasks()
        normalized_payload = _with_tenant(payload, tenant_id)
        dedupe_key = json.dumps(
            {"name": name, "payload": normalized_payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        dedupe_key = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()
        task = enqueue_task_detached(name, normalized_payload, tenant_id=tenant_id, dedupe_key=dedupe_key)
        if task:
            AppLogUtil.info(f"Queued embedding task: {name} task_id={task.get('id')}")
    except Exception:
        AppLogUtil.exception(f"Failed to queue embedding task: {name}")


def run_save_table_embeddings(ids: list[int], tenant_id: int | None = None):
    """
    是什么：run_save_table_embeddings 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具的主要流程跑起来，一步步调用需要的处理。
    """
    _enqueue_embedding_task("datasource.table_embedding", {"ids": _int_list(ids)}, tenant_id)


def run_save_ds_embeddings(ids: list[int], tenant_id: int | None = None):
    """
    是什么：run_save_ds_embeddings 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具的主要流程跑起来，一步步调用需要的处理。
    """
    _enqueue_embedding_task("datasource.datasource_embedding", {"ids": _int_list(ids)}, tenant_id)


def fill_empty_table_and_ds_embeddings(tenant_id: int | None = None):
    """
    是什么：fill_empty_table_and_ds_embeddings 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _enqueue_embedding_task("datasource.fill_empty_table_and_ds_embedding", {}, tenant_id)


def run_save_custom_prompt_skill_embeddings(ids: list[int], tenant_id: int | None = None):
    """
    是什么：run_save_custom_prompt_skill_embeddings 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具的主要流程跑起来，一步步调用需要的处理。
    """
    _enqueue_embedding_task("custom_prompt.skill_embedding", {"ids": _int_list(ids)}, tenant_id)


def fill_empty_custom_prompt_skill_embeddings(tenant_id: int | None = None):
    """
    是什么：fill_empty_custom_prompt_skill_embeddings 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _enqueue_embedding_task("custom_prompt.fill_empty_skill_embedding", {}, tenant_id)
