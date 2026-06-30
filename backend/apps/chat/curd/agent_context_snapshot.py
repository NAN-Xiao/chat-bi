"""
脚本说明：这个脚本封装聊天问数据和 Agent的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


AGENT_CONTEXT_SNAPSHOT_VERSION = 1


def _text_digest(value: str | None) -> str | None:
    """
    是什么：_text_digest 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    text = (value or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text_length(value: str | None) -> int:
    """
    是什么：_text_length 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return len((value or "").strip())


def build_agent_context_snapshot(
    *,
    surface: str,
    datasource_id: int | str | None = None,
    datasource_name: str | None = None,
    custom_prompt_id: int | str | None = None,
    custom_prompt_text: str | None = None,
    custom_prompt_model_id: int | str | None = None,
    data_skill_id: int | str | None = None,
    data_skill_text: str | None = None,
    ai_model_id: int | str | None = None,
    ai_model_name: str | None = None,
    target_scope: str | None = None,
) -> dict[str, Any]:
    """
    是什么：build_agent_context_snapshot 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
    return {
        "version": AGENT_CONTEXT_SNAPSHOT_VERSION,
        "captured_at": datetime.utcnow().isoformat(timespec="seconds"),
        "surface": surface,
        "target_scope": target_scope,
        "datasource": {
            "id": str(datasource_id) if datasource_id not in (None, "") else None,
            "name": datasource_name or None,
        },
        "custom_agent": {
            "id": str(custom_prompt_id) if custom_prompt_id not in (None, "") else None,
            "applied": bool((custom_prompt_text or "").strip()),
            "model_id": str(custom_prompt_model_id) if custom_prompt_model_id not in (None, "") else None,
            "content_sha256": _text_digest(custom_prompt_text),
            "content_chars": _text_length(custom_prompt_text),
        },
        "data_skill": {
            "id": str(data_skill_id) if data_skill_id not in (None, "") else None,
            "applied": bool((data_skill_text or "").strip()),
            "content_sha256": _text_digest(data_skill_text),
            "content_chars": _text_length(data_skill_text),
        },
        "runtime_model": {
            "id": str(ai_model_id) if ai_model_id not in (None, "") else None,
            "name": ai_model_name or None,
        },
    }
