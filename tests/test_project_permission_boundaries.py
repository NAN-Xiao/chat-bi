import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import text
from sqlmodel import create_engine

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.system.schemas import permission as permission_schema


def _engine_with_project_metadata_tables():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE core_datasource (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(128) NOT NULL,
                description VARCHAR(512),
                type VARCHAR(64),
                type_name VARCHAR(64),
                configuration TEXT,
                create_time DATETIME,
                create_by INTEGER,
                status VARCHAR(64),
                num VARCHAR(256),
                table_relation TEXT,
                embedding TEXT,
                recommended_config INTEGER
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_datasource_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ds_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'viewer',
                create_by INTEGER,
                create_time DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_table (
                id INTEGER PRIMARY KEY,
                ds_id INTEGER NOT NULL,
                checked BOOLEAN,
                table_name TEXT,
                table_comment TEXT,
                custom_comment TEXT,
                embedding TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_field (
                id INTEGER PRIMARY KEY,
                ds_id INTEGER NOT NULL,
                table_id INTEGER NOT NULL,
                checked BOOLEAN,
                field_name TEXT,
                field_type VARCHAR(128),
                field_comment TEXT,
                custom_comment TEXT,
                field_index INTEGER
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_datasource
                (id, tenant_id, name, type, configuration, create_by, recommended_config)
            VALUES
                (1, 1, 'Project 1', 'pg', '{}', 9, 1),
                (2, 1, 'Project 2', 'pg', '{}', 9, 1),
                (3, 2, 'Project 3', 'pg', '{}', 9, 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_datasource_user (ds_id, user_id, role)
            VALUES
                (1, 2, 'viewer'),
                (2, 2, 'editor')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_table (id, ds_id, checked, table_name)
            VALUES
                (10, 1, 1, 'orders'),
                (11, 3, 1, 'customers')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_field (id, ds_id, table_id, checked, field_name, field_index)
            VALUES
                (20, 2, 10, 1, 'amount', 1),
                (21, 3, 11, 1, 'name', 1)
            """
        ))
    return engine


def test_table_and_field_permissions_resolve_to_owning_datasource(monkeypatch):
    engine = _engine_with_project_metadata_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")

    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "table",
        10,
        ["project_viewer"],
    )) is True
    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "table",
        10,
        ["project_editor"],
    )) is False
    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "field",
        20,
        ["project_editor"],
    )) is True
    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "field",
        21,
        ["project_viewer"],
    )) is False


def test_project_permission_requires_explicit_workspace_context(monkeypatch):
    engine = _engine_with_project_metadata_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    current_user = SimpleNamespace(id=2, isAdmin=False)

    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "ds",
        1,
        ["project_viewer"],
    )) is False
    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "table",
        10,
        ["project_viewer"],
    )) is False


def test_resource_scoped_permission_defaults_to_deny_on_empty_or_unknown_resource():
    current_user = SimpleNamespace(id=2, isAdmin=False)
    system_admin = SimpleNamespace(id=1, isAdmin=True)

    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "ds",
        None,
        ["project_viewer"],
    )) is False
    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "ds",
        [],
        ["project_viewer"],
    )) is False
    assert asyncio.run(permission_schema.check_project_permission(
        current_user,
        "unknown",
        1,
        ["project_viewer"],
    )) is False
    assert asyncio.run(permission_schema.check_project_permission(
        system_admin,
        "unknown",
        None,
        ["project_viewer"],
    )) is True


def test_permission_decorator_rejects_unresolved_resource(monkeypatch):
    monkeypatch.setattr(permission_schema, "check_project_permission", lambda *args, **kwargs: False)
    request = Request({"type": "http", "headers": []})
    request.state.current_user = SimpleNamespace(id=2, isAdmin=False)
    token = permission_schema.RequestContext.set_request(request)

    @permission_schema.require_permissions(
        permission_schema.AppPermission(type="ds", keyExpression="payload.datasource_id")
    )
    async def endpoint(payload):
        return True

    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoint(SimpleNamespace()))
        assert exc.value.status_code == 403
    finally:
        permission_schema.RequestContext.reset(token)


def test_permission_decorator_rejects_missing_key_expression():
    request = Request({"type": "http", "headers": []})
    request.state.current_user = SimpleNamespace(id=2, isAdmin=False)
    token = permission_schema.RequestContext.set_request(request)

    @permission_schema.require_permissions(permission_schema.AppPermission(type="ds"))
    async def endpoint(datasource_id):
        return True

    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoint(1))
        assert exc.value.status_code == 403
    finally:
        permission_schema.RequestContext.reset(token)


def test_platform_admin_role_is_separate_from_tenant_admin():
    request = Request({"type": "http", "headers": []})
    request.state.current_user = SimpleNamespace(
        id=2,
        system_role="viewer",
        tenant_id=10,
        tenant_role="owner",
    )
    token = permission_schema.RequestContext.set_request(request)

    @permission_schema.require_permissions(permission_schema.AppPermission(role=["platform_admin"]))
    async def platform_endpoint():
        return "ok"

    @permission_schema.require_permissions(permission_schema.AppPermission(role=["admin"]))
    async def tenant_endpoint():
        return "ok"

    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(platform_endpoint())
        assert exc.value.status_code == 403
        assert asyncio.run(tenant_endpoint()) == "ok"
    finally:
        permission_schema.RequestContext.reset(token)


def test_platform_admin_role_accepts_service_provider_admin():
    request = Request({"type": "http", "headers": []})
    request.state.current_user = SimpleNamespace(
        id=1,
        system_role="system_admin",
        tenant_id=10,
        tenant_role="owner",
    )
    token = permission_schema.RequestContext.set_request(request)

    @permission_schema.require_permissions(permission_schema.AppPermission(role=["platform_admin"]))
    async def endpoint():
        return "ok"

    try:
        assert asyncio.run(endpoint()) == "ok"
    finally:
        permission_schema.RequestContext.reset(token)


def test_permission_decorator_rejects_unresolved_resource_for_system_admin():
    request = Request({"type": "http", "headers": []})
    request.state.current_user = SimpleNamespace(id=1, isAdmin=True)
    token = permission_schema.RequestContext.set_request(request)

    @permission_schema.require_permissions(
        permission_schema.AppPermission(type="ds", keyExpression="payload.datasource_id")
    )
    async def endpoint():
        return "ok"

    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoint())
        assert exc.value.status_code == 403
    finally:
        permission_schema.RequestContext.reset(token)
