"""
脚本说明：验证请求级事件属性只按当前问题和 Data Skill 投影到 AI Schema。
"""
from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import pytest

from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingFieldDTO,
)


def _projection_module():
    try:
        return import_module("apps.system.crud.tracking_event_schema")
    except ModuleNotFoundError:
        pytest.fail("尚未实现请求级事件属性 Schema 投影模块")


def _config(*mappings: dict) -> TenantTrackingConfigDTO:
    return TenantTrackingConfigDTO(
        tenant_id=2001,
        datasource_id=1,
        enabled=True,
        default_event_table="event",
        default_event_name_field="event",
        event_name_mappings=list(mappings),
    )


def _property(name: str, property_type: str, source_field: str, json_path: str, display_name: str = "") -> dict:
    return {
        "property_name": name,
        "property_display_name": display_name or name,
        "property_type": property_type,
        "source_field": source_field,
        "json_path": json_path,
    }


def test_data_skill_projects_only_referenced_properties_for_event() -> None:
    module = _projection_module()
    config = _config(
        {
            "event_name": "PayBuyRet",
            "event_display_name": "支付回调",
            "properties": [
                _property("personal.ed_money", "number", "personal", "$.ed_money", "充值金额"),
                _property("personal.ed_isSuccess", "boolean", "personal", "$.ed_isSuccess", "是否成功"),
                _property("personal.order_id", "text", "personal", "$.order_id", "订单号"),
            ],
        }
    )

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "personal", "uid"}},
        "mysql",
        question="使用折线图展示近七天 ARPPU 趋势",
        data_skill_text="PayBuyRet 使用 personal.ed_money，成功条件 personal.ed_isSuccess=1",
    )

    assert [field.field_name for field in projection.fields] == [
        "personal.ed_money",
        "personal.ed_isSuccess",
    ]
    assert {field.event_name for field in projection.fields} == {"PayBuyRet"}
    assert projection.fields[0].expression == (
        "CAST(JSON_UNQUOTE(JSON_EXTRACT(`event`.`personal`, '$.ed_money')) AS DECIMAL(38, 10))"
    )
    assert projection.warnings == []

    schema = module.format_event_schema_projection(projection)
    assert "# Event: PayBuyRet" in schema
    assert "Required predicate: `event`.`event` = 'PayBuyRet'" in schema
    assert "personal.order_id" not in schema


def test_multiple_events_keep_separate_event_boundaries() -> None:
    module = _projection_module()
    config = _config(
        {
            "event_name": "PayBuyRet",
            "properties": [_property("personal.ed_money", "number", "personal", "$.ed_money")],
        },
        {
            "event_name": "ResourceChange",
            "properties": [_property("personal.ed_change.FOOD", "number", "personal", "$.ed_change.FOOD")],
        },
    )

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "personal", "uid"}},
        "postgresql",
        question="比较 PayBuyRet 与 ResourceChange",
        data_skill_text="使用 personal.ed_money 和 personal.ed_change.FOOD",
    )

    assert [(field.event_name, field.field_name) for field in projection.fields] == [
        ("PayBuyRet", "personal.ed_money"),
        ("ResourceChange", "personal.ed_change.FOOD"),
    ]
    schema = module.format_event_schema_projection(projection)
    assert schema.count("# Event:") == 2
    assert "Required predicate: \"event\".\"event\" = 'PayBuyRet'" in schema
    assert "Required predicate: \"event\".\"event\" = 'ResourceChange'" in schema


def test_shared_property_without_event_context_is_rejected_as_ambiguous() -> None:
    module = _projection_module()
    config = _config(
        {
            "event_name": "PayBuyRet",
            "properties": [_property("personal.amount", "number", "personal", "$.amount")],
        },
        {
            "event_name": "RefundRet",
            "properties": [_property("personal.amount", "number", "personal", "$.amount")],
        },
    )

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "personal"}},
        "mysql",
        question="统计 personal.amount",
        data_skill_text="",
    )

    assert projection.fields == []
    assert any("无法确定所属事件" in warning for warning in projection.warnings)


def test_missing_physical_host_field_returns_warning_without_expression() -> None:
    module = _projection_module()
    config = _config(
        {
            "event_name": "PayBuyRet",
            "properties": [_property("personal.ed_money", "number", "personal", "$.ed_money")],
        }
    )

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "uid"}},
        "mysql",
        question="PayBuyRet 的 personal.ed_money",
        data_skill_text="",
    )

    assert projection.fields == []
    assert any("来源字段 personal 不在当前数据源 schema 中" in warning for warning in projection.warnings)


def test_container_property_is_not_projected_as_scalar_expression() -> None:
    module = _projection_module()
    config = _config(
        {
            "event_name": "HeroSnapshot",
            "properties": [_property("personal.heroes", "对象数组", "personal", "$.heroes")],
        }
    )

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "personal"}},
        "mysql",
        question="HeroSnapshot 的 personal.heroes",
        data_skill_text="",
    )

    assert projection.fields == []
    assert any("容器类型" in warning for warning in projection.warnings)


@pytest.mark.parametrize(
    ("datasource_type", "expected_expression"),
    [
        (
            "mysql",
            "CAST(JSON_UNQUOTE(JSON_EXTRACT(`event`.`personal`, '$.amount')) AS DECIMAL(38, 10))",
        ),
        (
            "postgresql",
            "NULLIF((\"event\".\"personal\"::jsonb ->> 'amount'), '')::numeric",
        ),
        (
            "clickhouse",
            "toFloat64OrNull(JSON_VALUE(`event`.`personal`, '$.amount'))",
        ),
    ],
)
def test_projection_compiles_numeric_expression_for_runtime_dialect(
    datasource_type: str,
    expected_expression: str,
) -> None:
    module = _projection_module()
    config = _config(
        {
            "event_name": "PayBuyRet",
            "properties": [_property("personal.amount", "数值", "personal", "$.amount")],
        }
    )

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "personal"}},
        datasource_type,
        question="PayBuyRet 的 personal.amount",
        data_skill_text="",
    )

    assert projection.fields[0].semantic_type == "number"
    assert projection.fields[0].expression == expected_expression


def test_projection_budget_overflow_rejects_all_required_fields() -> None:
    module = _projection_module()
    properties = [
        _property(f"personal.metric_{index}", "number", "personal", f"$.metric_{index}")
        for index in range(240)
    ]
    config = _config({"event_name": "LargeEvent", "properties": properties})
    data_skill_text = "LargeEvent " + " ".join(item["property_name"] for item in properties)

    projection = module.project_event_schema_fields(
        config,
        {"event": {"event", "personal"}},
        "mysql",
        question="计算大型事件指标",
        data_skill_text=data_skill_text,
    )

    assert projection.fields == []
    assert any("超过 16000 字符预算" in warning for warning in projection.warnings)


class _Rows:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return list(self._rows)


class _DictionarySession:
    def exec(self, _statement) -> _Rows:
        return _Rows([])


def test_workspace_dictionary_schema_does_not_append_request_event_projection(monkeypatch) -> None:
    from apps.datasource.crud import datasource as datasource_crud

    config = _config(
        {
            "event_name": "PayBuyRet",
            "properties": [
                _property("personal.ed_money", "number", "personal", "$.ed_money"),
                _property("personal.order_id", "text", "personal", "$.order_id"),
            ],
        }
    )
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(datasource_crud, "get_tracking_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(
        datasource_crud,
        "datasource_physical_schema",
        lambda *_args, **_kwargs: {"event": {"event", "personal", "uid"}},
    )
    schema, tables, configured = datasource_crud._dictionary_schema_from_workspace(
        session=_DictionarySession(),
        current_user=SimpleNamespace(id=1001),
        ds=SimpleNamespace(id=1, type="mysql", type_name="MySQL"),
        tenant_id=2001,
        db_name="xiuxian",
        table_list=None,
    )

    assert configured is False
    assert tables == []
    assert schema == ""
    assert not hasattr(datasource_crud, "project_event_schema_fields")


def test_workspace_dictionary_schema_omits_event_specific_validation_warnings(monkeypatch) -> None:
    from apps.datasource.crud import datasource as datasource_crud

    config = _config(
        {
            "event_name": "ShopBuyItem",
            "properties": [_property("personal.item_id", "text", "personal", "$.item_id")],
        }
    ).model_copy(
        update={
            "default_event_table": "missing_event_table",
            "fields": [
                TenantTrackingFieldDTO(
                    tenant_id=2001,
                    table_name="event",
                    field_name="uid",
                    field_comment="用户 ID",
                )
            ],
        }
    )
    table_obj = SimpleNamespace(
        table=SimpleNamespace(id=10, table_name="event"),
        fields=[SimpleNamespace(field_name="uid", field_type="text")],
    )
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(datasource_crud, "get_tracking_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(
        datasource_crud,
        "datasource_physical_schema",
        lambda *_args, **_kwargs: {"event": {"uid"}},
    )
    monkeypatch.setattr(datasource_crud, "get_table_obj_by_ds", lambda **_kwargs: [table_obj])
    monkeypatch.setattr(datasource_crud, "get_user_permission_rules", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(datasource_crud, "get_user_scoped_table_ids", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        datasource_crud,
        "get_column_permission_fields",
        lambda **kwargs: kwargs["fields"],
    )

    schema, tables, configured = datasource_crud._dictionary_schema_from_workspace(
        session=_DictionarySession(),
        current_user=SimpleNamespace(id=1001),
        ds=SimpleNamespace(id=1, type="mysql", type_name="MySQL"),
        tenant_id=2001,
        db_name="xiuxian",
        table_list=None,
    )

    assert configured is True
    assert tables == ["event"]
    assert "uid:text" in schema
    assert "missing_event_table" not in schema
    assert "ShopBuyItem" not in schema
