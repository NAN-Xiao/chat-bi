from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


AGENT_CONTEXT_SNAPSHOT_VERSION = 1


def _text_digest(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text_length(value: str | None) -> int:
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
