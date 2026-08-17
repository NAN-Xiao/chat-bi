"""Structured source fusion remains read-only and fails closed on conflicts."""

from __future__ import annotations

from types import SimpleNamespace

from apps.knowledge_base import source_references
from apps.knowledge_base.source_references import (
    StructuredEventRecord,
    TrackingStructuredRecords,
)
from apps.knowledge_base.structured_context import StructuredKnowledgeContextService


class _Result:
    def first(self):
        return None

    def all(self):
        return []


class _Session:
    def exec(self, _statement):
        return _Result()


def _snapshot():
    return SimpleNamespace(
        tenant_id=2,
        datasource_id=9,
        schema_hash="schema",
        allowed_object_keys=frozenset({"allowed"}),
        denied_object_keys=frozenset(),
    )


def test_tracking_adapter_filters_denied_events_without_writing(monkeypatch):
    config = SimpleNamespace(
        id=12,
        enabled=True,
        default_event_table="events",
        default_event_name_field="event_name",
        default_event_time_field="event_time",
        event_name_mappings=[{"event_name": "purchase", "description": "购买"}],
        fields=[],
    )
    monkeypatch.setattr(source_references, "get_tracking_config", lambda *args, **kwargs: config)
    result = source_references.load_tracking_structured_records(
        _Session(),
        tenant_id=2,
        datasource_id=9,
        permission_snapshot=_snapshot(),
        resolver=lambda *_args, **_kwargs: [SimpleNamespace(status="RESOLVED", canonical_key="denied")],
    )
    assert result.events == ()
    assert result.json_fields == ()


def test_structured_service_uses_tracking_records_without_knowledge_type_projection():
    tracking_event = StructuredEventRecord(
        event_name="purchase",
        display_name="购买",
        description="旧事件字典",
        table_name="events",
        event_name_field="event_name",
        event_time_field="event_time",
        parameters=(),
        source_identity=("TRACKING_CONFIG", 12),
        source_hash="tracking-hash",
    )
    service = StructuredKnowledgeContextService(
        tracking_loader=lambda *args, **kwargs: TrackingStructuredRecords(
            events=(tracking_event,),
            warnings=("tracking warning", "tracking warning"),
        ),
    )
    result = service.load(
        session=_Session(),
        tenant_id=2,
        datasource_id=9,
        permission_snapshot=_snapshot(),
    )
    assert [item.description for item in result.events] == ["旧事件字典"]
    assert result.warnings == ("tracking warning",)
