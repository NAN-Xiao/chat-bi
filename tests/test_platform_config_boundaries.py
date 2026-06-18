import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from apps.system.api import parameter as parameter_api
from apps.system.api import variable_api
from apps.system.schemas import permission as permission_schema


def _tenant_admin():
    return SimpleNamespace(
        id=2,
        system_role="viewer",
        tenant_id=10,
        tenant_role="owner",
    )


def _platform_admin():
    return SimpleNamespace(
        id=1,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
    )


def _with_request(user):
    request = Request({"type": "http", "headers": []})
    request.state.current_user = user
    return permission_schema.RequestContext.set_request(request)


def test_tenant_admin_cannot_manage_platform_parameters():
    token = _with_request(_tenant_admin())
    try:
        with pytest.raises(HTTPException) as get_exc:
            asyncio.run(parameter_api.get_args(session=None))
        with pytest.raises(HTTPException) as save_exc:
            asyncio.run(parameter_api.save_args(session=None, request=None))

        assert get_exc.value.status_code == 403
        assert save_exc.value.status_code == 403
    finally:
        permission_schema.RequestContext.reset(token)


def test_tenant_admin_cannot_manage_system_variables():
    token = _with_request(_tenant_admin())
    try:
        with pytest.raises(HTTPException) as save_exc:
            asyncio.run(variable_api.save_variable(session=None, user=_tenant_admin(), trans=None, variable=None))
        with pytest.raises(HTTPException) as delete_exc:
            asyncio.run(variable_api.delete_variable(session=None, ids=[1]))
        with pytest.raises(HTTPException) as page_exc:
            asyncio.run(variable_api.pager(session=None, trans=None, pageNum=1, pageSize=20, variable=None))

        assert save_exc.value.status_code == 403
        assert delete_exc.value.status_code == 403
        assert page_exc.value.status_code == 403
    finally:
        permission_schema.RequestContext.reset(token)


def test_platform_admin_can_read_platform_parameters(monkeypatch):
    async def fake_get_parameter_args(session):
        return ["ok"]

    monkeypatch.setattr(parameter_api, "get_parameter_args", fake_get_parameter_args)
    token = _with_request(_platform_admin())
    try:
        assert asyncio.run(parameter_api.get_args(session=None)) == ["ok"]
    finally:
        permission_schema.RequestContext.reset(token)
