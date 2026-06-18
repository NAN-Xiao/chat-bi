from enum import Enum
from typing import Optional

from sqlalchemy import text as sql_text
from sqlmodel import Session

from apps.system.crud.tenant import DEFAULT_TENANT_ID


class CustomPromptTypeEnum(str, Enum):
    GENERATE_SQL = "GENERATE_SQL"
    ANALYSIS = "ANALYSIS"
    PREDICT_DATA = "PREDICT_DATA"


class CustomPromptTargetScopeEnum(str, Enum):
    SMART_QA = "SMART_QA"
    ANALYSIS_ASSISTANT = "ANALYSIS_ASSISTANT"
    ALL = "ALL"


class CustomPromptVisibilityScopeEnum(str, Enum):
    ADMIN_PUBLIC = "ADMIN_PUBLIC"
    USER_PRIVATE = "USER_PRIVATE"


def _normalize_prompt_id(prompt_id: Optional[int | str]) -> Optional[int]:
    if prompt_id in (None, ""):
        return None
    try:
        return int(prompt_id)
    except (TypeError, ValueError):
        return None


def _normalize_target_scope(
        target_scope: Optional[CustomPromptTargetScopeEnum | str],
) -> CustomPromptTargetScopeEnum:
    if isinstance(target_scope, CustomPromptTargetScopeEnum):
        return target_scope
    try:
        return CustomPromptTargetScopeEnum(str(target_scope))
    except ValueError:
        return CustomPromptTargetScopeEnum.SMART_QA


def _xml_text(value: Optional[str]) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _agent_log_text(name: str, description: str, system_prompt: str) -> str:
    parts = [f"名称：{name}"]
    if description:
        parts.append(f"描述：{description}")
    parts.append(f"补充提示词：{system_prompt}")
    return "\n".join(parts)


def find_custom_prompts(
        session: Session,
        custom_prompt_type: Optional[CustomPromptTypeEnum] = None,
        datasource: Optional[int] = None,
        target_scope: Optional[CustomPromptTargetScopeEnum | str] = CustomPromptTargetScopeEnum.SMART_QA,
        prompt_id: Optional[int | str] = None,
        current_user_id: Optional[int | str] = None,
        can_manage_all: bool = False,
        tenant_id: Optional[int | str] = None,
) -> tuple[str, list[str], Optional[int]]:
    normalized_prompt_id = _normalize_prompt_id(prompt_id)
    if normalized_prompt_id is None:
        return "", [], None

    normalized_scope = _normalize_target_scope(target_scope)
    type_condition = ""
    params = {
        "prompt_id": normalized_prompt_id,
        "tenant_id": int(tenant_id or DEFAULT_TENANT_ID),
        "target_scope": normalized_scope.value,
        "all_scope": CustomPromptTargetScopeEnum.ALL.value,
        "smart_qa_scope": CustomPromptTargetScopeEnum.SMART_QA.value,
        "current_user_id": int(current_user_id) if current_user_id not in (None, "") else None,
        "public_scope": CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value,
        "private_scope": CustomPromptVisibilityScopeEnum.USER_PRIVATE.value,
    }
    if custom_prompt_type is not None:
        type_condition = "AND type = :custom_prompt_type"
        params["custom_prompt_type"] = custom_prompt_type.value

    rows = session.execute(
        sql_text(
            f"""
            SELECT name, description, prompt, specific_ds, datasource_ids, ai_model_id, create_by, visibility_scope
            FROM custom_prompt
            WHERE id = :prompt_id
              {type_condition}
              AND COALESCE(active, false) = true
              AND (
                (COALESCE(visibility_scope, :public_scope) = :public_scope AND tenant_id = :tenant_id)
                OR (visibility_scope = :private_scope AND create_by = :current_user_id)
              )
              AND (
                target_scope = :target_scope
                OR target_scope = :all_scope
                OR (target_scope IS NULL AND :target_scope = :smart_qa_scope)
              )
            ORDER BY create_time, id
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
        }
        if not row.get("specific_ds"):
            agent_list.append(agent)
            ai_model_id = row.get("ai_model_id")
            continue
        if datasource is None:
            continue
        datasource_ids = row.get("datasource_ids") or []
        if any(str(item) == str(datasource) for item in datasource_ids):
            agent_list.append(agent)
            ai_model_id = row.get("ai_model_id")

    if not agent_list:
        return "", [], None

    content = "<Other-Infos>\n"
    for agent in agent_list:
        content += "\t<agent>\n"
        content += f"\t\t<name>{_xml_text(agent['name'])}</name>\n"
        if agent["description"]:
            content += f"\t\t<description>{_xml_text(agent['description'])}</description>\n"
        content += f"\t\t<supplemental-prompt>{_xml_text(agent['system_prompt'])}</supplemental-prompt>\n"
        content += "\t</agent>\n"
    content += "</Other-Infos>\n"
    prompt_list = [
        _agent_log_text(agent["name"], agent["description"], agent["system_prompt"])
        for agent in agent_list
    ]
    return content, prompt_list, ai_model_id
