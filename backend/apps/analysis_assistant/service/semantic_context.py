"""Analysis assistant adapter for the shared permission-safe semantic context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum
from apps.datasource.crud.sql_engine import BusinessSqlContext, BusinessSqlContextService


@dataclass(frozen=True)
class AnalysisSemanticContext:
    """Immutable view used by an analysis request after context construction."""

    business_context: BusinessSqlContext
    prompt_text: str
    snapshot: dict[str, Any]


class AnalysisSemanticContextAdapter:
    """Keep analysis routes on the same context builder as SQL surfaces."""

    @staticmethod
    def build(
        *,
        session,
        current_user,
        tenant_id: int,
        datasource_id: int,
        question: str,
        data_skill_id: int | None,
        target_scope: CustomPromptTargetScopeEnum,
        context_service: Callable[..., BusinessSqlContext] = BusinessSqlContextService.build,
    ) -> AnalysisSemanticContext:
        business_context = context_service(
            session=session,
            current_user=current_user,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            question=question,
            target_scope=target_scope,
            data_skill_id=data_skill_id,
            include_all_target_scopes=False,
            embedding=False,
        )
        return AnalysisSemanticContext(
            business_context=business_context,
            prompt_text=business_context.semantic_context,
            snapshot=business_context.snapshot_metadata(),
        )


__all__ = ["AnalysisSemanticContext", "AnalysisSemanticContextAdapter"]
