"""
脚本说明：这个脚本封装聊天问数据和 Agent的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
import json
import re
from enum import Enum
from typing import Any, Optional

from sqlalchemy import text as sql_text
from sqlmodel import Session

from apps.ai_model.embedding import EmbeddingModelCache
from apps.chat.curd.custom_prompt_embedding import embedding_vector_from_json, skill_definition_signature
from apps.datasource.embedding.utils import cosine_similarity
from apps.system.schemas.access_context import require_tenant_id
from common.core.config import settings
from common.utils.embedding_threads import run_save_custom_prompt_skill_embeddings
from common.utils.utils import AppLogUtil


class CustomPromptTypeEnum(str, Enum):
    """
    类说明：CustomPromptTypeEnum 收拢聊天问数据和 Agent里固定的可选值，避免代码里到处写零散字符串。
    """
    GENERATE_SQL = "GENERATE_SQL"
    ANALYSIS = "ANALYSIS"
    PREDICT_DATA = "PREDICT_DATA"
    DATA_SKILL = "DATA_SKILL"


class CustomPromptTargetScopeEnum(str, Enum):
    """
    类说明：CustomPromptTargetScopeEnum 收拢聊天问数据和 Agent里固定的可选值，避免代码里到处写零散字符串。
    """
    SMART_QA = "SMART_QA"
    ANALYSIS_ASSISTANT = "ANALYSIS_ASSISTANT"
    REPORT_INTERPRETATION = "REPORT_INTERPRETATION"
    ALL = "ALL"


class CustomPromptVisibilityScopeEnum(str, Enum):
    """
    类说明：CustomPromptVisibilityScopeEnum 收拢聊天问数据和 Agent里固定的可选值，避免代码里到处写零散字符串。
    """
    PLATFORM_PUBLIC = "PLATFORM_PUBLIC"
    ADMIN_PUBLIC = "ADMIN_PUBLIC"
    USER_PRIVATE = "USER_PRIVATE"


def _normalize_prompt_id(prompt_id: Optional[int | str]) -> Optional[int]:
    """
    是什么：_normalize_prompt_id 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if prompt_id in (None, ""):
        return None
    try:
        return int(prompt_id)
    except (TypeError, ValueError):
        return None


def _normalize_target_scope(
        target_scope: Optional[CustomPromptTargetScopeEnum | str],
) -> CustomPromptTargetScopeEnum:
    """
    是什么：_normalize_target_scope 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(target_scope, CustomPromptTargetScopeEnum):
        return target_scope
    try:
        return CustomPromptTargetScopeEnum(str(target_scope))
    except ValueError:
        return CustomPromptTargetScopeEnum.SMART_QA


def _xml_text(value: Optional[str]) -> str:
    """
    是什么：_xml_text 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _datasource_id_values(value) -> list[str]:
    """
    是什么：_datasource_id_values 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _row_matches_datasource(row, datasource: Optional[int]) -> bool:
    """
    是什么：_row_matches_datasource 用当前项目判断一条提示词或 Skill 是否可用于本次上下文。
    谁调用：运行时查找自定义 Agent 和 Data Skills 时调用。
    做了什么：全局记录直接放行；限定项目的记录必须命中当前 datasource。
    """
    if not row.get("specific_ds"):
        return True
    if datasource is None:
        return False
    return str(datasource) in _datasource_id_values(row.get("datasource_ids"))


def _prompt_log_text(name: str, description: str, system_prompt: str, label: str = "补充提示词") -> str:
    """
    是什么：_prompt_log_text 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parts = [f"名称：{name}"]
    if description:
        parts.append(f"描述：{description}")
    parts.append(f"{label}：{system_prompt}")
    return "\n".join(parts)


def _scope_label(visibility_scope: str | None, datasource_scoped: bool = False) -> str:
    """
    是什么：_scope_label 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value:
        if datasource_scoped:
            return "platform-managed-project"
        return "platform-generic"
    if visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value:
        return "user-private"
    return "workspace"


def _scope_runtime_notice(
        visibility_scope: str | None,
        prompt_type: str = "Agent",
        datasource_scoped: bool = False,
) -> str:
    """
    是什么：_scope_runtime_notice 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value and datasource_scoped:
        return (
            f"This {prompt_type} is managed at platform level but explicitly scoped to the current datasource. "
            "Use it only when the configured project matches the current datasource context. It cannot expand "
            "datasource access or override schema, permissions, workspace metadata, or SQL safety rules."
        )
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value:
        return (
            f"This {prompt_type} is a platform-level generic capability. Use it only for reusable methods, "
            "answer style, workflow preferences, SQL safety hints, or analysis process guidance. "
            "Do not treat any table name, field name, event name, metric formula, datasource name, "
            "sample value, or business definition inside it as authoritative for the current workspace. "
            "Current workspace schema, workspace Data Skills, workspace metadata, permissions, and user-provided "
            "requirements always override it."
        )
    if visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value:
        return (
            f"This {prompt_type} is a user-private preference for the current workspace context. "
            "It cannot expand datasource access or override schema, permissions, workspace Data Skills, or SQL safety rules."
        )
    return (
        f"This {prompt_type} is scoped to the current workspace and its bound datasource. "
        "Use it only inside the current workspace context, and do not apply it to other workspaces or datasources."
    )


def _source_order_sql(alias: str = "") -> str:
    """
    是什么：_source_order_sql 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    prefix = f"{alias}." if alias else ""
    return (
        "CASE "
        f"WHEN {prefix}visibility_scope = 'PLATFORM_PUBLIC' THEN 0 "
        f"WHEN {prefix}visibility_scope = 'USER_PRIVATE' THEN 2 "
        "ELSE 1 END"
    )


_SKILL_NAME_SCOPE_MARKERS = (
    "analysis assistant",
    "data skill",
    "workspace",
    "platform",
    "personal",
    "private",
    "generic",
    "tenant",
    "saas",
    "skill",
    "工作空间",
    "平台级",
    "平台",
    "个人",
    "私有",
    "租户",
    "通用",
    "技能",
)


def _skill_scope_priority(skill: dict[str, Any]) -> int:
    """
    是什么：_skill_scope_priority 给同类 Skill 的来源排优先级。
    谁调用：运行时自动筛选 Data Skills 时调用。
    做了什么：SaaS 平台 Skill 优先于工作空间 Skill，工作空间 Skill 优先于个人 Skill。
    """
    visibility_scope = skill.get("visibility_scope")
    if visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value:
        return 0
    if visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value:
        return 2
    return 1


def _normalize_skill_name_for_override(name: str | None) -> str:
    """
    是什么：_normalize_skill_name_for_override 把 Skill 名称归一成冲突判断用的 key。
    谁调用：运行时自动筛选 Data Skills 时调用。
    做了什么：去掉常见来源前后缀和标点，让“平台-收入健康度”和“收入健康度”能被识别为同类。
    """
    text = (name or "").strip().lower()
    if not text:
        return ""
    separator = r"[\s_\-—–·:：/\\|]+"
    for _ in range(4):
        previous = text
        for marker in _SKILL_NAME_SCOPE_MARKERS:
            escaped = re.escape(marker)
            if text == marker:
                text = ""
            else:
                text = re.sub(rf"^(?:{escaped})(?:{separator})", "", text).strip()
                text = re.sub(rf"(?:{separator})(?:{escaped})$", "", text).strip()
        if text == previous:
            break
    return re.sub(r"[\s_\-—–·:：/\\|,，.。()（）\[\]【】{}]+", "", text)


def _skill_override_group_key(skill: dict[str, Any]) -> str:
    """
    是什么：_skill_override_group_key 给同名或近似命名的 Skill 分组。
    谁调用：运行时自动筛选 Data Skills 时调用。
    做了什么：名称可归一时按名称分组，否则退回到 id，避免无名称 Skill 被误合并。
    """
    name_key = _normalize_skill_name_for_override(skill.get("name"))
    if name_key:
        return f"name:{name_key}"
    return f"id:{skill.get('id') or ''}"


def _dedupe_overridden_data_skills(skill_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    是什么：_dedupe_overridden_data_skills 处理同类 Data Skill 的覆盖关系。
    谁调用：运行时自动筛选 Data Skills 时调用。
    做了什么：相同或近似 Skill 只保留优先级最高的一条：SaaS > 工作空间 > 个人；同层级里项目限定优先于全项目。
    """
    best_by_key: dict[str, tuple[tuple[int, int, int], int, dict[str, Any]]] = {}
    for index, skill in enumerate(skill_rows):
        key = _skill_override_group_key(skill)
        rank = (
            _skill_scope_priority(skill),
            0 if skill.get("specific_ds") else 1,
            index,
        )
        current = best_by_key.get(key)
        if current is None or rank < current[0]:
            best_by_key[key] = (rank, index, skill)
    return [item[2] for item in sorted(best_by_key.values(), key=lambda item: item[1])]


def _is_split_legacy_data_skill(row) -> bool:
    """
    是什么：_is_split_legacy_data_skill 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    prompt = row.get("prompt") or ""
    return (
        "<!-- data-skill-source:terminology:" in prompt
        or "<!-- data-skill-source:data-training:" in prompt
        or "<!-- data-skill-source:custom-prompt-generate-sql:" in prompt
        or "<!-- data-skill-source:legacy-semantic:" in prompt
        or "<!-- data-skill-source:semantic-theme:saas:" in prompt
        or "<!-- legacy-data-training:" in prompt
        or "<!-- legacy-terminology:" in prompt
        or "<!-- legacy-sql-prompt:" in prompt
    )


def _skill_match_terms(question: str) -> set[str]:
    """
    是什么：_skill_match_terms 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    text = (question or "").lower()
    terms = {item for item in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{1,}", text)}
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    stop_terms = {
        "帮我",
        "分析",
        "一下",
        "这个",
        "这天",
        "情况",
        "数据",
        "看看",
        "是否",
        "怎么",
        "为什么",
    }
    for run in cjk_runs:
        run = re.sub(r"[年月日号天这的了和与及在后前]", "", run)
        if len(run) < 2:
            continue
        max_len = min(6, len(run))
        for size in range(2, max_len + 1):
            for start in range(0, len(run) - size + 1):
                term = run[start:start + size]
                if term not in stop_terms:
                    terms.add(term)
    return terms


def _score_data_skill(skill: dict[str, Any], question: str) -> int:
    """
    是什么：_score_data_skill 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    terms = _skill_match_terms(question)
    if not terms:
        return 0

    name = (skill.get("name") or "").lower()
    description = (skill.get("description") or "").lower()
    prompt = (skill.get("prompt") or "").lower()
    score = 0
    for term in terms:
        lower_term = term.lower()
        if lower_term in name:
            score += 24
        if lower_term in description:
            score += 12
        if lower_term in prompt:
            score += 4
    if question and (name in question.lower() or question.lower() in name):
        score += 40
    return score


def _estimated_skill_chars(skill: dict[str, Any]) -> int:
    """
    是什么：_estimated_skill_chars 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (
        len(skill.get("name") or "")
        + len(skill.get("description") or "")
        + len(skill.get("prompt") or "")
        + 96
    )


def _select_ranked_data_skills(
        scored: list[tuple[float, int, dict[str, Any]]],
        skill_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    是什么：_select_ranked_data_skills 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    positive = [item for item in scored if item[0] > 0]
    if not positive:
        return skill_rows

    # 在保留下游大语言模型调用所需关键信息的同时，尽量压缩提示词长度。
    # 同类 Skill 已在入口按 SaaS > 工作空间 > 个人完成覆盖，这里只按相关性取最合适的一组。
    max_skills = 12
    max_prompt_chars = 18000
    ranked_positive = sorted(positive, key=lambda item: (-item[0], item[1]))
    selected: list[tuple[float, int, dict[str, Any]]] = []
    selected_keys: set[str] = set()
    used_chars = 0

    def skill_key(skill: dict[str, Any]) -> str:
        """
        是什么：skill_key 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 _select_ranked_data_skills 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return str(skill.get("id") or _skill_override_group_key(skill))

    def add_skill(item: tuple[float, int, dict[str, Any]]) -> bool:
        """
        是什么：add_skill 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 _select_ranked_data_skills 跑到对应步骤时会调用它。
        做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
        """
        nonlocal used_chars
        _score, _index, skill = item
        key = skill_key(skill)
        if key in selected_keys:
            return False
        estimated_chars = _estimated_skill_chars(skill)
        if selected and len(selected) >= max_skills:
            return False
        if selected and used_chars + estimated_chars > max_prompt_chars:
            return False
        selected.append(item)
        selected_keys.add(key)
        used_chars += estimated_chars
        return True

    for item in ranked_positive:
        if not add_skill(item):
            if len(selected) >= max_skills:
                break

    selected.sort(key=lambda item: (-item[0], item[1]))
    return [skill for _score, _index, skill in selected] or skill_rows


def _queue_stale_skill_embeddings(skill_rows: list[dict[str, Any]]) -> None:
    """
    是什么：_queue_stale_skill_embeddings 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not settings.EMBEDDING_ENABLED:
        return
    stale_by_tenant: dict[int | None, list[int]] = {}
    for skill in skill_rows:
        expected_signature = skill_definition_signature(
            skill.get("name"),
            skill.get("description"),
            skill.get("prompt"),
        )
        current_signature = skill.get("embedding_signature")
        vector = embedding_vector_from_json(skill.get("embedding"))
        if current_signature == expected_signature and vector is not None:
            continue
        try:
            skill_id = int(skill.get("id"))
        except (TypeError, ValueError):
            continue
        tenant_id = skill.get("tenant_id")
        try:
            tenant_key = int(tenant_id) if tenant_id not in (None, "") else None
        except (TypeError, ValueError):
            tenant_key = None
        stale_by_tenant.setdefault(tenant_key, []).append(skill_id)

    for tenant_id, ids in stale_by_tenant.items():
        if ids:
            run_save_custom_prompt_skill_embeddings(ids[:50], tenant_id=tenant_id)


def _rank_auto_data_skills_by_embedding(
        skill_rows: list[dict[str, Any]],
        question: str | None,
) -> list[dict[str, Any]] | None:
    """
    是什么：_rank_auto_data_skills_by_embedding 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not question or not question.strip() or not settings.EMBEDDING_ENABLED:
        return None

    _queue_stale_skill_embeddings(skill_rows)
    valid_embeddings: list[tuple[int, dict[str, Any], list[float]]] = []
    for index, skill in enumerate(skill_rows):
        expected_signature = skill_definition_signature(
            skill.get("name"),
            skill.get("description"),
            skill.get("prompt"),
        )
        if skill.get("embedding_signature") != expected_signature:
            continue
        vector = embedding_vector_from_json(skill.get("embedding"))
        if vector is None:
            continue
        valid_embeddings.append((index, skill, vector))

    if not valid_embeddings:
        return None

    try:
        query_embedding = EmbeddingModelCache.get_model().embed_query(question)
    except Exception:
        AppLogUtil.exception("Failed to embed question for data skill ranking")
        return None

    threshold = float(settings.EMBEDDING_DEFAULT_SIMILARITY or 0)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, skill, vector in valid_embeddings:
        try:
            similarity = cosine_similarity(query_embedding, vector)
        except Exception:
            continue
        if similarity >= threshold:
            scored.append((float(similarity), index, skill))

    if not scored:
        return None

    embedding_ranked = _select_ranked_data_skills(scored, skill_rows)
    keyword_ranked = _rank_auto_data_skills_by_keyword(skill_rows, question)
    if keyword_ranked == skill_rows:
        return embedding_ranked

    def skill_key(skill: dict[str, Any]) -> str:
        """
        是什么：skill_key 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 _rank_auto_data_skills_by_embedding 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return str(skill.get("id") or _skill_override_group_key(skill))

    keyword_scores = {
        skill_key(skill): _score_data_skill(skill, question or "")
        for skill in keyword_ranked
    }
    max_keyword_score = max(keyword_scores.values(), default=0)
    strong_keyword_threshold = max(80, int(max_keyword_score * 0.6)) if max_keyword_score else 0

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(skill: dict[str, Any]) -> bool:
        """
        是什么：add 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 _rank_auto_data_skills_by_embedding 跑到对应步骤时会调用它。
        做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
        """
        key = skill_key(skill)
        if key in seen:
            return False
        if merged and len(merged) >= 12:
            return False
        merged.append(skill)
        seen.add(key)
        return True

    for skill in embedding_ranked:
        add(skill)
    for skill in keyword_ranked:
        score = keyword_scores.get(skill_key(skill), 0)
        is_workspace_specific = skill.get("visibility_scope") != CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value
        if is_workspace_specific and strong_keyword_threshold and score >= strong_keyword_threshold:
            if add(skill):
                continue
        vector = embedding_vector_from_json(skill.get("embedding"))
        expected_signature = skill_definition_signature(
            skill.get("name"),
            skill.get("description"),
            skill.get("prompt"),
        )
        if skill.get("embedding_signature") == expected_signature and vector is not None:
            continue
        add(skill)
    return merged or embedding_ranked


def _rank_auto_data_skills_by_keyword(skill_rows: list[dict[str, Any]], question: str | None) -> list[dict[str, Any]]:
    """
    是什么：_rank_auto_data_skills_by_keyword 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not question or not question.strip():
        return skill_rows

    scored: list[tuple[int, int, dict[str, Any]]] = [
        (_score_data_skill(skill, question), index, skill)
        for index, skill in enumerate(skill_rows)
    ]
    return _select_ranked_data_skills(scored, skill_rows)


def _rank_auto_data_skills(skill_rows: list[dict[str, Any]], question: str | None) -> list[dict[str, Any]]:
    """
    是什么：_rank_auto_data_skills 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    skill_rows = _dedupe_overridden_data_skills(skill_rows)
    embedding_ranked = _rank_auto_data_skills_by_embedding(skill_rows, question)
    if embedding_ranked is not None:
        return embedding_ranked
    return _rank_auto_data_skills_by_keyword(skill_rows, question)


def find_custom_prompts(
        session: Session,
        custom_prompt_type: Optional[CustomPromptTypeEnum] = None,
        datasource: Optional[int] = None,
        target_scope: Optional[CustomPromptTargetScopeEnum | str] = CustomPromptTargetScopeEnum.SMART_QA,
        prompt_id: Optional[int | str] = None,
        current_user_id: Optional[int | str] = None,
        can_manage_all: bool = False,
        tenant_id: Optional[int | str] = None,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
) -> tuple[str, list[str], Optional[int]]:
    """
    是什么：find_custom_prompts 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    normalized_prompt_id = _normalize_prompt_id(prompt_id)
    if normalized_prompt_id is None:
        return "", [], None

    normalized_scope = _normalize_target_scope(target_scope)
    type_condition = ""
    params = {
        "prompt_id": normalized_prompt_id,
        "tenant_id": require_tenant_id(tenant_id),
        "target_scope": normalized_scope.value,
        "all_scope": CustomPromptTargetScopeEnum.ALL.value,
        "smart_qa_scope": CustomPromptTargetScopeEnum.SMART_QA.value,
        "current_user_id": int(current_user_id) if current_user_id not in (None, "") else None,
        "platform_scope": CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value,
        "public_scope": CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value,
        "private_scope": CustomPromptVisibilityScopeEnum.USER_PRIVATE.value,
        "can_manage_public": bool(can_manage_public or can_manage_all),
        "can_manage_platform_public": bool(can_manage_platform_public),
    }
    if custom_prompt_type is not None:
        type_condition = "AND type = :custom_prompt_type"
        params["custom_prompt_type"] = custom_prompt_type.value

    rows = session.execute(
        sql_text(
            f"""
            SELECT id, name, description, prompt, specific_ds, datasource_ids, ai_model_id, create_by, visibility_scope
            FROM custom_prompt
            WHERE id = :prompt_id
              {type_condition}
              AND COALESCE(active, false) = true
              AND (
                (
                  visibility_scope = :platform_scope
                  AND (:can_manage_platform_public OR COALESCE(visible, true) = true)
                )
                OR
                (
                  COALESCE(visibility_scope, :public_scope) = :public_scope
                  AND tenant_id = :tenant_id
                  AND (:can_manage_public OR COALESCE(visible, true) = true)
                )
                OR (visibility_scope = :private_scope AND create_by = :current_user_id)
              )
              AND (
                target_scope = :target_scope
                OR target_scope = :all_scope
                OR (target_scope IS NULL AND :target_scope = :smart_qa_scope)
              )
            ORDER BY {_source_order_sql()}, create_time DESC, id DESC
            """
        ),
        params,
    ).mappings().all()

    agent_list: list[dict[str, str]] = []
    ai_model_id: Optional[int] = None
    for row in rows:
        visibility_scope = row.get("visibility_scope") or CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value
        if visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value:
            if current_user_id is None or str(row.get("create_by")) != str(current_user_id):
                continue

        prompt = row.get("prompt")
        if not prompt:
            continue
        agent = {
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "system_prompt": prompt,
            "visibility_scope": visibility_scope,
            "specific_ds": bool(row.get("specific_ds")),
        }
        if _row_matches_datasource(row, datasource):
            agent_list.append(agent)
            ai_model_id = row.get("ai_model_id")

    if not agent_list:
        return "", [], None

    content = "<Other-Infos>\n"
    for agent in agent_list:
        content += "\t<agent>\n"
        datasource_scoped = bool(agent.get("specific_ds"))
        content += f"\t\t<scope>{_scope_label(agent['visibility_scope'], datasource_scoped)}</scope>\n"
        content += f"\t\t<runtime-constraint>{_xml_text(_scope_runtime_notice(agent['visibility_scope'], datasource_scoped=datasource_scoped))}</runtime-constraint>\n"
        content += f"\t\t<name>{_xml_text(agent['name'])}</name>\n"
        if agent["description"]:
            content += f"\t\t<description>{_xml_text(agent['description'])}</description>\n"
        content += f"\t\t<supplemental-prompt>{_xml_text(agent['system_prompt'])}</supplemental-prompt>\n"
        content += "\t</agent>\n"
    content += "</Other-Infos>\n"
    prompt_list = [
        _prompt_log_text(agent["name"], agent["description"], agent["system_prompt"])
        for agent in agent_list
    ]
    return content, prompt_list, ai_model_id


def find_data_skills(
        session: Session,
        datasource: Optional[int] = None,
        target_scope: Optional[CustomPromptTargetScopeEnum | str] = CustomPromptTargetScopeEnum.SMART_QA,
        skill_id: Optional[int | str] = None,
        current_user_id: Optional[int | str] = None,
        can_manage_all: bool = False,
        tenant_id: Optional[int | str] = None,
        question: Optional[str] = None,
        include_all_target_scopes: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
) -> tuple[str, list[str], Optional[int]]:
    """
    是什么：find_data_skills 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent需要的数据找出来，整理成后面好用的样子。
    """
    normalized_skill_id = _normalize_prompt_id(skill_id)
    normalized_scope = _normalize_target_scope(target_scope)
    target_scope_condition = ""
    if not include_all_target_scopes:
        target_scope_condition = """
              AND (
                target_scope = :target_scope
                OR target_scope = :all_scope
                OR (target_scope IS NULL AND :target_scope = :smart_qa_scope)
              )
        """
    params = {
        "custom_prompt_type": CustomPromptTypeEnum.DATA_SKILL.value,
        "tenant_id": require_tenant_id(tenant_id),
        "target_scope": normalized_scope.value,
        "all_scope": CustomPromptTargetScopeEnum.ALL.value,
        "smart_qa_scope": CustomPromptTargetScopeEnum.SMART_QA.value,
        "current_user_id": int(current_user_id) if current_user_id not in (None, "") else None,
        "platform_scope": CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value,
        "public_scope": CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value,
        "private_scope": CustomPromptVisibilityScopeEnum.USER_PRIVATE.value,
        "disabled_pref": False,
        "can_manage_public": bool(can_manage_public or can_manage_all),
        "can_manage_platform_public": bool(can_manage_platform_public),
    }

    rows = session.execute(
        sql_text(
            f"""
            SELECT id, tenant_id, name, description, prompt, embedding, embedding_signature,
                   specific_ds, datasource_ids, ai_model_id, create_by, visibility_scope
            FROM custom_prompt
            WHERE 1 = 1
              AND type = :custom_prompt_type
              AND COALESCE(active, false) = true
              AND (
                (
                  visibility_scope = :platform_scope
                  AND (:can_manage_platform_public OR COALESCE(visible, true) = true)
                )
                OR
                (
                  COALESCE(visibility_scope, :public_scope) = :public_scope
                  AND tenant_id = :tenant_id
                  AND (:can_manage_public OR COALESCE(visible, true) = true)
                )
                OR (visibility_scope = :private_scope AND create_by = :current_user_id)
              )
              {target_scope_condition}
              AND (
                :current_user_id IS NULL
                OR NOT EXISTS (
                  SELECT 1
                  FROM custom_prompt_user_preference AS pref
                  WHERE pref.custom_prompt_id = custom_prompt.id
                    AND pref.user_id = :current_user_id
                    AND pref.enabled = :disabled_pref
                )
              )
            ORDER BY {_source_order_sql()}, create_time DESC, id DESC
            """
        ),
        params,
    ).mappings().all()

    skill_rows: list[dict[str, Any]] = []
    ai_model_id: Optional[int] = None
    for row in rows:
        if _is_split_legacy_data_skill(row):
            continue

        visibility_scope = row.get("visibility_scope") or CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value
        if visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value:
            if current_user_id is None or str(row.get("create_by")) != str(current_user_id):
                continue

        prompt = row.get("prompt")
        if not prompt:
            continue
        if not _row_matches_datasource(row, datasource):
            continue
        skill_rows.append({
            "id": str(row.get("id") or ""),
            "tenant_id": row.get("tenant_id"),
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "prompt": prompt,
            "embedding": row.get("embedding"),
            "embedding_signature": row.get("embedding_signature"),
            "visibility_scope": visibility_scope,
            "specific_ds": bool(row.get("specific_ds")),
            "ai_model_id": row.get("ai_model_id"),
        })
        ai_model_id = row.get("ai_model_id")

    if normalized_skill_id is None:
        skill_rows = _rank_auto_data_skills(skill_rows, question)
    else:
        selected_skill = next(
            (skill for skill in skill_rows if str(skill.get("id")) == str(normalized_skill_id)),
            None,
        )
        if selected_skill is None:
            return "", [], None
        selected_key = _skill_override_group_key(selected_skill)
        skill_rows = _dedupe_overridden_data_skills(
            [skill for skill in skill_rows if _skill_override_group_key(skill) == selected_key]
        )

    if not skill_rows:
        return "", [], None
    ai_model_id = next((skill.get("ai_model_id") for skill in skill_rows if skill.get("ai_model_id")), ai_model_id)

    content_parts = [
        "<Data-Skills>",
        "以下是本次自动匹配或用户指定的数据 Skill。Skill 以 Markdown/自然语言描述业务口径、查询范式、示例 SQL、"
        "图表偏好或注意事项。生成 SQL、解释结果和组织分析时必须优先参考它；如果它与数据库 Schema、"
        "数据权限、SQL 安全规则或当前已选数据源冲突，必须以 SaaS 规则和当前权限为准。",
        "未限定项目的平台级 Skill 只代表通用能力或通用方法论，不能作为当前工作空间的表名、字段名、事件名、指标口径或业务枚举来源；"
        "项目限定的平台管理 Skill、当前工作空间级 Skill 或用户私有 Skill 可以沉淀当前项目上下文，且仍必须受当前 Schema 与权限约束。",
    ]
    for skill in skill_rows:
        content_parts.append("\n---")
        content_parts.append(f"## {skill['name']}")
        datasource_scoped = bool(skill.get("specific_ds"))
        content_parts.append(f"\n作用域：{_scope_label(skill['visibility_scope'], datasource_scoped)}")
        content_parts.append(
            f"\n约束：{_scope_runtime_notice(skill['visibility_scope'], prompt_type='Data Skill', datasource_scoped=datasource_scoped)}"
        )
        if skill["description"]:
            content_parts.append(f"\n描述：{skill['description']}")
        content_parts.append("")
        content_parts.append(skill["prompt"])
    content_parts.append("</Data-Skills>\n")
    skill_text = "\n".join(content_parts)
    skill_list = [
        _prompt_log_text(skill["name"], skill["description"], skill["prompt"], label="Skill 内容")
        for skill in skill_rows
    ]
    return skill_text, skill_list, ai_model_id
