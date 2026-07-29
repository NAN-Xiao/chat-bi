"""
脚本说明：验证看板 SQL 预览在数据权限场景下不复用旧缓存。
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from apps.dashboard.crud import dashboard_service
from apps.dashboard.crud.dashboard_date_filter import (
    prepare_dashboard_date_filter,
    validate_dashboard_date_parameter_sql,
)
from apps.dashboard.models.dashboard_model import CoreDashboard, DashboardPivotRequest, DashboardSqlPreview


def _request(cache_only: bool = False) -> DashboardSqlPreview:
    return DashboardSqlPreview(
        datasource=1,
        sql="select day, revenue from fact_payments",
        cache_only=cache_only,
    )


def _user():
    return SimpleNamespace(id=1001, tenant_id=2001)


def _session():
    return SimpleNamespace(get=lambda *_args: SimpleNamespace(id=1, type="pg"))


def test_date_parameter_sql_requires_exact_configured_token_pair() -> None:
    assert validate_dashboard_date_parameter_sql(
        "select * from event where dt between "
        "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        "yyyymmdd_number",
    ) is None
    assert (
        validate_dashboard_date_parameter_sql("select * from event where dt >= 20260101", "yyyymmdd_number")
        == "missing_parameters"
    )
    assert validate_dashboard_date_parameter_sql(
        "select * from event where dt between "
        "{{dashboard_start_date}} and {{dashboard_end_date}}",
        "yyyymmdd_number",
    ) == "parameter_type_mismatch"


def test_date_parameter_sql_infers_end_only_mode() -> None:
    assert validate_dashboard_date_parameter_sql(
        "select * from event where dt <= {{dashboard_end_yyyymmdd}}",
        "yyyymmdd_number",
    ) is None


def test_date_parameter_sql_rejects_start_only_mode() -> None:
    assert validate_dashboard_date_parameter_sql(
        "select * from event where dt >= {{dashboard_start_yyyymmdd}}",
        "yyyymmdd_number",
    ) == "incomplete_parameters"


def test_end_only_sql_does_not_need_pivot_date_parameter_mode() -> None:
    pivot = DashboardPivotRequest.model_validate(
        {
            "time_field": "dt",
            "date_parameter_type": "yyyymmdd_number",
        }
    )

    prepared = prepare_dashboard_date_filter(
        "select * from `user` where dt = {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot=pivot,
        today=date(2026, 7, 29),
    )

    assert prepared.capability["status"] == "available"
    assert "20260728" in prepared.sql


def _allow_chart_execution_datasource(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: None)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: int(datasource_id),
    )


def test_bound_datasource_requires_time_field_only_for_enabled_pivot(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """绑定数据源只在启用透视聚合时要求配置时间字段。"""
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_is_bound_datasource",
        lambda *_args, **_kwargs: True,
    )

    assert not dashboard_service._dashboard_requires_pivot_time_field(
        _session(),
        _user(),
        1,
        {"enabled": False, "time_field": ""},
    )
    assert dashboard_service._dashboard_requires_pivot_time_field(
        _session(),
        _user(),
        1,
        {"enabled": True, "time_field": ""},
    )

    sql = (
        "select * from `event` where dt between "
        "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
    )
    non_pivot = {"enabled": False, "time_field": "", "date_parameter_type": "yyyymmdd_number"}
    non_pivot_prepared = dashboard_service._prepare_dashboard_chart_query(
        SimpleNamespace(type="mysql"),
        sql,
        non_pivot,
        require_time_field=dashboard_service._dashboard_requires_pivot_time_field(
            _session(), _user(), 1, non_pivot
        ),
    )
    pivot_prepared = dashboard_service._prepare_dashboard_chart_query(
        SimpleNamespace(type="mysql"),
        sql,
        {"enabled": True, "time_field": "", "date_parameter_type": "yyyymmdd_number"},
        require_time_field=dashboard_service._dashboard_requires_pivot_time_field(
            _session(),
            _user(),
            1,
            {"enabled": True, "time_field": "", "date_parameter_type": "yyyymmdd_number"},
        ),
    )

    assert non_pivot_prepared.date_filter_capability["status"] == "available"
    assert "{{dashboard_start_yyyymmdd}}" not in non_pivot_prepared.source_sql
    assert pivot_prepared.date_filter_capability == {
        "status": "unconfigured",
        "reason": "missing_time_field",
    }


def test_date_filter_cache_key_uses_rendered_dates_and_parameter_type() -> None:
    sql = (
        "select dt from orders where dt between "
        "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
    )
    number_pivot = DashboardPivotRequest(
        time_field="dt",
        date_parameter_type="yyyymmdd_number",
    )
    text_pivot = number_pivot.model_copy(update={"date_parameter_type": "yyyymmdd_text"})
    day_one = prepare_dashboard_date_filter(
        sql, ds_type="mysql", pivot=number_pivot, today=date(2026, 7, 27)
    )
    day_two = prepare_dashboard_date_filter(
        sql, ds_type="mysql", pivot=number_pivot, today=date(2026, 7, 28)
    )
    text_range = prepare_dashboard_date_filter(
        sql, ds_type="mysql", pivot=text_pivot, today=date(2026, 7, 27)
    )
    keys = [
        dashboard_service._dashboard_sql_preview_cache_key(_user(), 1, prepared.sql, pivot)
        for prepared, pivot in (
            (day_one, number_pivot),
            (day_two, number_pivot),
            (text_range, text_pivot),
        )
    ]
    assert len({key.fingerprint for key in keys}) == 3
    same_key = dashboard_service._dashboard_sql_preview_cache_key(
        _user(), 1, day_one.sql, number_pivot
    )
    assert same_key.fingerprint == keys[0].fingerprint


def test_date_expression_is_preserved_by_pivot_request_and_separates_cache_keys() -> None:
    sql = (
        "select dt from orders where dt between "
        "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
    )
    today_pivot = DashboardPivotRequest(
        enabled=False,
        time_field="dt",
        date_parameter_type="yyyymmdd_number",
        date_expression={"version": 1, "mode": "preset", "preset": "today"},
    )
    past_pivot = today_pivot.model_copy(
        update={
            "date_expression": {"version": 1, "mode": "preset", "preset": "past_30_days"},
        }
    )
    rendered_today_sql = prepare_dashboard_date_filter(
        sql, ds_type="mysql", pivot=today_pivot, today=date(2026, 7, 28)
    ).sql
    rendered_past_sql = prepare_dashboard_date_filter(
        sql, ds_type="mysql", pivot=past_pivot, today=date(2026, 7, 28)
    ).sql

    assert today_pivot.date_expression == {"version": 1, "mode": "preset", "preset": "today"}
    assert (
        dashboard_service._dashboard_sql_preview_cache_key(
            _user(), 7, rendered_today_sql, today_pivot
        ).fingerprint
        != dashboard_service._dashboard_sql_preview_cache_key(
            _user(), 7, rendered_past_sql, past_pivot
        ).fingerprint
    )


def test_date_filter_cache_key_explicitly_separates_resolved_expression_context() -> None:
    pivot = DashboardPivotRequest(time_field="dt", date_parameter_type="yyyymmdd_number")
    base_context = {
        "timezone": "Asia/Shanghai",
        "resolvedStart": "2026-07-28",
        "resolvedEnd": "2026-07-28",
        "expression": {"version": 1, "mode": "preset", "preset": "today"},
        "parameterType": "yyyymmdd_number",
    }
    contexts = [
        base_context,
        {**base_context, "timezone": "UTC"},
        {**base_context, "resolvedStart": "2026-07-27"},
        {**base_context, "resolvedEnd": "2026-07-29"},
        {
            **base_context,
            "expression": {"version": 1, "mode": "preset", "preset": "past_30_days"},
        },
        {**base_context, "parameterType": "yyyymmdd_text"},
    ]

    fingerprints = {
        dashboard_service._dashboard_sql_preview_cache_key(
            _user(),
            7,
            "select dt from orders where dt between 20260728 and 20260728",
            pivot,
            date_filter_capability=context,
        ).fingerprint
        for context in contexts
    }

    assert len(fingerprints) == len(contexts)


def test_preview_sql_checks_permission_before_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：权限校验失败时，看板预览不能先命中历史缓存。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    _allow_chart_execution_datasource(monkeypatch)
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_chart_permission_audit",
        lambda *_args, **_kwargs: (
            dashboard_service._failed_chart_result(
                "SQL 超出当前数据权限范围",
                "permission_denied",
            ),
            False,
        ),
    )

    def _unexpected_cache_get(*_args, **_kwargs):
        raise AssertionError("权限失败前不应读取看板缓存")

    monkeypatch.setattr(dashboard_service, "_dashboard_sql_preview_cache_get", _unexpected_cache_get)

    result = dashboard_service.preview_sql(_session(), _user(), _request())

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["message"] == "没有查看权限"
    assert result["data"] == []


def test_preview_sql_cache_only_misses_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：命中任意数据权限时，cache_only 请求不能返回旧缓存。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    _allow_chart_execution_datasource(monkeypatch)
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args, **_kwargs: (None, True))

    def _unexpected_cache_get(*_args, **_kwargs):
        raise AssertionError("权限命中时 cache_only 不应读取旧缓存")

    monkeypatch.setattr(dashboard_service, "_dashboard_sql_preview_cache_get", _unexpected_cache_get)

    result = dashboard_service.preview_sql(_session(), _user(), _request(cache_only=True))

    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_cache_miss"
    assert result["data"] == []


def test_preview_sql_does_not_write_cache_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：命中任意数据权限时，即使实时执行成功也不能把结果写入共享预览缓存。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    _allow_chart_execution_datasource(monkeypatch)
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args, **_kwargs: (None, True))
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *_args, **_kwargs: {
            "status": "success",
            "fields": ["day", "revenue"],
            "data": [{"day": "2026-06-30", "revenue": 12.5}],
            "message": "",
        },
    )

    def _unexpected_cache_set(*_args, **_kwargs):
        raise AssertionError("权限命中时不应写入看板缓存")

    monkeypatch.setattr(dashboard_service, "_dashboard_sql_preview_cache_set", _unexpected_cache_set)

    result = dashboard_service.preview_sql(_session(), _user(), _request())

    assert result["status"] == "success"
    assert result["data"] == [{"day": "2026-06-30", "revenue": 12.5}]


def test_dashboard_payload_without_data_strips_saved_chart_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：看板初始加载不能先把保存的图表快照发给前端，再等待异步权限检查覆盖。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    _allow_chart_execution_datasource(monkeypatch)
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args, **_kwargs: (None, False))
    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(dashboard_service, "_can_edit_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_share_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_set_default_dashboard", lambda *_args, **_kwargs: False)

    record = CoreDashboard(
        id="dashboard-1",
        tenant_id=2001,
        name="核心看板",
        pid="root",
        datasource=1,
        node_type="leaf",
        type="dashboard",
        canvas_style_data="{}",
        component_data="[]",
        canvas_view_info=json.dumps(
            {
                "chart-1": {
                    "id": "chart-1",
                    "datasource": 1,
                    "sql": "select day, revenue from fact_payments",
                    "status": "success",
                    "fields": ["day", "revenue"],
                    "data": {
                        "fields": ["day", "revenue"],
                        "data": [{"day": "2026-06-30", "revenue": 12.5}],
                    },
                }
            }
        ),
        status=1,
        is_default=1,
        delete_flag=0,
    )

    result = dashboard_service._dashboard_payload(
        _session(),
        _user(),
        record,
        default_context=True,
        include_data=False,
    )

    chart = json.loads(result["canvas_view_info"])["chart-1"]
    assert chart["status"] == "loading"
    assert chart["dataState"] == "loading"
    assert chart["fields"] == []
    assert chart["data"]["fields"] == []
    assert chart["data"]["data"] == []


def test_dashboard_payload_with_data_executes_sql_engine_instead_of_saved_snapshot(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：看板加载真实数据时必须走 SQL Engine 刷新，不能直接回显保存的旧图表快照。
    """
    calls: list[tuple[int, str]] = []

    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    _allow_chart_execution_datasource(monkeypatch)
    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(dashboard_service, "_can_edit_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_share_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_set_default_dashboard", lambda *_args, **_kwargs: False)

    def _execute(_session, _user, datasource_id, sql, pivot=None):
        calls.append((datasource_id, sql))
        return {
            "status": "success",
            "fields": ["day", "revenue"],
            "data": [{"day": "2026-07-01", "revenue": 20}],
            "message": "",
        }

    monkeypatch.setattr(dashboard_service, "_execute_dashboard_chart_sql", _execute)

    record = CoreDashboard(
        id="dashboard-1",
        tenant_id=2001,
        name="核心看板",
        pid="root",
        datasource=1,
        node_type="leaf",
        type="dashboard",
        canvas_style_data="{}",
        component_data="[]",
        canvas_view_info=json.dumps(
            {
                "chart-1": {
                    "id": "chart-1",
                    "datasource": 1,
                    "sql": "select day, revenue from fact_payments",
                    "status": "success",
                    "fields": ["day", "revenue"],
                    "data": {
                        "fields": ["day", "revenue"],
                        "data": [{"day": "2026-06-30", "revenue": 12.5}],
                    },
                }
            }
        ),
        status=1,
        is_default=1,
        delete_flag=0,
    )

    result = dashboard_service._dashboard_payload(
        _session(),
        _user(),
        record,
        default_context=True,
        include_data=True,
    )

    chart = json.loads(result["canvas_view_info"])["chart-1"]
    assert calls == [(1, "select day, revenue from fact_payments")]
    assert chart["data"]["data"] == [{"day": "2026-07-01", "revenue": 20}]
