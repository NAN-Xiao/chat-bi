"""Workspace role mappings reach SQL schema only for authorized exact fields."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.datasource.crud import datasource as datasource_crud
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO


class _Session:
    def __init__(self, schema_fields=()):
        tables = [SimpleNamespace(table_name="activity", table_comment="")] if schema_fields else []
        self.results = iter([tables, list(schema_fields)])

    def exec(self, _statement):
        return SimpleNamespace(all=lambda: next(self.results))


def _schema(monkeypatch, *, mappings, field_role=None, denied=False, table_denied=False, enabled=True, schema_only=False):
    field = {
        "table_name": "activity", "field_name": "occurred_at", "field_role": field_role,
        "semantic_type": "date", "field_comment": "原始事件时间",
        "extra_properties": {"encoding": "epoch_milliseconds"},
    }
    config = TenantTrackingConfigDTO(
        tenant_id=201, datasource_id=31, enabled=enabled,
        fields=[] if schema_only else [field], field_role_mappings=mappings,
    )
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args: True)

    def configured(_session, tenant_id, datasource_id, *, include_legacy):
        assert (tenant_id, datasource_id, include_legacy) == (201, 31, False)
        return config

    monkeypatch.setattr(datasource_crud, "get_tracking_config", configured)
    monkeypatch.setattr(datasource_crud, "datasource_physical_schema", lambda *_args: {"activity": {"occurred_at"}})
    cached = SimpleNamespace(
        table=SimpleNamespace(id=71, table_name="activity"),
        fields=[SimpleNamespace(field_name="occurred_at", field_type="bigint")],
    )
    monkeypatch.setattr(datasource_crud, "get_table_obj_by_ds", lambda **_kwargs: [cached])
    monkeypatch.setattr(datasource_crud, "get_user_permission_rules", lambda *_args: [])
    monkeypatch.setattr(datasource_crud, "get_user_scoped_table_ids", lambda *_args: set() if table_denied else None)
    monkeypatch.setattr(datasource_crud, "get_column_permission_fields", lambda **kwargs: [] if denied else kwargs["fields"])
    schema_fields = [SimpleNamespace(table_name="activity", field_name="occurred_at", field_comment="事件时间说明")] if schema_only else []
    return datasource_crud._dictionary_schema_from_workspace(
        session=_Session(schema_fields), current_user=SimpleNamespace(id=5, tenant_id=999),
        ds=SimpleNamespace(id=31, type="mysql"), tenant_id=201, db_name="business", table_list=None,
    )[0]


def test_explicit_workspace_role_mapping_reaches_schema_with_encoding(monkeypatch):
    schema = _schema(monkeypatch, mappings=[{"table": "activity", "field": "occurred_at", "role": "event_time"}])
    assert "role=event_time" in schema
    assert "occurred_at:bigint" in schema
    assert "encoding=epoch_milliseconds" in schema


def test_mapping_applies_to_workspace_schema_comment_fields(monkeypatch):
    schema = _schema(monkeypatch, mappings=[{"table": "activity", "field": "occurred_at", "role": "event_time"}], schema_only=True)
    assert "role=event_time" in schema
    assert "事件时间说明" in schema


@pytest.mark.parametrize("field_role,mappings", [
    ("partition_date", [{"table": "activity", "field": "occurred_at", "role": "event_time"}]),
    (None, [{"table": "activity", "field": "occurred_at", "role": "event_time"}, {"table": "activity", "field": "occurred_at", "role": "partition_date"}]),
])
def test_conflicting_visible_field_roles_are_explicit_validation_error(monkeypatch, field_role, mappings):
    with pytest.raises(HTTPException) as error:
        _schema(monkeypatch, field_role=field_role, mappings=mappings)
    assert error.value.status_code == 422
    assert "activity.occurred_at" in error.value.detail
    assert "冲突" in error.value.detail


def test_matching_field_and_mapping_roles_are_emitted_once(monkeypatch):
    mapping = {"table": "activity", "field": "occurred_at", "role": "event_time"}
    schema = _schema(monkeypatch, field_role="event_time", mappings=[mapping, mapping])
    assert schema.count("role=event_time") == 1


@pytest.mark.parametrize("mapping", [
    {"table": "other_table", "field": "occurred_at", "role": "event_time"},
    {"table": "activity", "field": "other_field", "role": "event_time"},
    {"field": "occurred_at", "role": "event_time"},
    {"field_role": "event_time", "description": "角色词典条目"},
])
def test_mapping_never_guesses_a_field_or_table(monkeypatch, mapping):
    schema = _schema(monkeypatch, mappings=[mapping])
    assert "role=event_time" not in schema


def test_denied_field_does_not_leak_role_or_conflict(monkeypatch):
    schema = _schema(monkeypatch, denied=True, field_role="partition_date", mappings=[
        {"table": "activity", "field": "occurred_at", "role": "event_time"},
    ])
    assert "occurred_at" not in schema
    assert "event_time" not in schema


def test_disabled_tracking_config_does_not_apply_role_mappings(monkeypatch):
    schema = _schema(monkeypatch, enabled=False, schema_only=True, mappings=[
        {"table": "activity", "field": "occurred_at", "role": "event_time"},
    ])
    assert "role=event_time" not in schema


def test_denied_table_does_not_leak_role_or_conflict(monkeypatch):
    schema = _schema(monkeypatch, table_denied=True, field_role="partition_date", mappings=[
        {"table": "activity", "field": "occurred_at", "role": "event_time"},
    ])
    assert "activity" not in schema
    assert "event_time" not in schema


def test_no_datasource_access_does_not_read_workspace_roles(monkeypatch):
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args: False)

    def unavailable(*_args, **_kwargs):
        pytest.fail("无数据源访问权时不能读取字段角色配置")

    monkeypatch.setattr(datasource_crud, "get_tracking_config", unavailable)
    assert datasource_crud._dictionary_schema_from_workspace(
        session=_Session(), current_user=SimpleNamespace(id=5), ds=SimpleNamespace(id=31),
        tenant_id=201, db_name="business", table_list=None,
    ) == ("", [], False)
