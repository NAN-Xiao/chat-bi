"""验证 AI Schema 始终使用业务上下文中已确认的工作空间租户。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.datasource.crud import datasource as datasource_crud


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _SchemaSession:
    def __init__(self, results):
        self._results = iter(results)

    def exec(self, _statement):
        return _ExecResult(next(self._results))


def test_schema_metadata_prefers_explicit_business_context_tenant(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []

    def _bound(_session, datasource_id: int, tenant_id: int) -> bool:
        calls.append((datasource_id, tenant_id))
        return (datasource_id, tenant_id) == (10, 7493272675721154560)

    monkeypatch.setattr(datasource_crud, "datasource_bound_to_tenant", _bound)

    tenant_id = datasource_crud._schema_metadata_tenant_id(
        SimpleNamespace(),
        SimpleNamespace(id=10, tenant_id=7493272675721154560),
        SimpleNamespace(tenant_id=7477202383789887488),
        tenant_id=7493272675721154560,
    )

    assert tenant_id == 7493272675721154560
    assert calls == [(10, 7493272675721154560)]


def test_schema_metadata_rejects_datasource_outside_explicit_tenant(monkeypatch) -> None:
    monkeypatch.setattr(
        datasource_crud,
        "datasource_bound_to_tenant",
        lambda _session, _datasource_id, _tenant_id: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        datasource_crud._schema_metadata_tenant_id(
            SimpleNamespace(),
            SimpleNamespace(id=10, tenant_id=7493272675721154560),
            SimpleNamespace(tenant_id=7477202383789887488),
            tenant_id=7493272675721154560,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "当前数据源未绑定到所选工作空间"


def test_ai_schema_propagates_explicit_tenant_to_dictionary_and_cached_fallback(monkeypatch) -> None:
    dictionary_tenants: list[int | None] = []
    cached_tenants: list[int | None] = []

    monkeypatch.setattr(
        datasource_crud,
        "_schema_metadata_tenant_id",
        lambda _session, _ds, _user, tenant_id=None: tenant_id,
    )
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda _value: '{"dbSchema":"public"}')

    def _dictionary(**kwargs):
        dictionary_tenants.append(kwargs.get("tenant_id"))
        return "", [], False

    def _cached(**kwargs):
        cached_tenants.append(kwargs.get("tenant_id"))
        return "【Schema】\n# Table: event\n", ["event"]

    monkeypatch.setattr(datasource_crud, "_dictionary_schema_from_workspace", _dictionary)
    monkeypatch.setattr(datasource_crud, "get_table_schema", _cached)

    schema, tables = datasource_crud.get_ai_table_schema(
        SimpleNamespace(),
        SimpleNamespace(tenant_id=7477202383789887488),
        SimpleNamespace(id=10, type="pg", configuration="{}"),
        "最近 30 天留存",
        embedding=False,
        tenant_id=7493272675721154560,
    )

    assert dictionary_tenants == [7493272675721154560]
    assert cached_tenants == [7493272675721154560]
    assert tables == ["event"]
    assert "cached datasource metadata" in schema


def test_dictionary_schema_uses_explicit_tenant_for_cached_metadata(monkeypatch) -> None:
    cached_tenants: list[int | None] = []
    tenant_id = 7493272675721154560

    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        datasource_crud,
        "get_tracking_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            enabled=False,
            tables=[],
            fields=[],
            event_name_mappings=[],
            field_role_mappings=[],
            sql_rules=[],
        ),
    )
    monkeypatch.setattr(datasource_crud, "datasource_physical_schema", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        datasource_crud,
        "project_event_schema_fields",
        lambda *_args, **_kwargs: SimpleNamespace(warnings=[], fields=[], datasource_type="pg"),
    )

    def _cached_tables(**kwargs):
        cached_tenants.append(kwargs.get("tenant_id"))
        return [
            SimpleNamespace(
                table=SimpleNamespace(id=101, table_name="event"),
                fields=[SimpleNamespace(field_name="event_name", field_type="text")],
            )
        ]

    monkeypatch.setattr(datasource_crud, "get_table_obj_by_ds", _cached_tables)
    monkeypatch.setattr(datasource_crud, "get_user_permission_rules", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(datasource_crud, "get_user_scoped_table_ids", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        datasource_crud,
        "get_column_permission_fields",
        lambda **kwargs: kwargs["fields"],
    )

    session = _SchemaSession([
        [SimpleNamespace(table_name="event", table_comment="event table")],
        [SimpleNamespace(table_name="event", field_name="event_name", field_comment="event")],
    ])
    schema, tables, configured = datasource_crud._dictionary_schema_from_workspace(
        session=session,
        current_user=SimpleNamespace(tenant_id=7477202383789887488),
        ds=SimpleNamespace(id=10, type="pg", table_relation=None),
        tenant_id=tenant_id,
        db_name="public",
        table_list=None,
    )

    assert cached_tenants == [tenant_id]
    assert configured is True
    assert tables == ["event"]
    assert "event_name:text" in schema
