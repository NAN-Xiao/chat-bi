"""
脚本说明：验证看板 SQL 预览在数据权限场景下不复用旧缓存。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import DashboardSqlPreview


def _request(cache_only: bool = False) -> DashboardSqlPreview:
    return DashboardSqlPreview(
        datasource=1,
        sql="select day, revenue from fact_payments",
        cache_only=cache_only,
    )


def _user():
    return SimpleNamespace(id=1001, tenant_id=2001)


def test_preview_sql_checks_permission_before_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：权限校验失败时，看板预览不能先命中历史缓存。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
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

    result = dashboard_service.preview_sql(object(), _user(), _request())

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["message"] == "没有查看权限"
    assert result["data"] == []


def test_preview_sql_cache_only_misses_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：命中任意数据权限时，cache_only 请求不能返回旧缓存。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args, **_kwargs: (None, True))

    def _unexpected_cache_get(*_args, **_kwargs):
        raise AssertionError("权限命中时 cache_only 不应读取旧缓存")

    monkeypatch.setattr(dashboard_service, "_dashboard_sql_preview_cache_get", _unexpected_cache_get)

    result = dashboard_service.preview_sql(object(), _user(), _request(cache_only=True))

    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_cache_miss"
    assert result["data"] == []


def test_preview_sql_does_not_write_cache_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：命中任意数据权限时，即使实时执行成功也不能把结果写入共享预览缓存。
    """
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
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

    result = dashboard_service.preview_sql(object(), _user(), _request())

    assert result["status"] == "success"
    assert result["data"] == [{"day": "2026-06-30", "revenue": 12.5}]
