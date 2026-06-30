import os
from types import SimpleNamespace

import pytest

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.dashboard.crud import dashboard_service
from common.core.config import settings
from common.core.redis_client import (
    datasource_redis_key,
    platform_redis_key,
    tenant_redis_key,
    user_redis_key,
)


def test_scoped_redis_key_helpers_build_predictable_namespaces(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_KEY_PREFIX", "test")

    assert platform_redis_key("auth", "login") == "test:platform:auth:login"
    assert tenant_redis_key(42, "rate_limit", "chat") == "test:tenant:42:rate_limit:chat"
    assert user_redis_key(42, 7, "dashboard") == "test:tenant:42:user:7:dashboard"
    assert datasource_redis_key(42, 3, "schema") == "test:tenant:42:datasource:3:schema"


@pytest.mark.parametrize(
    ("builder", "args", "message"),
    [
        (tenant_redis_key, (None, "x"), "Tenant context is required"),
        (user_redis_key, (42, None, "x"), "User context is required"),
        (datasource_redis_key, (42, None, "x"), "Datasource context is required"),
    ],
)
def test_scoped_redis_key_helpers_require_scope_context(builder, args, message):
    with pytest.raises(ValueError, match=message):
        builder(*args)


def test_dashboard_sql_preview_cache_key_is_user_and_datasource_scoped(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_KEY_PREFIX", "test")
    user = SimpleNamespace(id=7, tenant_id=42)

    cache_key = dashboard_service._dashboard_sql_preview_cache_key(
        current_user=user,
        datasource_id=3,
        sql=" select 1 ",
        pivot={"enabled": True, "time_field": "dt"},
    )

    assert cache_key.memory_key.startswith("42:7:3:")
    assert dashboard_service._dashboard_sql_preview_redis_key(cache_key).startswith(
        "test:tenant:42:user:7:datasource:3:dashboard:sql_preview:"
    )


def test_dashboard_sql_preview_cache_key_changes_across_tenant_user_and_datasource():
    base = dashboard_service._dashboard_sql_preview_cache_key(
        current_user=SimpleNamespace(id=7, tenant_id=42),
        datasource_id=3,
        sql="select 1",
        pivot=None,
    )
    same_user_other_tenant = dashboard_service._dashboard_sql_preview_cache_key(
        current_user=SimpleNamespace(id=7, tenant_id=43),
        datasource_id=3,
        sql="select 1",
        pivot=None,
    )
    same_tenant_other_user = dashboard_service._dashboard_sql_preview_cache_key(
        current_user=SimpleNamespace(id=8, tenant_id=42),
        datasource_id=3,
        sql="select 1",
        pivot=None,
    )
    same_user_other_datasource = dashboard_service._dashboard_sql_preview_cache_key(
        current_user=SimpleNamespace(id=7, tenant_id=42),
        datasource_id=4,
        sql="select 1",
        pivot=None,
    )

    assert len({
        base.memory_key,
        same_user_other_tenant.memory_key,
        same_tenant_other_user.memory_key,
        same_user_other_datasource.memory_key,
    }) == 4
