"""
脚本说明：验证工作空间事件字典不进入 AI 上下文，非事件字段规则仍按问题投影。
"""
from __future__ import annotations

from copy import deepcopy

from apps.system.crud import tracking_config as tracking_config_crud
from apps.system.crud.tracking_config import build_tracking_prompt_context
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingEventGroupDTO,
    TenantTrackingFieldDTO,
)


def _tracking_config() -> TenantTrackingConfigDTO:
    return TenantTrackingConfigDTO(
        tenant_id=1,
        enabled=True,
        default_event_table="event_log",
        default_subject_field="uid",
        default_event_name_field="event_name",
        default_event_time_field="event_time",
        fields=[
            TenantTrackingFieldDTO(
                tenant_id=1,
                table_name="event_log",
                field_name="uid",
                field_role="subject_id",
                semantic_type="identifier",
            ),
            TenantTrackingFieldDTO(
                tenant_id=1,
                table_name="event_log",
                field_name="event_name",
                field_comment="业务事件名",
                field_role="event_name",
                semantic_type="text",
                value_mappings={
                    "ShopBuyComplete": "商店购买完成",
                    "PayBuyRet": "商店购买返回",
                },
            ),
            TenantTrackingFieldDTO(
                tenant_id=1,
                table_name="event_log",
                field_name="event_props.amount",
                field_comment="支付金额",
                field_role="json_path_metric",
                semantic_type="number",
                source_field="event_props",
                json_path="$.amount",
                expression="amount_expression",
            ),
            TenantTrackingFieldDTO(
                tenant_id=1,
                table_name="event_log",
                field_name="event_props.battle_result",
                field_comment="战斗结果",
                field_role="json_path_dimension",
                semantic_type="text",
                source_field="event_props",
                json_path="$.battle_result",
                expression="battle_result_expression",
                value_mappings={"MappingOnlyVictory": "仅映射命中的胜利"},
            ),
        ],
        event_name_mappings=[
            {
                "event_name": "ShopBuyItem",
                "event_display_name": "商店购买真实使用",
                "event_category": "商店事件",
                "properties": [
                    {"property_name": "item_id", "property_display_name": "商品 ID"},
                ],
            },
            {
                "event_name": "ShopBuyComplete",
                "event_display_name": "商店购买完成",
                "event_category": "商店事件",
                "properties": [
                    {"property_name": "order_id", "property_display_name": "订单号"},
                ],
            },
        ],
        event_groups=[
            TenantTrackingEventGroupDTO(
                tenant_id=1,
                group_key="shop_purchase",
                group_name="商店购买流程",
                event_names=["ShopBuyItem", "ShopBuyComplete"],
                enabled=True,
            )
        ],
        sql_rules="订单金额统一使用 event_props.amount。",
        notes="字段定义由当前工作空间维护。",
    )


def test_tracking_prompt_omits_event_dictionary_without_mutating_config() -> None:
    """
    是什么：事件名、属性和分组不进入 AI Prompt，原始管理配置保持不变。
    """
    config = _tracking_config()
    original_mappings = deepcopy(config.event_name_mappings)
    original_groups = deepcopy(config.event_groups)
    original_field_mappings = deepcopy([field.value_mappings for field in config.fields])

    context, summary = build_tracking_prompt_context(config, question="商店购买相关事件有哪些")

    assert "<Workspace-Tracking-Rules>" in context
    assert "<Configured-Event-Names>" not in context
    assert "## 事件名映射" not in context
    assert "## 事件分组" not in context
    assert "## 默认字段" not in context
    for event_text in (
        "ShopBuyItem",
        "ShopBuyComplete",
        "商店购买真实使用",
        "商店购买完成",
        "item_id",
        "order_id",
        "shop_purchase",
        "商店购买流程",
        "PayBuyRet",
    ):
        assert event_text not in context
        assert all(event_text not in item for item in summary)
    assert "订单金额统一使用 event_props.amount" in context
    assert "字段定义由当前工作空间维护" in context
    assert config.event_name_mappings == original_mappings
    assert config.event_groups == original_groups
    assert [field.value_mappings for field in config.fields] == original_field_mappings


def test_tracking_prompt_does_not_match_or_render_field_value_mappings() -> None:
    """字段值映射既不进入 Prompt，也不能成为字段投影命中依据。"""
    context, summary = build_tracking_prompt_context(
        _tracking_config(),
        question='{"MappingOnlyVictory":"仅映射命中的胜利"}',
    )

    assert "`event_log.event_props.battle_result`" not in context
    assert "MappingOnlyVictory" not in context
    assert "仅映射命中的胜利" not in context
    assert all("MappingOnlyVictory" not in item for item in summary)
    assert "value_mappings=" not in context
    assert all("value_mappings=" not in item for item in summary)


def test_tracking_prompt_omits_event_specific_schema_warnings(monkeypatch) -> None:
    """事件默认配置的 schema 漂移不得通过校验 warning 重新进入 Prompt。"""
    config = _tracking_config().model_copy(
        update={
            "default_event_table": "missing_event_table",
            "default_event_name_field": "ShopBuyItem",
        }
    )
    monkeypatch.setattr(tracking_config_crud, "get_tracking_config", lambda *_args: config)
    monkeypatch.setattr(
        tracking_config_crud,
        "datasource_physical_schema",
        lambda *_args: {"event_log": {"uid", "event_name", "event_props"}},
    )

    context, summary = tracking_config_crud.find_tracking_prompt_context(
        object(),
        tenant_id=1,
        datasource_id=2,
        datasource_type="postgresql",
        question="分析支付金额",
    )

    assert "missing_event_table" not in context
    assert "ShopBuyItem" not in context
    assert all("missing_event_table" not in item for item in summary)
    assert all("ShopBuyItem" not in item for item in summary)
    assert "订单金额统一使用 event_props.amount" in context


def test_tracking_prompt_projects_only_default_and_question_matched_fields_without_mutating_config() -> None:
    """
    是什么：字段投影保留默认字段和支付问题命中的金额字段，不携带无关战斗字段。
    """
    config = _tracking_config()
    original_fields = deepcopy(config.fields)

    context, _summary = build_tracking_prompt_context(config, question="分析支付金额")

    assert "`event_log.uid`" in context
    assert "`event_log.event_name`" in context
    assert "`event_log.event_props.amount`" in context
    assert "`event_log.event_props.battle_result`" not in context
    assert config.fields == original_fields


def test_tracking_prompt_keeps_data_skill_referenced_field_when_question_uses_business_term() -> None:
    """
    是什么：问题未出现物理字段名时，Data Skill 引用仍应保留对应字段语义。
    """
    context, _summary = build_tracking_prompt_context(
        _tracking_config(),
        question="分析收入趋势",
        data_skill_text="收入指标使用 event_props.amount 计算。",
    )

    assert "`event_log.event_props.amount`" in context
    assert "`event_log.event_props.battle_result`" not in context
