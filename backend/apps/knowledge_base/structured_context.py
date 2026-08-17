"""Permission-safe, read-only projection of workspace tracking metadata."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.knowledge_base.source_references import (
    StructuredEventRecord,
    StructuredJsonFieldRecord,
    TrackingStructuredRecords,
    load_tracking_structured_records,
)


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
    """Load structured records from the workspace tracking specification."""

    def __init__(
        self,
        *,
        tracking_loader: Callable[..., TrackingStructuredRecords] = load_tracking_structured_records,
    ) -> None:
        self.tracking_loader = tracking_loader

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
        return StructuredKnowledgeContext(
            events=tuple(tracking.events),
            json_fields=tuple(tracking.json_fields),
            warnings=tuple(dict.fromkeys(tracking.warnings)),
        )


def _event_text(item: StructuredEventRecord) -> str:
    parameters = ", ".join(
        f"{value.get('name')}: {value.get('description') or value.get('data_type') or '未说明'}"
        for value in item.parameters
    )
    suffix = f"；参数：{parameters}" if parameters else ""
    return f"- {item.event_name}（表：{item.table_name}，事件字段：{item.event_name_field}）{item.description or ''}{suffix}"


def _json_text(item: StructuredJsonFieldRecord) -> str:
    return f"- {item.field_name}：{item.table_name}.{item.source_field}{item.json_path}，类型：{item.data_type}，表达式：{item.expression}"


__all__ = ["StructuredKnowledgeContext", "StructuredKnowledgeContextService"]
