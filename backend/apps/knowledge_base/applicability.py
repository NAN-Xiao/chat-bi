"""Datasource applicability checks for workspace and platform knowledge."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from apps.knowledge_base.lifecycle_models import KnowledgeBaseVersion
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.object_projection_models import SemanticObjectReference
from apps.knowledge_base.object_projection_models import SemanticObjectResolution
from apps.knowledge_base.object_resolution import (
    ResolvedObjectReference,
    resolve_references_for_context,
)
from apps.knowledge_base.retrieval_models import (
    KnowledgeApplicabilityStatus,
    KnowledgeBaseApplicability,
    KnowledgeBaseWorkspaceOverride,
)


@dataclass(frozen=True)
class KnowledgeApplicabilityResult:
    version_id: int
    knowledge_base_id: int | None
    knowledge_tenant_id: int | None
    tenant_id: int
    datasource_id: int
    physical_schema_hash: str
    status: str
    reference_count: int
    resolved_count: int
    warnings: tuple[str, ...] = ()
    report: dict[str, Any] | None = None

    @property
    def eligible(self) -> bool:
        return self.status == KnowledgeApplicabilityStatus.VALID.value


class KnowledgeApplicabilityService:
    """Evaluate physical applicability without making user permission claims."""

    def __init__(
        self,
        *,
        resolver: Callable[..., list[ResolvedObjectReference]] = resolve_references_for_context,
        version_loader: Callable[[Session, int], Any | None] | None = None,
        knowledge_loader: Callable[[Session, int, int], Any | None] | None = None,
        reference_loader: Callable[[Session, int], Iterable[Any]] | None = None,
        override_loader: Callable[[Session, int, int], Any | None] | None = None,
    ) -> None:
        self.resolver = resolver
        self.version_loader = version_loader or self._load_version
        self.knowledge_loader = knowledge_loader or self._load_knowledge
        self.reference_loader = reference_loader or self._load_references
        self.override_loader = override_loader or self._load_override

    def evaluate(
        self,
        *,
        session: Session,
        tenant_id: int,
        datasource_id: int,
        version_id: int,
        physical_schema_hash: str,
    ) -> KnowledgeApplicabilityResult:
        current_hash = str(physical_schema_hash or "").strip()
        version = self.version_loader(session, int(version_id))
        if version is None:
            return self._result(
                version_id=version_id,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                physical_schema_hash=current_hash,
                status=KnowledgeApplicabilityStatus.ERROR.value,
                warnings=("知识版本不存在。",),
            )
        knowledge = self.knowledge_loader(
            session,
            int(version.knowledge_base_id),
            int(version.tenant_id),
        )
        if knowledge is None:
            return self._result(
                version_id=version_id,
                knowledge_base_id=int(version.knowledge_base_id),
                knowledge_tenant_id=int(version.tenant_id),
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                physical_schema_hash=current_hash,
                status=KnowledgeApplicabilityStatus.ERROR.value,
                warnings=("知识库不存在。",),
            )
        if not current_hash:
            result = self._result(
                version_id=version_id,
                knowledge_base_id=int(version.knowledge_base_id),
                knowledge_tenant_id=int(version.tenant_id),
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                physical_schema_hash=current_hash,
                status=KnowledgeApplicabilityStatus.STALE.value,
                warnings=("当前数据源缺少物理 Schema 指纹。",),
            )
            self._persist(session, result)
            return result

        scope = KnowledgeBaseVisibilityScopeEnum(knowledge.visibility_scope)
        if scope != KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC and int(knowledge.tenant_id) != int(tenant_id):
            result = self._result(
                version_id=version_id,
                knowledge_base_id=int(version.knowledge_base_id),
                knowledge_tenant_id=int(version.tenant_id),
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                physical_schema_hash=current_hash,
                status=KnowledgeApplicabilityStatus.INVALID.value,
                warnings=("工作空间知识不属于当前工作空间。",),
            )
            self._persist(session, result)
            return result
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
            override = self.override_loader(session, int(tenant_id), int(knowledge.id))
            if override is not None and not bool(override.enabled):
                result = self._result(
                    version_id=version_id,
                    knowledge_base_id=int(version.knowledge_base_id),
                    knowledge_tenant_id=int(version.tenant_id),
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    physical_schema_hash=current_hash,
                    status=KnowledgeApplicabilityStatus.INVALID.value,
                    warnings=("该平台公共知识已被当前工作空间停用。",),
                )
                self._persist(session, result)
                return result

        references = list(self.reference_loader(session, int(version_id)))
        try:
            resolved = self.resolver(
                references,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                physical_schema_hash=current_hash,
                session=session,
            )
        except Exception as exc:
            result = self._result(
                version_id=version_id,
                knowledge_base_id=int(version.knowledge_base_id),
                knowledge_tenant_id=int(version.tenant_id),
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                physical_schema_hash=current_hash,
                status=KnowledgeApplicabilityStatus.ERROR.value,
                warnings=("对象引用解析失败，暂不可使用。",),
                report={"reason": type(exc).__name__},
            )
            self._persist(session, result)
            return result
        unresolved = [item for item in resolved if item.status != "RESOLVED"]
        status = KnowledgeApplicabilityStatus.VALID.value if not unresolved else KnowledgeApplicabilityStatus.INVALID.value
        result = self._result(
            version_id=version_id,
            knowledge_base_id=int(version.knowledge_base_id),
            knowledge_tenant_id=int(version.tenant_id),
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            physical_schema_hash=current_hash,
            status=status,
            reference_count=len(references),
            resolved_count=len(resolved) - len(unresolved),
            warnings=tuple(
                "存在未解析或有歧义的对象引用。" for _ in unresolved
            ),
            report={
                "reference_statuses": [
                    {"declared_key": item.declared_key, "status": item.status}
                    for item in resolved
                ]
            },
        )
        self._persist(session, result)
        self._persist_resolutions(
            session,
            references=references,
            resolved=resolved,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            physical_schema_hash=current_hash,
        )
        return result

    @staticmethod
    def _load_version(session: Session, version_id: int) -> Any | None:
        return session.get(KnowledgeBaseVersion, int(version_id))

    @staticmethod
    def _load_knowledge(session: Session, knowledge_base_id: int, tenant_id: int) -> Any | None:
        return session.exec(
            select(KnowledgeBase).where(
                KnowledgeBase.id == int(knowledge_base_id),
                KnowledgeBase.tenant_id == int(tenant_id),
            )
        ).first()

    @staticmethod
    def _load_references(session: Session, version_id: int) -> Iterable[Any]:
        return session.exec(
            select(SemanticObjectReference).where(
                SemanticObjectReference.owner_type == "KNOWLEDGE_VERSION",
                SemanticObjectReference.version_id == int(version_id),
            )
        ).all()

    @staticmethod
    def _load_override(session: Session, tenant_id: int, knowledge_base_id: int) -> Any | None:
        return session.exec(
            select(KnowledgeBaseWorkspaceOverride).where(
                KnowledgeBaseWorkspaceOverride.tenant_id == int(tenant_id),
                KnowledgeBaseWorkspaceOverride.knowledge_base_id == int(knowledge_base_id),
            )
        ).first()

    @staticmethod
    def _result(
        *,
        version_id: int,
        tenant_id: int,
        datasource_id: int,
        physical_schema_hash: str,
        status: str,
        knowledge_base_id: int | None = None,
        knowledge_tenant_id: int | None = None,
        reference_count: int = 0,
        resolved_count: int = 0,
        warnings: tuple[str, ...] = (),
        report: dict[str, Any] | None = None,
    ) -> KnowledgeApplicabilityResult:
        return KnowledgeApplicabilityResult(
            version_id=int(version_id),
            knowledge_base_id=knowledge_base_id,
            knowledge_tenant_id=knowledge_tenant_id,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            physical_schema_hash=physical_schema_hash,
            status=status,
            reference_count=int(reference_count),
            resolved_count=int(resolved_count),
            warnings=warnings,
            report=report,
        )

    @staticmethod
    def _persist(session: Session, result: KnowledgeApplicabilityResult) -> None:
        if result.knowledge_base_id is None:
            return
        existing = session.exec(
            select(KnowledgeBaseApplicability).where(
                KnowledgeBaseApplicability.version_id == result.version_id,
                KnowledgeBaseApplicability.tenant_id == result.tenant_id,
                KnowledgeBaseApplicability.datasource_id == result.datasource_id,
                KnowledgeBaseApplicability.physical_schema_hash == result.physical_schema_hash,
            )
        ).first()
        now = datetime.utcnow()
        if existing is None:
            existing = KnowledgeBaseApplicability(
                knowledge_base_id=result.knowledge_base_id,
                knowledge_tenant_id=result.knowledge_tenant_id or result.tenant_id,
                version_id=result.version_id,
                tenant_id=result.tenant_id,
                datasource_id=result.datasource_id,
                physical_schema_hash=result.physical_schema_hash,
            )
        existing.status = result.status
        existing.report = result.report or {"warnings": list(result.warnings)}
        existing.checked_at = now
        session.add(existing)
        session.flush()

    @staticmethod
    def _persist_resolutions(
        session: Session,
        *,
        references: Iterable[Any],
        resolved: Iterable[ResolvedObjectReference],
        tenant_id: int,
        datasource_id: int,
        physical_schema_hash: str,
    ) -> None:
        """Persist resolution status per consuming datasource and schema epoch."""
        if not hasattr(session, "add") or not hasattr(session, "exec"):
            return
        reference_rows = {
            (str(row.declared_key), str(getattr(row.source_kind, "value", row.source_kind))): row
            for row in references
            if getattr(row, "id", None) is not None
        }
        for item in resolved:
            key = (
                str(item.declared_key),
                str(getattr(item.reference.source_kind, "value", item.reference.source_kind)),
            )
            reference = reference_rows.get(key)
            if reference is None:
                continue
            row = session.exec(
                select(SemanticObjectResolution).where(
                    SemanticObjectResolution.reference_id == int(reference.id),
                    SemanticObjectResolution.tenant_id == int(tenant_id),
                    SemanticObjectResolution.datasource_id == int(datasource_id),
                    SemanticObjectResolution.physical_schema_hash == physical_schema_hash,
                )
            ).first()
            if row is None:
                row = SemanticObjectResolution(
                    reference_id=int(reference.id),
                    tenant_id=int(tenant_id),
                    datasource_id=int(datasource_id),
                    physical_schema_hash=physical_schema_hash,
                )
            row.status = item.status
            row.canonical_key = item.canonical_key
            row.report = dict(item.report or {})
            row.checked_at = item.checked_at or datetime.utcnow()
            session.add(row)
        session.flush()
