"""
脚本说明：验证工作空间埋点配置在 SQL 生成时按问题投影，不修改原始数据字典。
"""
from __future__ import annotations

from copy import deepcopy

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
            ),
        ],
        event_name_mappings=[
            {
                "event_name": "login",
                "event_display_name": "登录",
                "event_category": "基础事件",
                "properties": [
                    {"property_name": "duration_seconds", "property_display_name": "停留时长"},
                ],
            },
            {
                "event_name": "pay_success",
                "event_display_name": "支付成功",
                "event_category": "付费事件",
                "properties": [
                    {"property_name": "transaction_id", "property_display_name": "订单号"},
                ],
            },
        ],
    )


def test_tracking_prompt_keeps_only_matched_event_properties_without_mutating_config() -> None:
    """
    是什么：问题命中登录事件时，只投影登录属性，完整事件配置仍保持不变。
    """
    config = _tracking_config()
    original_mappings = deepcopy(config.event_name_mappings)

    context, _summary = build_tracking_prompt_context(config, question="分析登录停留时长")

    assert "duration_seconds" in context
    assert "transaction_id" not in context
    assert "pay_success" in context
    assert config.event_name_mappings == original_mappings


def test_tracking_prompt_omits_event_properties_when_question_has_no_event_match() -> None:
    """
    是什么：未命中任何事件时仍保留轻量事件目录，但不注入无关事件属性。
    """
    context, _summary = build_tracking_prompt_context(_tracking_config(), question="最近 30 天 LTV")

    assert "login" in context
    assert "pay_success" in context
    assert "duration_seconds" not in context
    assert "transaction_id" not in context
    assert "`event_log.uid`" in context


def test_tracking_prompt_keeps_lightweight_match_when_full_properties_exceed_budget() -> None:
    """
    是什么：命中事件的属性超出预算时，仍保留事件目录，不能让事件从上下文中静默消失。
    """
    config = _tracking_config()
    config.event_name_mappings[0]["properties"] = [
        {"property_name": "oversized_property", "description": "x" * 20_000},
    ]

    context, _summary = build_tracking_prompt_context(config, question="分析登录事件")

    assert "login" in context
    assert "oversized_property" not in context


def test_tracking_prompt_keeps_complete_event_inventory_when_details_fill_budget() -> None:
    """
    是什么：事件详情占满投影预算时，完整事件目录仍应作为独立紧凑清单保留。
    """
    config = _tracking_config()
    config.event_name_mappings[1]["properties"] = [
        {"property_name": "large_property", "description": "x" * 15_500},
    ]

    context, _summary = build_tracking_prompt_context(
        config,
        question="分析支付成功事件",
    )

    assert '<Configured-Event-Names>["login","pay_success"]</Configured-Event-Names>' in context


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


def test_tracking_prompt_includes_only_enabled_event_groups_without_mutating_config() -> None:
    config = _tracking_config().model_copy(
        update={
            "event_groups": [
                TenantTrackingEventGroupDTO(
                    tenant_id=1,
                    group_key="payment_process",
                    group_name="支付流程事件",
                    description="只统计流程量",
                    event_names=["pay_success"],
                    sort_order=20,
                    enabled=True,
                ),
                TenantTrackingEventGroupDTO(
                    tenant_id=1,
                    group_key="disabled_group",
                    group_name="停用分组",
                    event_names=["login"],
                    sort_order=10,
                    enabled=False,
                ),
            ]
        }
    )
    original_mappings = deepcopy(config.event_name_mappings)

    context, summary = build_tracking_prompt_context(config)

    assert "## 事件分组" in context
    assert "payment_process" in context
    assert "pay_success" in context
    assert "disabled_group" not in context
    assert any("事件分组" in item and "payment_process" in item for item in summary)
    assert config.event_name_mappings == original_mappings
