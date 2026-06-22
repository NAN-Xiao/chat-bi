import json
from enum import Enum
from typing import Optional

from sqlalchemy import text as sql_text
from sqlmodel import Session

from apps.system.schemas.access_context import require_tenant_id


class CustomPromptTypeEnum(str, Enum):
    GENERATE_SQL = "GENERATE_SQL"
    ANALYSIS = "ANALYSIS"
    PREDICT_DATA = "PREDICT_DATA"
    DATA_SKILL = "DATA_SKILL"


class CustomPromptTargetScopeEnum(str, Enum):
    SMART_QA = "SMART_QA"
    ANALYSIS_ASSISTANT = "ANALYSIS_ASSISTANT"
    ALL = "ALL"


class CustomPromptVisibilityScopeEnum(str, Enum):
    PLATFORM_PUBLIC = "PLATFORM_PUBLIC"
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


def _datasource_id_values(value) -> list[str]:
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


def _prompt_log_text(name: str, description: str, system_prompt: str, label: str = "补充提示词") -> str:
    parts = [f"名称：{name}"]
    if description:
        parts.append(f"描述：{description}")
    parts.append(f"{label}：{system_prompt}")
    return "\n".join(parts)


def _source_order_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        "CASE "
        f"WHEN {prefix}visibility_scope = 'PLATFORM_PUBLIC' THEN 0 "
        f"WHEN {prefix}visibility_scope = 'USER_PRIVATE' THEN 2 "
        "ELSE 1 END"
    )


def _is_split_legacy_data_skill(row) -> bool:
    prompt = row.get("prompt") or ""
    return (
        "<!-- data-skill-source:terminology:" in prompt
        or "<!-- data-skill-source:data-training:" in prompt
        or "<!-- data-skill-source:custom-prompt-generate-sql:" in prompt
        or "<!-- data-skill-source:legacy-semantic:" in prompt
        or "<!-- data-skill-source:semantic-theme:saas:" in prompt
    )


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
        "tenant_id": require_tenant_id(tenant_id),
        "target_scope": normalized_scope.value,
        "all_scope": CustomPromptTargetScopeEnum.ALL.value,
        "smart_qa_scope": CustomPromptTargetScopeEnum.SMART_QA.value,
        "current_user_id": int(current_user_id) if current_user_id not in (None, "") else None,
        "platform_scope": CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value,
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
                visibility_scope = :platform_scope
                OR
                (COALESCE(visibility_scope, :public_scope) = :public_scope AND tenant_id = :tenant_id)
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
) -> tuple[str, list[str], Optional[int]]:
    normalized_skill_id = _normalize_prompt_id(skill_id)
    normalized_scope = _normalize_target_scope(target_scope)
    skill_condition = "AND id = :skill_id" if normalized_skill_id is not None else ""
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
    }
    if normalized_skill_id is not None:
        params["skill_id"] = normalized_skill_id

    rows = session.execute(
        sql_text(
            f"""
            SELECT name, description, prompt, specific_ds, datasource_ids, ai_model_id, create_by, visibility_scope
            FROM custom_prompt
            WHERE 1 = 1
              {skill_condition}
              AND type = :custom_prompt_type
              AND COALESCE(active, false) = true
              AND (
                visibility_scope = :platform_scope
                OR
                (COALESCE(visibility_scope, :public_scope) = :public_scope AND tenant_id = :tenant_id)
                OR (visibility_scope = :private_scope AND create_by = :current_user_id)
              )
              AND (
                target_scope = :target_scope
                OR target_scope = :all_scope
                OR (target_scope IS NULL AND :target_scope = :smart_qa_scope)
              )
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

    skill_rows: list[dict[str, str]] = []
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
        if row.get("specific_ds"):
            if datasource is None:
                continue
            if str(datasource) not in _datasource_id_values(row.get("datasource_ids")):
                continue
        skill_rows.append({
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "prompt": prompt,
        })
        ai_model_id = row.get("ai_model_id")

    if not skill_rows:
        return "", [], None

    content_parts = [
        "<Data-Skills>",
        "以下是本次自动匹配或用户指定的数据 Skill。Skill 以 Markdown/自然语言描述业务口径、查询范式、示例 SQL、"
        "图表偏好或注意事项。生成 SQL、解释结果和组织分析时必须优先参考它；如果它与数据库 Schema、"
        "数据权限、SQL 安全规则或当前已选数据源冲突，必须以 SaaS 规则和当前权限为准。",
    ]
    for skill in skill_rows:
        content_parts.append("\n---")
        content_parts.append(f"## {skill['name']}")
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
