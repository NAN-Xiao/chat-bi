import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.system.api import parameter as parameter_api
from apps.system.api import variable_api
from apps.system.crud import system_variable as variable_crud
from apps.system.models.system_variable_model import SystemVariable
from apps.system.schemas.business_access import ensure_chatbi_business_user
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


def _variable_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE system_variable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(128) NOT NULL,
                var_type VARCHAR(128) NOT NULL,
                type VARCHAR(128) NOT NULL,
                value TEXT,
                create_time DATETIME,
                create_by INTEGER
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO system_variable
                (id, tenant_id, name, var_type, type, value, create_time, create_by)
            VALUES
                (1, 1, 'i18n_variable.account', 'text', 'system', '["account"]', NULL, NULL),
                (2, 1, 'global_region', 'text', 'platform', '["CN","US"]', NULL, 1),
                (3, 10, 'workspace_region', 'text', 'custom', '["CN"]', NULL, 2),
                (4, 11, 'other_workspace_region', 'text', 'custom', '["US"]', NULL, 3)
            """
        ))
    return engine


def _trans(value):
    return value


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


def test_tenant_admin_can_manage_tenant_scoped_variables(monkeypatch):
    def fake_save(session, user, trans, variable):
        return {"tenant_id": user.tenant_id, "variable": variable}

    def fake_delete(session, user, ids):
        return {"tenant_id": user.tenant_id, "ids": ids}

    async def fake_list_page(session, trans, user, pageNum, pageSize, variable):
        return {"tenant_id": user.tenant_id, "page": pageNum, "size": pageSize}

    monkeypatch.setattr(variable_api, "save", fake_save)
    monkeypatch.setattr(variable_api, "delete", fake_delete)
    monkeypatch.setattr(variable_api, "list_page", fake_list_page)
    token = _with_request(_tenant_admin())
    try:
        assert asyncio.run(
            variable_api.save_variable(
                session=None,
                user=_tenant_admin(),
                trans=None,
                variable={"name": "tenant-variable"},
            )
        ) == {"tenant_id": 10, "variable": {"name": "tenant-variable"}}
        assert asyncio.run(
            variable_api.delete_variable(session=None, user=_tenant_admin(), ids=[1])
        ) == {"tenant_id": 10, "ids": [1]}
        assert asyncio.run(
            variable_api.pager(
                session=None,
                user=_tenant_admin(),
                trans=None,
                pageNum=1,
                pageSize=20,
                variable=None,
            )
        ) == {"tenant_id": 10, "page": 1, "size": 20}
    finally:
        permission_schema.RequestContext.reset(token)


def test_variable_scope_separates_platform_and_workspace_records():
    engine = _variable_engine()
    with Session(engine) as session:
        tenant_rows = variable_crud.list_all(session, _trans, _tenant_admin(), None)
        assert [row["name"] for row in tenant_rows] == [
            "i18n_variable.account",
            "global_region",
            "workspace_region",
        ]
        assert [row["can_edit"] for row in tenant_rows] == [False, False, True]

        platform_rows = variable_crud.list_all(session, _trans, _platform_admin(), None)
        assert [row["name"] for row in platform_rows] == [
            "i18n_variable.account",
            "global_region",
        ]
        assert [row["can_edit"] for row in platform_rows] == [False, True]


def test_workspace_cannot_change_platform_variable_but_platform_can():
    engine = _variable_engine()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as workspace_exc:
            variable_crud.save(
                session,
                _tenant_admin(),
                _trans,
                SystemVariable(id=2, name="global_region", var_type="text", type="platform", value=["EU"]),
            )
        assert workspace_exc.value.status_code == 403

        variable_crud.save(
            session,
            _platform_admin(),
            _trans,
            SystemVariable(id=2, name="global_region", var_type="text", type="platform", value=["EU"]),
        )
        row = session.get(SystemVariable, 2)
        assert row.type == "platform"
        assert row.value == ["EU"]


def test_variable_creation_uses_current_management_scope():
    engine = _variable_engine()
    with Session(engine) as session:
        variable_crud.save(
            session,
            _platform_admin(),
            _trans,
            SystemVariable(name="platform_budget", var_type="number", type="custom", value=[0, 100]),
        )
        platform_row = session.query(SystemVariable).filter(SystemVariable.name == "platform_budget").first()
        assert platform_row.type == "platform"
        assert platform_row.tenant_id == 1

        variable_crud.save(
            session,
            _tenant_admin(),
            _trans,
            SystemVariable(name="tenant_budget", var_type="number", type="custom", value=[0, 10]),
        )
        tenant_row = session.query(SystemVariable).filter(SystemVariable.name == "tenant_budget").first()
        assert tenant_row.type == "custom"
        assert tenant_row.tenant_id == 10


def test_platform_admin_can_read_platform_parameters(monkeypatch):
    async def fake_get_parameter_args(session):
        return ["ok"]

    monkeypatch.setattr(parameter_api, "get_parameter_args", fake_get_parameter_args)
    token = _with_request(_platform_admin())
    try:
        assert asyncio.run(parameter_api.get_args(session=None)) == ["ok"]
    finally:
        permission_schema.RequestContext.reset(token)


def test_platform_admin_cannot_use_tenant_chatbi_business_features():
    with pytest.raises(HTTPException) as exc:
        ensure_chatbi_business_user(_platform_admin())

    assert exc.value.status_code == 403


def test_tenant_admin_can_use_tenant_chatbi_business_features():
    ensure_chatbi_business_user(_tenant_admin())
