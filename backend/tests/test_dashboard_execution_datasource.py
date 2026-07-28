"""验证看板图表执行数据源只能来自当前工作空间的绑定与 ROI 配置。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import CoreDashboard, DashboardSqlPreview
from apps.datasource.crud import sql_engine_executor


class _Session:
    def get(self, _model, datasource_id: int):
        return SimpleNamespace(
            id=datasource_id,
            name=f"数据源{datasource_id}",
            type="mysql",
            type_name="MySQL",
            status="success",
        )


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _MetadataSession(_Session):
    def __init__(self):
        self.tables = [
            SimpleNamespace(
                id=301,
                ds_id=22,
                checked=True,
                table_name="roi_metric",
                table_comment="ROI 指标",
                custom_comment="",
            )
        ]
        self.fields = [
            SimpleNamespace(
                id=401,
                ds_id=22,
                table_id=301,
                checked=True,
                field_name="amount",
                field_type="decimal",
                field_comment="金额",
                custom_comment="",
                field_index=1,
            )
        ]

    def query(self, model):
        return _Query(self.tables if model.__name__ == "CoreTable" else self.fields)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1001, tenant_id=2001)


def _report_target_dashboard(*, view_datasource: int | None) -> SimpleNamespace:
    return SimpleNamespace(
        id="dashboard-1",
        tenant_id=2001,
        datasource=11,
        component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
        canvas_view_info=json.dumps({"chart-1": {"datasource": view_datasource}}),
    )


def test_report_target_uses_saved_roi_drawer_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """报表解读应使用保存的 ROI 图表抽屉数据源。"""
    resolved_ids: list[int | None] = []
    record = _report_target_dashboard(view_datasource=22)
    monkeypatch.setattr(dashboard_service, "_load_dashboard_or_404", lambda *_args: record)
    monkeypatch.setattr(dashboard_service, "_can_view_dashboard_resource", lambda *_args: True)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 11)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_ids.append(datasource_id) or 22,
    )

    dashboard_service.validate_dashboard_report_target(
        _Session(), _user(), "dashboard-1", 11, ["chart-1"]
    )

    assert resolved_ids == [22]


def test_report_target_falls_back_to_dashboard_datasource_without_drawer_value(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有抽屉数据源时，报表解读应回退到看板数据源。"""
    resolved_ids: list[int | None] = []
    record = _report_target_dashboard(view_datasource=None)
    monkeypatch.setattr(dashboard_service, "_load_dashboard_or_404", lambda *_args: record)
    monkeypatch.setattr(dashboard_service, "_can_view_dashboard_resource", lambda *_args: True)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 11)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_ids.append(datasource_id) or 11,
    )

    dashboard_service.validate_dashboard_report_target(
        _Session(), _user(), "dashboard-1", 22, ["chart-1"]
    )

    assert resolved_ids == [11]


def test_chart_execution_datasources_include_only_bound_and_roi(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """候选集只能包含当前空间的绑定数据源和 ROI 数据源。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)

    options = dashboard_service.list_chart_execution_datasources(_Session(), _user())

    assert [(item.id, item.role) for item in options] == [(11, "bound"), (22, "roi")]


def test_date_filter_validation_only_applies_to_bound_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """日期参数完整性只约束工作空间绑定数据源。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)

    assert dashboard_service._dashboard_is_bound_datasource(_Session(), _user(), 11) is True
    assert dashboard_service._dashboard_is_bound_datasource(_Session(), _user(), 22) is False


def test_roi_chart_execution_datasource_does_not_require_user_grant(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空间已配置的 ROI 数据源不依赖用户级数据源授权。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)

    def ensure_bound_access(_session, _user, datasource_id, **_kwargs):
        if datasource_id == 22:
            raise HTTPException(status_code=403, detail="用户未被单独授权")
        return datasource_id

    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", ensure_bound_access)

    options = dashboard_service.list_chart_execution_datasources(_Session(), _user())

    assert [(item.id, item.role) for item in options] == [(11, "bound"), (22, "roi")]
    assert dashboard_service.resolve_chart_execution_datasource(_Session(), _user(), 22) == 22


def test_chart_execution_datasources_deduplicate_roi_matching_bound(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROI 数据源与绑定数据源相同不会产生重复选项。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)

    options = dashboard_service.list_chart_execution_datasources(_Session(), _user())

    assert [(item.id, item.role) for item in options] == [(11, "bound")]


def test_chart_execution_datasource_rejects_id_outside_current_workspace(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """构造其他空间或平台数据源 ID 必须被服务端拒绝。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)

    with pytest.raises(HTTPException, match="当前空间未配置该图表执行数据源") as error:
        dashboard_service.resolve_chart_execution_datasource(_Session(), _user(), 99)

    assert error.value.status_code == 403


def test_dashboard_sql_preview_uses_resolved_chart_execution_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预览 SQL 必须执行服务端解析后的图表数据源。"""
    resolved_calls: list[int] = []
    execute_calls: list[int] = []
    monkeypatch.setattr(dashboard_service, "_dashboard_is_bound_datasource", lambda *_args: False)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_calls.append(datasource_id) or 22,
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 11)
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_chart_permission_audit",
        lambda *_args, **_kwargs: (None, False),
    )
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, datasource_id, *_args, **_kwargs: execute_calls.append(datasource_id) or {
            "status": "success",
            "fields": ["value"],
            "data": [{"value": 1}],
            "message": "",
        },
    )

    result = dashboard_service.preview_sql(
        _Session(),
        _user(),
        DashboardSqlPreview(datasource=22, sql="select 1", force_refresh=True),
    )

    assert result["status"] == "success"
    assert resolved_calls == [22]
    assert execute_calls == [22]


def test_dashboard_sql_preview_skips_date_parameter_gate_for_unbound_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非绑定数据源不因缺少时间字段阻断原 SQL 预览。"""
    executed_sql: list[str] = []
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, _datasource_id: 22,
    )
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args, **_kwargs: (None, False))
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, _datasource, sql, *_args, **_kwargs: executed_sql.append(sql) or {
            "status": "success",
            "fields": ["dt", "value"],
            "data": [{"dt": "2026-07-28", "value": 1}],
            "message": "",
        },
    )

    result = dashboard_service.preview_sql(
        _Session(),
        _user(),
        DashboardSqlPreview(
            datasource=22,
            sql=(
                "select dt, value from orders where dt between "
                "{{dashboard_start_date}} and {{dashboard_end_date}}"
            ),
            pivot={"time_field": "", "date_parameter_type": "date"},
            force_refresh=True,
        ),
    )

    assert result["status"] == "success"
    assert result["date_filter_capability"]["status"] == "available"
    assert executed_sql and "{{dashboard_start_date}}" not in executed_sql[0]
    assert executed_sql and "{{dashboard_end_date}}" not in executed_sql[0]


def test_dashboard_sql_preview_keeps_date_parameter_gate_for_bound_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """绑定数据源仍需完整配置日期参数。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, _datasource_id: 11,
    )

    result = dashboard_service.preview_sql(
        _Session(),
        _user(),
        DashboardSqlPreview(
            datasource=11,
            sql=(
                "select dt, value from orders where dt between "
                "{{dashboard_start_date}} and {{dashboard_end_date}}"
            ),
            pivot={"time_field": "", "date_parameter_type": "date"},
            force_refresh=True,
        ),
    )

    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_date_filter_unconfigured"


def test_dashboard_chart_execution_marks_resolved_datasource_as_prevalidated(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """图表执行器不得对已完成空间级 ROI 校验的数据源重复做用户级校验。"""
    execution_options: list[bool] = []
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(
        dashboard_service,
        "execute_user_query",
        lambda *_args, **kwargs: execution_options.append(
            kwargs.get("datasource_access_checked", False)
        ) or {
            "status": "success",
            "fields": ["value"],
            "data": [{"value": 1}],
            "message": "",
        },
    )

    result = dashboard_service._execute_dashboard_chart_sql(
        _Session(), _user(), 22, "select 1"
    )

    assert result["status"] == "success"
    assert execution_options == [True]


def test_dashboard_roi_permission_audit_marks_validation_as_prevalidated(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROI 图表的 SQL 校验不得重复要求用户级数据源授权。"""
    validation_options: list[bool] = []
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(
        dashboard_service,
        "validate_user_query_sql_or_raise",
        lambda *_args, **kwargs: validation_options.append(
            kwargs.get("datasource_access_checked", False)
        ) or ("select 1", {"roi_metric"}),
    )
    monkeypatch.setattr(dashboard_service, "has_applicable_permissions", lambda *_args, **_kwargs: False)

    failure, permissions_apply = dashboard_service._dashboard_chart_permission_audit(
        _Session(),
        SimpleNamespace(id=1001, tenant_id=2001, system_role="viewer", tenant_role="member"),
        22,
        "select 1",
    )

    assert failure is None
    assert permissions_apply is False
    assert validation_options == [True]


def test_prevalidated_roi_sql_validation_skips_user_permission_scope(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROI 图表仍校验表字段，但不应用用户级表字段权限范围。"""
    scope_options: list[bool] = []
    datasource = SimpleNamespace(id=22, type="mysql")
    monkeypatch.setattr(sql_engine_executor, "has_datasource_access", lambda *_args: False)
    monkeypatch.setattr(
        sql_engine_executor,
        "prepare_query_sql",
        lambda *_args, **kwargs: scope_options.append(
            kwargs.get("apply_user_permission_scope", True)
        ) or ("select 1", {"roi_metric"}),
    )

    result = sql_engine_executor.validate_user_query_sql_or_raise(
        _Session(),
        _user(),
        datasource,
        "select 1",
        datasource_access_checked=True,
    )

    assert result == ("select 1", {"roi_metric"})
    assert scope_options == [False]


def test_dashboard_execution_datasource_metadata_uses_roi_space_scope(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROI 图表编辑器的表字段元数据必须由空间级执行数据源校验保护。"""
    resolved_datasources: list[int] = []
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_datasources.append(datasource_id) or 22,
    )

    metadata = dashboard_service.get_chart_execution_datasource_metadata(
        _MetadataSession(), _user(), 22
    )

    assert resolved_datasources == [22]
    assert metadata["id"] == 22
    assert len(metadata["tables"]) == 1
    assert metadata["tables"][0]["id"] == 301
    assert metadata["tables"][0]["table_name"] == "roi_metric"
    assert metadata["tables"][0]["fields"][0]["id"] == 401
    assert metadata["tables"][0]["fields"][0]["field_name"] == "amount"
    assert metadata["tables"][0]["fields"][0]["field_type"] == "decimal"


def test_dashboard_api_exposes_execution_datasource_candidates() -> None:
    """看板 SQL 接口使用空间级执行数据源校验，而非通用数据源装饰器。"""
    from apps.dashboard.api import dashboard_api

    assert hasattr(dashboard_api, "execution_datasources_api")
    assert not hasattr(dashboard_api.sql_preview_api, "__wrapped__")


def test_dashboard_refresh_uses_saved_roi_chart_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已保存的 ROI 图表刷新时必须执行 ROI 数据源，而非被看板默认数据源拒绝。"""
    execute_calls: list[int] = []
    monkeypatch.setattr(dashboard_service, "_dashboard_is_bound_datasource", lambda *_args: False)
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: 11 if datasource_id is None else datasource_id,
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(dashboard_service, "_can_edit_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_share_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_set_default_dashboard", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, datasource_id, *_args, **_kwargs: execute_calls.append(datasource_id) or {
            "status": "success",
            "fields": ["value"],
            "data": [{"value": 1}],
            "message": "",
        },
    )
    record = CoreDashboard(
        id="dashboard-1",
        tenant_id=2001,
        name="任意名称看板",
        pid="root",
        datasource=11,
        node_type="leaf",
        type="dashboard",
        canvas_style_data="{}",
        component_data="[]",
        canvas_view_info=json.dumps({"chart-1": {"id": "chart-1", "datasource": 22, "sql": "select 1"}}),
        status=1,
        delete_flag=0,
    )

    result = dashboard_service._dashboard_payload(
        _Session(),
        _user(),
        record,
        default_context=True,
        include_data=True,
    )

    chart = json.loads(result["canvas_view_info"])["chart-1"]
    assert execute_calls == [22]
    assert chart["data"]["data"] == [{"value": 1}]


def test_canvas_validation_accepts_saved_roi_chart_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存看板时，ROI 图表应通过当前空间候选集校验而非强制等于看板默认数据源。"""
    calls: list[int | None] = []
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: calls.append(datasource_id) or 22,
    )
    dashboard = SimpleNamespace(
        canvas_view_info=json.dumps({"chart-1": {"datasource": 22, "sql": "select 1"}}),
    )

    dashboard_service._validate_canvas_datasources(_Session(), _user(), dashboard)

    assert calls == [22]
    assert json.loads(dashboard.canvas_view_info)["chart-1"]["datasource"] == 22
