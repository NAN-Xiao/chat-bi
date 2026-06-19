from dataclasses import dataclass
from typing import Optional

import traceback

from sqlmodel import Session

from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    find_custom_prompts,
)
from apps.data_training.curd.data_training import get_training_template
from apps.datasource.crud.datasource import get_datasource_list
from apps.datasource.crud.permission import has_datasource_access
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.user import is_system_admin
from apps.terminology.curd.terminology import get_terminology_template
from common.core.deps import CurrentUser


@dataclass
class ResolvedDatasourceContext:
    datasource: CoreDatasource


def resolve_datasource_context(
    session: Session,
    current_user: CurrentUser,
    datasource_id: Optional[int] = None,
    *,
    require_explicit_when_multiple: bool = True,
) -> ResolvedDatasourceContext:
    if datasource_id is not None:
        try:
            normalized_datasource_id = int(datasource_id)
        except (TypeError, ValueError):
            raise RuntimeError("项目 ID 无效")
        datasource = session.get(CoreDatasource, normalized_datasource_id)
        if not datasource or not has_datasource_access(session, current_user, normalized_datasource_id):
            raise RuntimeError("当前用户无权访问该项目，或项目不存在")
        return ResolvedDatasourceContext(datasource=CoreDatasource(**datasource.model_dump()))

    datasource_list = get_datasource_list(session=session, user=current_user)
    if not datasource_list:
        raise RuntimeError("当前没有可用项目，请联系管理员创建或分配项目")
    if require_explicit_when_multiple and len(datasource_list) > 1:
        raise RuntimeError("当前有多个项目，请先选择本次要使用的项目")
    datasource = datasource_list[0]
    return ResolvedDatasourceContext(datasource=CoreDatasource(**datasource.model_dump()))


def ensure_request_datasource_matches_chat(
    session: Session,
    current_user: CurrentUser,
    chat,
    datasource_id: Optional[int | str],
) -> Optional[int]:
    if datasource_id in (None, ""):
        return None
    try:
        request_datasource_id = int(datasource_id)
    except (TypeError, ValueError):
        raise RuntimeError("项目 ID 无效")

    if not has_datasource_access(session, current_user, request_datasource_id):
        raise RuntimeError("当前用户无权访问该项目，或项目不存在")

    chat_datasource_id = getattr(chat, "datasource", None)
    if chat_datasource_id and int(chat_datasource_id) != request_datasource_id:
        raise RuntimeError("当前对话不属于所选项目，请切换到对应项目后重新提问")
    return request_datasource_id


def collect_terminology_context(
    session: Session,
    datasource_id: Optional[int],
    question: str,
) -> tuple[str, list[dict]]:
    try:
        terminology_template, terms = get_terminology_template(session, question, datasource_id)
        if terminology_template and terminology_template.strip():
            return terminology_template.strip(), terms
        return "", terms
    except Exception:
        traceback.print_exc()
        return "", []


def collect_training_context(
    session: Session,
    datasource_id: Optional[int],
    question: str,
    *,
    advanced_application_id: Optional[int] = None,
) -> tuple[str, list[dict]]:
    try:
        training_template, examples = get_training_template(
            session,
            question,
            datasource_id,
            advanced_application_id,
        )
        if training_template and training_template.strip():
            return training_template.strip(), examples
        return "", examples
    except Exception:
        traceback.print_exc()
        return "", []


def collect_metric_knowledge(
    session: Session,
    datasource_id: Optional[int],
    question: str,
    *,
    advanced_application_id: Optional[int] = None,
) -> tuple[str, list[dict], list[dict]]:
    parts: list[str] = []
    terminology_template, terms = collect_terminology_context(session, datasource_id, question)
    training_template, examples = collect_training_context(
        session,
        datasource_id,
        question,
        advanced_application_id=advanced_application_id,
    )
    if terminology_template:
        parts.append(terminology_template)
    if training_template:
        parts.append(training_template)
    return "\n\n".join(parts), terms, examples


def collect_custom_agent_context(
    session: Session,
    datasource_id: Optional[int],
    custom_prompt_id: Optional[int | str],
    current_user: CurrentUser | None,
    *,
    target_scope: CustomPromptTargetScopeEnum,
    custom_prompt_type: Optional[CustomPromptTypeEnum] = None,
) -> tuple[str, list[str], Optional[int]]:
    if not custom_prompt_id:
        return "", [], None
    try:
        prompt_text, prompt_list, ai_model_id = find_custom_prompts(
            session,
            custom_prompt_type,
            datasource_id,
            target_scope,
            custom_prompt_id,
            getattr(current_user, "id", None),
            is_system_admin(current_user),
        )
        return prompt_text.strip(), prompt_list, ai_model_id
    except Exception:
        traceback.print_exc()
        return "", [], None
