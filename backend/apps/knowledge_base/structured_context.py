"""Permission-safe, read-only fusion of tracking and structured knowledge."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlmodel import select

from apps.knowledge_base.applicability import KnowledgeApplicabilityService
from apps.knowledge_base.lifecycle_models import KnowledgeBaseVersion
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.object_projection_models import SemanticObjectReference
from apps.knowledge_base.retrieval import KnowledgeRetrievalService
from apps.knowledge_base.retrieval_models import KnowledgeBaseWorkspaceOverride
from apps.knowledge_base.schemas import KnowledgePayloadAdapter
from apps.knowledge_base.source_references import (
    StructuredEventRecord,
    StructuredJsonFieldRecord,
    TrackingStructuredRecords,
    load_tracking_structured_records,
)
from apps.system.crud.tenant import DEFAULT_TENANT_ID


@dataclass(frozen=True)
class StructuredKnowledgeContext:
    events: tuple[StructuredEventRecord, ...] = ()
    json_fields: tuple[StructuredJsonFieldRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        parts: list[str] = []
        if self.events:
            parts.append("## 事件参数\n" + "\n".join(_event_text(item) for item in self.events))
        if self.json_fields:
            parts.append("## JSON 字段\n" + "\n".join(_json_text(item) for item in self.json_fields))
        return "\n\n".join(parts)


class StructuredKnowledgeContextService:
    """Load only current, applicable, authorized structured records."""

    def __init__(
        self,
        *,
        tracking_loader: Callable[..., TrackingStructuredRecords] = load_tracking_structured_records,
        knowledge_loader: Callable[..., Iterable[tuple[Any, Any]]] | None = None,
        applicability_evaluator: Callable[..., Any] | None = None,
        reference_loader: Callable[..., list[Any]] | None = None,
    ) -> None:
        self.tracking_loader = tracking_loader
        self.knowledge_loader = knowledge_loader or self._load_knowledge
        self.applicability_evaluator = applicability_evaluator or KnowledgeApplicabilityService().evaluate
        self.reference_loader = reference_loader or self._load_references

    def load(
        self,
        *,
        session: Any,
        tenant_id: int,
        datasource_id: int,
        permission_snapshot: Any,
    ) -> StructuredKnowledgeContext:
        tracking = self.tracking_loader(
            session,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            permission_snapshot=permission_snapshot,
        )
        warnings = list(tracking.warnings)
        events = list(tracking.events)
        json_fields = list(tracking.json_fields)
        identities: dict[tuple[Any, ...], str] = {
            ("EVENT", item.event_name): item.source_hash for item in events
        }
        identities.update(
            {
                ("JSON_FIELD", item.schema_name, item.table_name, item.source_field, item.json_path, item.field_name): item.source_hash
                for item in json_fields
            }
        )
        for knowledge, version in self.knowledge_loader(session, int(tenant_id), int(datasource_id)):
            if not self._is_eligible_knowledge(
                session,
                knowledge=knowledge,
                version=version,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                permission_snapshot=permission_snapshot,
                warnings=warnings,
            ):
                continue
            try:
                payload = KnowledgePayloadAdapter.validate_python(version.payload or {})
            except Exception:
                warnings.append("结构化知识内容格式不正确，已跳过。")
                continue
            projected = _structured_records(payload, version)
            for record in projected[0]:
                identity = ("EVENT", record.event_name)
                previous = identities.get(identity)
                if previous is not None:
                    if previous != record.source_hash:
                        warnings.append(f"事件 {record.event_name} 存在来源冲突，平台知识已跳过。")
                    continue
                identities[identity] = record.source_hash
                events.append(record)
            for record in projected[1]:
                identity = ("JSON_FIELD", record.schema_name, record.table_name, record.source_field, record.json_path, record.field_name)
                previous = identities.get(identity)
                if previous is not None:
                    if previous != record.source_hash:
                        warnings.append(f"JSON 字段 {record.field_name} 存在来源冲突，平台知识已跳过。")
                    continue
                identities[identity] = record.source_hash
                json_fields.append(record)
        return StructuredKnowledgeContext(
            events=tuple(events),
            json_fields=tuple(json_fields),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _is_eligible_knowledge(
        self,
        session: Any,
        *,
        knowledge: Any,
        version: Any,
        tenant_id: int,
        datasource_id: int,
        permission_snapshot: Any,
        warnings: list[str],
    ) -> bool:
        scope = KnowledgeBaseVisibilityScopeEnum(knowledge.visibility_scope)
        if scope != KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC and int(knowledge.tenant_id) != int(tenant_id):
            return False
        if scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC:
            override = session.exec(
                select(KnowledgeBaseWorkspaceOverride).where(
                    KnowledgeBaseWorkspaceOverride.tenant_id == int(tenant_id),
                    KnowledgeBaseWorkspaceOverride.knowledge_base_id == int(knowledge.id),
                )
            ).first()
            if override is not None and not bool(override.enabled):
                return False
        applicability = self.applicability_evaluator(
            session=session,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            version_id=int(version.id),
            physical_schema_hash=str(permission_snapshot.schema_hash),
        )
        if not getattr(applicability, "eligible", False):
            for warning in getattr(applicability, "warnings", ()):
                warnings.append(str(warning))
            return False
        references = self.reference_loader(session, int(version.id))
        if references and not KnowledgeRetrievalService._references_allowed(
            session,
            references,
            snapshot=permission_snapshot,
        ):
            warnings.append("结构化知识包含当前用户无权访问的对象，已跳过。")
            return False
        return True

    @staticmethod
    def _load_knowledge(session: Any, tenant_id: int, datasource_id: int):
        rows = [
            *session.exec(
                select(KnowledgeBase).where(
                    KnowledgeBase.archived.is_(False),
                    KnowledgeBase.active.is_(True),
                    KnowledgeBase.visibility_scope == KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC,
                    KnowledgeBase.tenant_id == DEFAULT_TENANT_ID,
                )
            ).all(),
            *session.exec(
                select(KnowledgeBase).where(
                    KnowledgeBase.archived.is_(False),
                    KnowledgeBase.active.is_(True),
                    KnowledgeBase.visibility_scope == KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                    KnowledgeBase.tenant_id == int(tenant_id),
                )
            ).all(),
        ]
        output: list[tuple[Any, Any]] = []
        for knowledge in rows:
            version_id = getattr(knowledge, "current_version_id", None)
            version = session.get(KnowledgeBaseVersion, int(version_id)) if version_id else None
            if version is not None and str(getattr(version.status, "value", version.status)) == "PUBLISHED":
                output.append((knowledge, version))
        return output

    @staticmethod
    def _load_references(session: Any, version_id: int) -> list[Any]:
        return list(
            session.exec(
                select(SemanticObjectReference).where(
                    SemanticObjectReference.owner_type == "KNOWLEDGE_VERSION",
                    SemanticObjectReference.version_id == int(version_id),
                )
            ).all()
        )


def _structured_records(payload: Any, version: Any) -> tuple[list[StructuredEventRecord], list[StructuredJsonFieldRecord]]:
    source_hash = str(getattr(version, "content_hash", None) or _hash(payload.model_dump(mode="json")))
    source_identity = ("KNOWLEDGE_VERSION", int(version.id))
    if getattr(payload, "knowledge_type", None) == "EVENT":
        return [StructuredEventRecord(
            event_name=payload.event_name,
            display_name=payload.display_name or payload.event_name,
            description=payload.description,
            table_name=payload.table_name,
            event_name_field=payload.event_name_field,
            event_time_field=payload.event_time_field,
            parameters=tuple(item.model_dump(mode="json") for item in payload.parameters),
            source_identity=source_identity,
            source_hash=source_hash,
        )], []
    if getattr(payload, "knowledge_type", None) == "JSON_FIELD":
        return [], [StructuredJsonFieldRecord(
            schema_name=payload.schema_name,
            table_name=payload.table_name,
            source_field=payload.source_field,
            json_path=payload.json_path,
            field_name=payload.field_name,
            display_name=payload.display_name or payload.field_name,
            data_type=payload.data_type,
            expression=payload.expression,
            description=payload.description,
            value_mappings=dict(payload.value_mappings or {}),
            source_identity=source_identity,
            source_hash=source_hash,
        )]
    return [], []


def _event_text(item: StructuredEventRecord) -> str:
    parameters = ", ".join(f"{value.get('name')}: {value.get('description') or value.get('data_type') or '未说明'}" for value in item.parameters)
    return f"- {item.event_name}（表：{item.table_name}，事件字段：{item.event_name_field}）{item.description or ''}{'；参数：' + parameters if parameters else ''}"


def _json_text(item: StructuredJsonFieldRecord) -> str:
    return f"- {item.field_name}：{item.table_name}.{item.source_field}{item.json_path}，类型：{item.data_type}，表达式：{item.expression}"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


__all__ = ["StructuredKnowledgeContext", "StructuredKnowledgeContextService"]
