"""验证数据字典 JSON 字段在写入存储前使用统一身份规则。"""
from __future__ import annotations

import pytest

from apps.system.crud.tracking_config import (
    _tracking_field_json_identity,
    get_tracking_config,
    save_tracking_config,
    validate_tracking_datasource_references,
)
from apps.system.models.tenant import TenantTrackingConfigModel
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigEditor,
    TenantTrackingFieldBase,
    TenantTrackingTableBase,
)


class UnexpectedSession:
    def exec(self, *_args, **_kwargs):
        raise AssertionError("无效 JSON 字段不应访问数据库")


class _QueryResult:
    def __init__(self, *, first=None, rows=None):
        self._first = first
        self._rows = list(rows or [])

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _SequenceSession:
    def __init__(self, results):
        self._results = iter(results)

    def exec(self, *_args, **_kwargs):
        return next(self._results)


@pytest.mark.parametrize(
    ("field_name", "json_path", "expected_path"),
    [
        ("abtest.1001", "$.1001", '$["1001"]'),
        ("abtest[1001]", "$[1001]", "$[1001]"),
    ],
)
def test_json_field_identity_normalizes_path_without_losing_segment_type(
    field_name: str,
    json_path: str,
    expected_path: str,
) -> None:
    field = TenantTrackingFieldBase(
        table_name="event",
        field_name=field_name,
        source_field="abtest",
        json_path=json_path,
    )

    assert _tracking_field_json_identity(field) == ("abtest", expected_path)


def test_save_rejects_json_field_name_that_disagrees_with_path() -> None:
    editor = TenantTrackingConfigEditor(
        fields=[
            TenantTrackingFieldBase(
                table_name="event",
                field_name='abtest["1001"]',
                source_field="abtest",
                json_path='$["1001"]',
            )
        ]
    )

    with pytest.raises(ValueError, match=r"event.*abtest\.1001"):
        save_tracking_config(UnexpectedSession(), 2001, editor, datasource_id=3)


def test_save_rejects_datasource_reference_from_another_workspace_before_database_access() -> None:
    editor = TenantTrackingConfigEditor(
        notes="LDS 数据字典，datasource_id = 3。",
    )

    with pytest.raises(ValueError, match=r"数据源 3 与当前数据源 10 不一致"):
        save_tracking_config(UnexpectedSession(), 2001, editor, datasource_id=10)


def test_save_rejects_nested_datasource_reference_from_extra_properties() -> None:
    editor = TenantTrackingConfigEditor(
        tables=[
            TenantTrackingTableBase(
                table_name="event",
                extra_properties={"source": {"description": "datasource_id: 3"}},
            )
        ]
    )

    with pytest.raises(ValueError, match=r"数据源 3 与当前数据源 10 不一致"):
        save_tracking_config(UnexpectedSession(), 2001, editor, datasource_id=10)


@pytest.mark.parametrize(
    "extra_properties",
    [
        {"datasource_id": 3},
        {"serialized": '{"datasource_id": 3}'},
    ],
)
def test_save_rejects_structured_or_serialized_datasource_reference(extra_properties: dict) -> None:
    editor = TenantTrackingConfigEditor(
        tables=[TenantTrackingTableBase(table_name="event", extra_properties=extra_properties)]
    )

    with pytest.raises(ValueError, match=r"数据源 3 与当前数据源 10 不一致"):
        save_tracking_config(UnexpectedSession(), 2001, editor, datasource_id=10)


def test_tracking_datasource_reference_allows_current_datasource() -> None:
    editor = TenantTrackingConfigEditor(
        notes="当前配置 datasource_id=10",
        sql_rules="只允许 datasource id：10。",
    )

    validate_tracking_datasource_references(editor, 10)


def test_tracking_datasource_reference_rejects_concrete_id_when_unbound() -> None:
    editor = TenantTrackingConfigEditor(notes="datasource_id=10")

    with pytest.raises(ValueError, match="当前工作空间未绑定数据源"):
        validate_tracking_datasource_references(editor, None)


def test_get_tracking_config_rejects_polluted_persisted_content() -> None:
    row = TenantTrackingConfigModel(
        id=1,
        tenant_id=2001,
        datasource_id=10,
        notes="错误配置 datasource_id=3",
    )
    session = _SequenceSession(
        [
            _QueryResult(first=row),
            _QueryResult(rows=[]),
            _QueryResult(rows=[]),
            _QueryResult(rows=[]),
        ]
    )

    with pytest.raises(ValueError, match=r"数据源 3 与当前数据源 10 不一致"):
        get_tracking_config(session, 2001, datasource_id=10)
