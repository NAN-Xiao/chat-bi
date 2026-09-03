from types import SimpleNamespace

from apps.dashboard.crud import ai_sql_generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


def _event(name: str):
    return {
        "kind": "tracking-event",
        "eventTable": "event",
        "eventNameField": "event_name",
        "eventName": name,
        "field": "event_name",
    }


def _property(name: str, event_name: str):
    return {
        "kind": "tracking-property",
        "table": "event",
        "field": name,
        "eventName": event_name,
        "propertyType": "numeric",
    }


def _revenue_request(**overrides):
    revenue = {
        "entityField": {"kind": "field", "table": "event", "field": "user_id"},
        "initialEvent": _event("login"),
        "paymentEvent": _event("purchase"),
        "metric": {"method": "property_sum", "field": _property("amount", "purchase")},
        "cost": {"enabled": False, "field": None},
        "observationDays": 30,
    }
    revenue.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="table",
        context={
            "analysisModel": "revenue",
            "chart": {"type": "table"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "revenue": revenue,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def test_revenue_config_is_normalized_and_validated_independently():
    request = _revenue_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "amount", "dt"}},
    )

    assert normalized["analysis_model"] == "revenue"
    assert normalized["revenue"]["observationDays"] == 30
    assert normalized["retention"] == {}
    assert normalized["funnel"] == {}
    assert normalized["distribution"] == {}
    assert normalized["interval"] == {}
    assert normalized["path"] == {}
    assert result.success is True
    assert result.analysis_model == "revenue"
    assert ai_sql_generator._config_reference_table_names(normalized, {}) == {"event"}


def test_revenue_rejects_missing_numeric_metric_cost_and_observation_window():
    request = _revenue_request(
        metric={"method": "property_avg", "field": None},
        cost={"enabled": True, "field": None},
        observationDays=366,
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
    )

    assert result.success is False
    assert "收入分析使用事件属性口径时，请先选择数值属性。" in result.issues
    assert "收入分析启用成本数据时，请先选择成本字段。" in result.issues
    assert "收入分析观察时长必须是 1 到 365 天。" in result.issues


def test_revenue_prompt_plan_and_result_contract_keep_cohort_semantics():
    request = _revenue_request(observationDays=7)
    normalized = ai_sql_generator._normalize_manual_config(request)
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("revenue")
    plan = ai_sql_generator._build_sql_plan(normalized, ai_sql_generator._build_formula_ir(normalized))
    valid_sql = (
        "WITH cohort AS (SELECT DISTINCT user_id, dt AS cohort_date FROM event), "
        "daily AS (SELECT SUM(amount) AS revenue_value FROM event) "
        "SELECT cohort_date, COUNT(DISTINCT user_id) AS cohort_size, "
        "0 AS day_0, 1 AS day_1, 2 AS day_2, 3 AS day_3, 4 AS day_4, "
        "5 AS day_5, 6 AS day_6, 7 AS day_7 FROM cohort GROUP BY cohort_date"
    )

    assert "只能使用 revenue 配置" in prompt
    assert "同期 Cohort" in prompt
    assert plan["analysis_model"] == "revenue"
    assert plan["result_contract"]["type"] == "revenue_cohort_table"
    assert plan["result_contract"]["date_field"] == "cohort_date"
    assert plan["result_contract"]["required_columns"] == [
        "cohort_date", "cohort_size", "day_0", "day_1", "day_2", "day_3",
        "day_4", "day_5", "day_6", "day_7",
    ]
    assert ai_sql_generator._revenue_sql_result_issues(valid_sql, normalized) == []
    assert ai_sql_generator._revenue_sql_result_issues("SELECT cohort_date FROM event", normalized)


def test_revenue_prompt_and_validation_require_displayable_cohort_date():
    request = _revenue_request(observationDays=1)
    normalized = ai_sql_generator._normalize_manual_config(request)
    datasource = SimpleNamespace(name="测试", type="mysql", type_name="MySQL")
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        datasource,
        "",
        "",
        sql_dialect="mysql",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("revenue")
    remaining_columns = "COUNT(DISTINCT user_id) AS cohort_size, SUM(amount) AS day_0, 0 AS day_1"
    invalid_sql = f"SELECT dt AS cohort_date, {remaining_columns} FROM event GROUP BY dt"
    valid_sql = f"""
        SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS cohort_date, {remaining_columns}
        FROM event
        GROUP BY STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d')
    """

    assert "cohort_date 必须输出真实 DATE 或 YYYY-MM-DD 日期文本" in prompt
    invalid_issues = ai_sql_generator._revenue_sql_result_issues(
        invalid_sql,
        normalized,
        sql_dialect="mysql",
        datasource=datasource,
    )
    assert any("cohort_date" in issue and "YYYYMMDD" in issue for issue in invalid_issues)
    assert ai_sql_generator._revenue_sql_result_issues(
        valid_sql,
        normalized,
        sql_dialect="mysql",
        datasource=datasource,
    ) == []
