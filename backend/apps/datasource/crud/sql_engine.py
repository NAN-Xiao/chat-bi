"""
脚本说明：SQL Engine 统一封装业务库 SQL 上下文构建和 SQL 执行入口。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from fastapi import HTTPException

from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum, find_data_skills
from apps.datasource.crud.permission import has_datasource_access
from apps.datasource.crud.sql_engine_executor import (
    QueryExecutionResult,
    SqlEngineResult,
    UnresolvedDashboardDateParametersError,
    execute_external_user_query_or_raise,
    execute_user_analysis_query_or_raise,
    execute_user_query,
    execute_user_query_or_raise,
    looks_like_data_unavailable_error,
    prepare_query_sql,
    safe_query_error_message,
    safe_query_error_type,
    user_data_unavailable_message,
    validate_user_query_sql_or_raise,
    wrap_external_subquery_with_table_rule,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import get_sqlglot_dialect
from apps.system.crud.tracking_config import find_tracking_prompt_context
from common.core.deps import CurrentUser, SessionDep


BUSINESS_SQL_CONTEXT_UNAVAILABLE_MESSAGE = (
    "当前数据源无法建立所选工作空间的业务上下文，请重新选择已绑定且有权限的数据源。"
)


def _stable_digest(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_ai_table_schema(*args, **kwargs):
    """
    是什么：延迟导入 AI schema 构建函数，避免 SQL Engine 与 datasource CRUD 循环导入。
    """
    from apps.datasource.crud.datasource import get_ai_table_schema as _get_ai_table_schema

    return _get_ai_table_schema(*args, **kwargs)


@dataclass
class BusinessSqlContext:
    """
    类说明：BusinessSqlContext 是 Agent 生成 SQL 前使用的统一业务库上下文。
    """
    tenant_id: int | None
    datasource_id: int
    target_scope: str
    datasource: CoreDatasource
    datasource_type: str | None
    sql_dialect: str | None
    schema: str
    allowed_tables: list[str]
    data_skill: str = ""
    data_skill_list: list[str] = field(default_factory=list)
    skill_model_id: int | None = None
    tracking_config: str = ""
    tracking_summary: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    business_context_hash: str | None = None

    @property
    def semantic_context(self) -> str:
        return "\n\n".join(
            part.strip()
            for part in (self.tracking_config, self.data_skill)
            if part and part.strip()
        )

    def snapshot_metadata(self) -> dict[str, Any]:
        return {
            "context_hash": self.business_context_hash,
            "tenant_id": str(self.tenant_id) if self.tenant_id is not None else None,
            "datasource_id": str(self.datasource_id),
            "datasource_type": self.datasource_type,
            "sql_dialect": self.sql_dialect,
            "target_scope": self.target_scope,
            "allowed_tables": list(self.allowed_tables or []),
            "tracking_warnings": list(self.warnings or []),
            "tracking_summary_count": len(self.tracking_summary or []),
            "data_skill_count": len(self.data_skill_list or []),
            "data_skill_list_sha256": _stable_digest(self.data_skill_list),
            "data_skill_model_id": str(self.skill_model_id) if self.skill_model_id is not None else None,
        }


class BusinessSqlContextService:
    """
    类说明：BusinessSqlContextService 统一构建当前业务库的 SQL 生成上下文。
    """

    @staticmethod
    def build(
        *,
        session: SessionDep,
        current_user: CurrentUser,
        tenant_id: int | None,
        datasource_id: int,
        question: str | None = None,
        target_scope: CustomPromptTargetScopeEnum | str = CustomPromptTargetScopeEnum.SMART_QA,
        data_skill_id: int | str | None = None,
        include_all_target_scopes: bool = False,
        embedding: bool = True,
        table_list: list[str] | None = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
    ) -> BusinessSqlContext:
        """
        是什么：构建 Agent 生成 SQL 需要的唯一业务库上下文。
        做了什么：确认当前数据源、读取 AI schema、数据字典、Data Skills 和 SQL 方言。
        """
        datasource = session.get(CoreDatasource, int(datasource_id))
        if datasource is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        if not has_datasource_access(session, current_user, int(datasource_id)):
            raise HTTPException(status_code=403, detail=f"当前用户无权访问项目 {datasource_id}")
        datasource_type = getattr(datasource, "type", None) or getattr(datasource, "type_name", None)
        sql_dialect = get_sqlglot_dialect(datasource_type)

        data_skill, skill_list, skill_model_id = find_data_skills(
            session,
            int(datasource_id),
            target_scope,
            data_skill_id,
            getattr(current_user, "id", None),
            can_manage_all,
            tenant_id,
            question=question,
            include_all_target_scopes=include_all_target_scopes,
            can_manage_public=can_manage_public,
            can_manage_platform_public=can_manage_platform_public,
            current_user=current_user,
        )
        schema, allowed_tables = get_ai_table_schema(
            session=session,
            current_user=current_user,
            ds=datasource,
            question=question or "",
            embedding=embedding,
            table_list=table_list,
            data_skill_text=data_skill,
            tenant_id=tenant_id,
        )
        tracking_config, tracking_summary = find_tracking_prompt_context(
            session,
            tenant_id,
            int(datasource_id),
            datasource_type=datasource_type,
            question=question,
            data_skill_text=data_skill,
        )
        warnings = [
            item[len("schema校验: ") :]
            for item in (tracking_summary or [])
            if isinstance(item, str) and item.startswith("schema校验: ")
        ]
        context_hash = _stable_digest(
            {
                "tenant_id": tenant_id,
                "datasource_id": int(datasource_id),
                "datasource_type": datasource_type,
                "sql_dialect": sql_dialect,
                "schema": schema,
                "allowed_tables": allowed_tables or [],
                "data_skill": data_skill or "",
                "tracking_config": tracking_config or "",
            }
        )
        return BusinessSqlContext(
            tenant_id=int(tenant_id) if tenant_id is not None else None,
            datasource_id=int(datasource_id),
            target_scope=target_scope.value if isinstance(target_scope, CustomPromptTargetScopeEnum) else str(target_scope),
            datasource=datasource,
            datasource_type=datasource_type,
            sql_dialect=sql_dialect,
            schema=schema,
            allowed_tables=list(allowed_tables or []),
            data_skill=data_skill or "",
            data_skill_list=list(skill_list or []),
            skill_model_id=int(skill_model_id) if skill_model_id is not None else None,
            tracking_config=tracking_config or "",
            tracking_summary=list(tracking_summary or []),
            warnings=warnings,
            business_context_hash=context_hash,
        )


__all__ = [
    "BusinessSqlContext",
    "BusinessSqlContextService",
    "QueryExecutionResult",
    "SqlEngineResult",
    "UnresolvedDashboardDateParametersError",
    "execute_external_user_query_or_raise",
    "execute_user_analysis_query_or_raise",
    "execute_user_query",
    "execute_user_query_or_raise",
    "looks_like_data_unavailable_error",
    "prepare_query_sql",
    "safe_query_error_message",
    "safe_query_error_type",
    "user_data_unavailable_message",
    "validate_user_query_sql_or_raise",
    "wrap_external_subquery_with_table_rule",
]
