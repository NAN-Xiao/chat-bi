"""Build one immutable semantic context for every AI surface."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum, find_data_skills
from apps.chat.curd.skill_object_references import eligible_data_skill_ids
from apps.datasource.crud.permission import has_datasource_access
from apps.datasource.crud.permission_scope import (
    PermissionScopeService,
    PermissionScopeSnapshot,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import get_sqlglot_dialect
from apps.knowledge_base.audit import (
    new_request_id,
    write_retrieval_audit,
    write_semantic_context_audit,
)
from apps.knowledge_base.retrieval import KnowledgeCitation, KnowledgeRetrievalService
from apps.knowledge_base.structured_context import StructuredKnowledgeContextService
from apps.system.crud.tracking_config import find_tracking_prompt_context
from common.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectedSkillSnapshot:
    skill_id: int
    selection_mode: str
    source_hash: str | None = None


@dataclass
class BusinessSemanticContext:
    permission_snapshot: PermissionScopeSnapshot
    selected_skills: list[SelectedSkillSnapshot] = field(default_factory=list)
    skill_text: str = ""
    skill_selection_hash: str | None = None
    tracking_config: str = ""
    tracking_summary: list[str] = field(default_factory=list)
    structured_context: str = ""
    knowledge_context: str = ""
    knowledge_citations: list[KnowledgeCitation] = field(default_factory=list)
    knowledge_version_hash: str | None = None
    retrieval_failure_type: str | None = None
    warnings: list[str] = field(default_factory=list)
    context_hash: str | None = None

    @property
    def semantic_text(self) -> str:
        return "\n\n".join(
            part.strip()
            for part in (self.tracking_config, self.skill_text, self.structured_context, self.knowledge_context)
            if part and part.strip()
        )

    def snapshot_metadata(self) -> dict[str, Any]:
        return {
            "context_hash": self.context_hash,
            "permission_version": self.permission_snapshot.permission_version,
            "schema_hash": self.permission_snapshot.schema_hash,
            "skill_selection_hash": self.skill_selection_hash,
            "selected_skills": [
                {
                    "id": str(item.skill_id),
                    "selection_mode": item.selection_mode,
                    "source_hash": item.source_hash,
                }
                for item in self.selected_skills
            ],
            "knowledge_version_hash": self.knowledge_version_hash,
            "retrieval_failure_type": self.retrieval_failure_type,
            "structured_context_hash": _digest(self.structured_context),
            "knowledge_citations": [
                _citation_summary(item) for item in self.knowledge_citations
            ],
            "warnings": list(self.warnings),
        }


class BusinessSemanticContextService:
    """Permission-first composition around existing Skill and tracking authorities."""

    @classmethod
    def build(
        cls,
        *,
        session,
        current_user,
        tenant_id: int,
        datasource_id: int,
        question: str | None = None,
        surface: str = "SMART_QA",
        target_scope: CustomPromptTargetScopeEnum | str = CustomPromptTargetScopeEnum.SMART_QA,
        data_skill_id: int | str | None = None,
        include_all_target_scopes: bool = False,
        embedding: bool = True,
        table_list: list[str] | None = None,
        can_manage_all: bool = False,
        can_manage_public: bool = False,
        can_manage_platform_public: bool = False,
        permission_snapshot: PermissionScopeSnapshot | None = None,
        datasource: CoreDatasource | None = None,
        schema: str | None = None,
        allowed_tables: list[str] | None = None,
        schema_loader: Callable[..., tuple[str, list[str]]] | None = None,
        tracking_loader: Callable[..., tuple[str, list[str]]] | None = None,
        structured_loader: Callable[..., Any] | None = None,
        retrieval_service: KnowledgeRetrievalService | None = None,
        audit_writer: Callable[..., Any] | None = None,
        request_id: str | None = None,
    ) -> SemanticBuildResult:
        datasource = datasource or session.get(CoreDatasource, int(datasource_id))
        if datasource is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        if not has_datasource_access(session, current_user, int(datasource_id)):
            raise HTTPException(status_code=403, detail=f"当前用户无权访问项目 {datasource_id}")
        datasource_type = getattr(datasource, "type", None) or getattr(datasource, "type_name", None)
        sql_dialect = get_sqlglot_dialect(datasource_type)
        snapshot = permission_snapshot or PermissionScopeService.build_snapshot(
            session=session,
            current_user=current_user,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
        )

        eligible_ids = eligible_data_skill_ids(
            session,
            snapshot=snapshot,
            skill_ids={int(data_skill_id)} if data_skill_id not in (None, "") else None,
        )
        selection: dict[str, Any] = {}
        skill_selector = find_data_skills
        skill_text, skill_list, skill_model_id = skill_selector(
            session,
            int(datasource_id),
            target_scope,
            data_skill_id,
            getattr(current_user, "id", None),
            can_manage_all,
            int(tenant_id),
            question=question,
            include_all_target_scopes=include_all_target_scopes,
            can_manage_public=can_manage_public,
            can_manage_platform_public=can_manage_platform_public,
            current_user=current_user,
            eligible_skill_ids=eligible_ids,
            selection_metadata=selection,
        )

        if schema is None:
            loader = schema_loader or _default_schema_loader
            schema, loaded_tables = loader(
                session=session,
                current_user=current_user,
                ds=datasource,
                question=question or "",
                embedding=embedding,
                table_list=table_list,
                data_skill_text=skill_text,
            )
            allowed_tables = list(loaded_tables or [])
        else:
            schema = str(schema)
            allowed_tables = list(allowed_tables or [])

        tracker = tracking_loader or find_tracking_prompt_context
        tracking_config, tracking_summary = tracker(
            session,
            int(tenant_id),
            int(datasource_id),
            datasource_type=datasource_type,
            question=question,
            data_skill_text=skill_text,
        )
        warnings = [
            item[len("schema校验: ") :]
            for item in (tracking_summary or [])
            if isinstance(item, str) and item.startswith("schema校验: ")
        ]

        structured_context = ""
        if settings.KNOWLEDGE_RUNTIME_CONTEXT_ENABLED:
            loader = structured_loader or StructuredKnowledgeContextService().load
            structured = loader(
                session=session,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                permission_snapshot=snapshot,
            )
            structured_context = str(getattr(structured, "text", "") or "")
            warnings.extend(str(item) for item in (getattr(structured, "warnings", ()) or ()))

        knowledge_context = ""
        citations: list[KnowledgeCitation] = []
        knowledge_version_hash: str | None = None
        retrieval_failure_type: str | None = None
        request_id = request_id or new_request_id()
        if retrieval_service is None and settings.KNOWLEDGE_RETRIEVAL_ENABLED:
            retrieval_service = KnowledgeRetrievalService(
                audit_writer=lambda **kwargs: write_retrieval_audit(
                    session=session,
                    request_id=request_id,
                    surface=str(surface),
                    snapshot=snapshot,
                    result=kwargs["result"],
                    user_id=getattr(current_user, "id", None),
                )
            )
        if retrieval_service is not None:
            retrieval = retrieval_service.search(
                session=session,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                surface=str(surface),
                query=_retrieval_query(question, surface, schema, allowed_tables, skill_list),
                permission_snapshot=snapshot,
                request_id=request_id,
                user_id=getattr(current_user, "id", None),
            )
            knowledge_context = retrieval.context
            citations = list(retrieval.citations)
            retrieval_failure_type = retrieval.failure_type
            warnings.extend(retrieval.warnings)
            knowledge_version_hash = _knowledge_version_hash(citations)

        selected_skills = [
            SelectedSkillSnapshot(
                skill_id=int(skill_id),
                selection_mode=str(selection.get("selection_mode") or "AUTOMATIC"),
                source_hash=str(source_hash) if source_hash else None,
            )
            for skill_id, source_hash in zip(
                selection.get("selected_skill_ids", ()),
                selection.get("source_hashes", ()),
                strict=False,
            )
        ]
        skill_selection_hash = _digest(
            {
                "skills": [item.__dict__ for item in selected_skills],
                "skill_list": list(skill_list or []),
            }
        )
        semantic = BusinessSemanticContext(
            permission_snapshot=snapshot,
            selected_skills=selected_skills,
            skill_text=skill_text or "",
            skill_selection_hash=skill_selection_hash,
            tracking_config=tracking_config or "",
            tracking_summary=list(tracking_summary or []),
            structured_context=structured_context,
            knowledge_context=knowledge_context,
            knowledge_citations=citations,
            knowledge_version_hash=knowledge_version_hash,
            retrieval_failure_type=retrieval_failure_type,
            warnings=warnings,
        )
        semantic.context_hash = _digest(
            {
                "permission_version": snapshot.permission_version,
                "schema_hash": snapshot.schema_hash,
                "skill_selection_hash": skill_selection_hash,
                "structured_context_hash": _digest(structured_context),
                "knowledge_version_hash": knowledge_version_hash,
                "retrieval_failure_type": retrieval_failure_type,
                "citation_ids": [item.chunk_id for item in citations],
                "datasource_id": int(datasource_id),
                "surface": str(surface),
            }
        )
        context_audit = audit_writer
        if context_audit is None and settings.KNOWLEDGE_RETRIEVAL_ENABLED:
            def context_audit_writer(**kwargs):
                write_semantic_context_audit(
                    session=session,
                    request_id=request_id,
                    surface=str(surface),
                    semantic=kwargs["semantic"],
                )

            context_audit = context_audit_writer
        if context_audit is not None:
            try:
                context_audit(
                    surface=str(surface),
                    snapshot=snapshot,
                    semantic=semantic,
                )
            except Exception:
                # Audit persistence is best effort; it cannot invalidate a usable context.
                logger.warning("Semantic context audit write failed", exc_info=True)
        return SemanticBuildResult(
            semantic=semantic,
            datasource=datasource,
            datasource_type=datasource_type,
            sql_dialect=sql_dialect,
            schema=str(schema or ""),
            allowed_tables=list(allowed_tables or []),
            data_skill=skill_text or "",
            data_skill_list=list(skill_list or []),
            skill_model_id=int(skill_model_id) if skill_model_id is not None else None,
        )


@dataclass(frozen=True)
class SemanticBuildResult:
    semantic: BusinessSemanticContext
    datasource: CoreDatasource
    datasource_type: str | None
    sql_dialect: str | None
    schema: str
    allowed_tables: list[str]
    data_skill: str
    data_skill_list: list[str]
    skill_model_id: int | None


def _default_schema_loader(**kwargs):
    from apps.datasource.crud.datasource import get_ai_table_schema

    return get_ai_table_schema(**kwargs)


def _retrieval_query(
    question: str | None,
    surface: str,
    schema: str,
    allowed_tables: list[str],
    skill_list: list[str],
) -> str:
    # Keep the retrieval query descriptive but bounded; full row data never enters it.
    parts = [str(question or "").strip(), f"场景：{surface}"]
    if allowed_tables:
        parts.append("数据表：" + ", ".join(str(item) for item in allowed_tables[:100]))
    if schema:
        parts.append("授权 Schema 摘要：" + str(schema)[:4000])
    if skill_list:
        parts.append("已选 Skill 摘要：" + "\n".join(str(item)[:1200] for item in skill_list[:12]))
    return "\n".join(item for item in parts if item)


def _citation_summary(citation: KnowledgeCitation) -> dict[str, Any]:
    return {
        "chunk_id": str(citation.chunk_id),
        "knowledge_base_id": str(citation.knowledge_base_id),
        "knowledge_base_name": citation.knowledge_base_name,
        "version_id": str(citation.version_id),
        "version_number": citation.version_number,
        "section_path": citation.section_path,
        "source_file_name": citation.source_file_name,
        "score": round(float(citation.score), 6),
        "visibility_scope": citation.visibility_scope,
    }


def _knowledge_version_hash(citations: list[KnowledgeCitation]) -> str | None:
    if not citations:
        return None
    snapshot = [
        {
            "knowledge_base_id": int(item.knowledge_base_id),
            "version_id": int(item.version_id),
            "chunk_id": int(item.chunk_id),
        }
        for item in citations
    ]
    return _digest(
        sorted(
            snapshot,
            key=lambda item: (
                item["knowledge_base_id"],
                item["version_id"],
                item["chunk_id"],
            ),
        )
    )


def _digest(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "BusinessSemanticContext",
    "BusinessSemanticContextService",
    "SelectedSkillSnapshot",
    "SemanticBuildResult",
]
