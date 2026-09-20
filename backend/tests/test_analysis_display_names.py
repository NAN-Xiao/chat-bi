import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest, DashboardAiSqlGenerateResponse


@pytest.mark.parametrize("model,key", [("event", "ac"), ("property", "property_metric_1")])
@pytest.mark.parametrize("name", ["ac", "reg", "123", "order", "指标1", "收入 / 用户", 'a"b`c'])
def test_explicit_metric_display_name_survives_normalization_and_response(model, key, name):
    request = DashboardAiSqlGenerateRequest(datasource=1, context={
        "analysisModel": model,
        "metrics": [{"alias": "ac", "displayName": name, "label": "指标1.总次数"}],
    })
    normalized = generator._normalize_manual_config(request)
    response = generator._node_finalize_response({
        "normalized_config": normalized,
        "response": DashboardAiSqlGenerateResponse(success=True),
    })["response"]
    assert response.result_config["display_names"][key] == name
    assert normalized["metrics"][0]["alias"] == "ac"


@pytest.mark.parametrize("value,expected", [
    ({"displayName": "ac", "alias": "chart_metric_1", "label": "指标1.总次数"}, "ac"),
    ({"alias": "ac", "label": "指标1.总次数"}, "ac"),
    ({"displayName": "amount", "comment": "金额"}, "amount"),
    ({"display_name": "123", "comment": "金额"}, "123"),
    ({"displayName": " ", "alias": "", "label": "用户数"}, "用户数"),
    ({}, "默认名称"),
])
def test_display_name_priority_is_independent_of_language(value, expected):
    assert generator._configured_display_name(value, "默认名称") == expected


@pytest.mark.parametrize("model,config,key,expected", [
    ("event", {"formula_metrics": [{"alias": "ratio", "displayName": "value / count", "label": "比率"}]}, "ratio", "value / count"),
    ("ranking", {"ranking": {"simultaneousMetrics": [{"alias": "order", "displayName": "order", "label": "次数"}]}}, "simultaneous_metric_1", "order"),
    ("ranking", {"ranking": {"entityField": {"displayName": "account", "comment": "账号"}}}, "ranking_entity", "account"),
    ("retention", {"retention": {"simultaneous": {"enabled": True, "metricField": {"displayName": "amount", "comment": "金额"}}}}, "simultaneous_value", "amount"),
    ("distribution", {"distribution": {"simultaneous": {"enabled": True, "metricField": {"displayName": "amount", "comment": "金额"}}}}, "simultaneous_value", "amount"),
    ("revenue", {"revenue": {"metric": {"method": "property_sum", "field": {"displayName": "amount", "comment": "金额"}}}}, "day_0", "第0日amount合计"),
    ("heatmap", {"heatmap": {"xField": {"displayName": "east", "comment": "横坐标"}}}, "heatmap_x", "east"),
    ("interval", {"groups": [{"displayName": "channel", "comment": "渠道"}]}, "group_1", "channel"),
    ("attribution", {"groups": [{"displayName": "channel", "comment": "渠道"}]}, "group_1", "channel"),
])
def test_models_respect_configured_names(model, config, key, expected):
    assert generator._analysis_result_display_names(config, model)[key] == expected


def test_interval_aliases_round_trip_without_changing_event_conditions_or_fixed_columns():
    config = generator._normalize_manual_config(DashboardAiSqlGenerateRequest(datasource=1, context={
        "analysisModel": "interval",
        "interval": {"startEventAlias": "select", "endEventAlias": "order", "startEvent": {"eventName": "start"}, "endEvent": {"eventName": "finish"}},
    }))
    response = generator._node_finalize_response({"normalized_config": config, "response": DashboardAiSqlGenerateResponse(success=True)})["response"]
    assert response.result_config["start_event_alias"] == "select"
    assert response.result_config["end_event_alias"] == "order"
    assert response.result_config["display_names"]["interval_count"] == "有效间隔数"
    assert config["interval"]["startEvent"]["eventName"] == "start"
    assert config["interval"]["endEvent"]["eventName"] == "finish"
