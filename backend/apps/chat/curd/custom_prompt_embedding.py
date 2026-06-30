import hashlib
import json
import traceback
from typing import Any

from sqlalchemy import and_, select, update

from apps.ai_model.embedding import EmbeddingModelCache
from common.core.config import settings
from common.utils.utils import AppLogUtil


def build_skill_embedding_text(name: str | None, description: str | None) -> str:
    """
    是什么：build_skill_embedding_text 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装聊天和 Agent相关对象和数据，并返回或写入对应状态。
    """
    parts = []
    if name and name.strip():
        parts.append(f"Skill Name: {name.strip()}")
    if description and description.strip():
        parts.append(f"Skill Description: {description.strip()}")
    return "\n".join(parts).strip()


def skill_embedding_signature(name: str | None, description: str | None) -> str:
    """
    是什么：skill_embedding_signature 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 skill_embedding_signature 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    text = build_skill_embedding_text(name, description)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def skill_definition_signature(name: str | None, description: str | None, prompt: str | None) -> str:
    """
    是什么：skill_definition_signature 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 skill_definition_signature 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    payload = {
        "name": (name or "").strip(),
        "description": (description or "").strip(),
        "prompt": (prompt or "").strip(),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embedding_vector_from_json(value: Any) -> list[float] | None:
    """
    是什么：embedding_vector_from_json 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 embedding_vector_from_json 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list):
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def save_custom_prompt_skill_embedding(
        session_maker,
        ids: list[int],
        tenant_id: int | None = None,
) -> int:
    """
    是什么：save_custom_prompt_skill_embedding 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装聊天和 Agent相关对象和数据，并返回或写入对应状态。
    """
    if not settings.EMBEDDING_ENABLED:
        return 0
    normalized_ids = [int(item) for item in ids or []]
    if not normalized_ids:
        return 0

    session = None
    try:
        from apps.chat.models.custom_prompt_model import CustomPrompt

        session = session_maker()
        conditions = [
            CustomPrompt.id.in_(normalized_ids),
            CustomPrompt.type == "DATA_SKILL",
        ]
        if tenant_id is not None:
            conditions.append(CustomPrompt.tenant_id == int(tenant_id))
        rows = session.execute(select(CustomPrompt).where(*conditions)).scalars().all()
        model = EmbeddingModelCache.get_model()
        saved = 0
        for row in rows:
            signature = skill_definition_signature(row.name, row.description, row.prompt)
            text = build_skill_embedding_text(row.name, row.description)
            if not text:
                row.embedding = None
                row.embedding_signature = signature
                session.add(row)
                saved += 1
                continue
            vector = model.embed_query(text)
            row.embedding = json.dumps(vector, ensure_ascii=False)
            row.embedding_signature = signature
            session.add(row)
            saved += 1
        session.commit()
        if saved:
            AppLogUtil.info(f"Saved custom prompt skill embeddings: count={saved}")
        return saved
    except Exception:
        if session is not None:
            session.rollback()
        traceback.print_exc()
        return 0
    finally:
        try:
            session_maker.remove()
        except Exception:
            pass


def run_fill_empty_custom_prompt_skill_embedding(
        session_maker,
        tenant_id: int | None = None,
        limit: int = 500,
) -> int:
    """
    是什么：run_fill_empty_custom_prompt_skill_embedding 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行聊天和 Agent主流程，协调下游服务并处理结果或异常。
    """
    if not settings.EMBEDDING_ENABLED:
        return 0
    session = None
    try:
        from apps.chat.models.custom_prompt_model import CustomPrompt

        session = session_maker()
        stmt = select(CustomPrompt).where(CustomPrompt.type == "DATA_SKILL").limit(max(1, int(limit or 500)))
        if tenant_id is not None:
            stmt = stmt.where(CustomPrompt.tenant_id == int(tenant_id))
        rows = session.execute(stmt).scalars().all()
        ids = [
            int(row.id)
            for row in rows
            if row.id
            and (
                embedding_vector_from_json(row.embedding) is None
                or row.embedding_signature != skill_definition_signature(row.name, row.description, row.prompt)
            )
        ]
        if not ids:
            return 0
        return save_custom_prompt_skill_embedding(session_maker, ids, tenant_id=tenant_id)
    except Exception:
        traceback.print_exc()
        return 0
    finally:
        try:
            session_maker.remove()
        except Exception:
            pass


def clear_custom_prompt_skill_embedding(session, prompt_id: int) -> None:
    """
    是什么：clear_custom_prompt_skill_embedding 是 backend/apps/chat/curd/custom_prompt_embedding.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：删除或清理聊天和 Agent相关数据、缓存或临时状态。
    """
    from apps.chat.models.custom_prompt_model import CustomPrompt

    session.execute(
        update(CustomPrompt)
        .where(CustomPrompt.id == int(prompt_id))
        .values(embedding=None, embedding_signature=None)
    )
