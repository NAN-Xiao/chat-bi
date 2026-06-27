import os
import json
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from apps.datasource.crud import datasource as datasource_crud
from apps.datasource.api import datasource as datasource_api
from apps.datasource.api import permission as permission_api
from apps.datasource.crud.binding import bind_tenant_to_datasource
from apps.datasource.crud import permission
from apps.datasource.crud import query_executor
from apps.datasource.crud.permission_rules import delete_permission_records_for_datasources
from apps.datasource.crud.permission_errors import PERMISSION_DENIED_AGENT_GUIDANCE, PERMISSION_DENIED_RESULT_MESSAGE
from apps.datasource.crud.sql_permission import validate_sql_scope
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser, CoreTable, TableObj
from apps.datasource.models.datasource import FieldObj
from apps.system.schemas import permission as permission_schema
from apps.analysis_assistant.api import analysis_assistant as analysis_assistant_api


def _engine_with_permission_tables():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
            CREATE TABLE sys_user (
                id INTEGER PRIMARY KEY,
                account VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                status INTEGER NOT NULL,
                origin INTEGER NOT NULL DEFAULT 0,
                create_time INTEGER NOT NULL,
                language VARCHAR(255),
                system_role VARCHAR(32) NOT NULL DEFAULT 'viewer'
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
            CREATE TABLE sys_tenant_schema_table (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                table_name TEXT NOT NULL,
                table_comment TEXT,
                create_by INTEGER,
                update_by INTEGER,
                create_time INTEGER NOT NULL,
                update_time INTEGER NOT NULL,
                UNIQUE (tenant_id, table_name)
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_tenant_schema_field (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                table_name TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_comment TEXT,
                create_by INTEGER,
                update_by INTEGER,
                create_time INTEGER NOT NULL,
                update_time INTEGER NOT NULL,
                UNIQUE (tenant_id, table_name, field_name)
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_tenant_schema_change_request (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                datasource_id INTEGER,
                change_type VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                table_name VARCHAR(255) NOT NULL,
                payload TEXT,
                requested_by_user_id INTEGER NOT NULL,
                executed_by_user_id INTEGER,
                request_comment TEXT,
                execution_comment TEXT,
                create_time INTEGER NOT NULL,
                update_time INTEGER NOT NULL,
                execute_time INTEGER
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE ds_rules (
                id INTEGER PRIMARY KEY,
                enable BOOLEAN NOT NULL,
                name VARCHAR NOT NULL,
                description VARCHAR,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                scope VARCHAR(32) NOT NULL DEFAULT 'TENANT',
                permission_list TEXT,
                user_list TEXT,
                white_list_user TEXT,
                create_time DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE ds_permission (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                enable BOOLEAN NOT NULL,
                auth_target_type VARCHAR,
                auth_target_id INTEGER,
                type VARCHAR NOT NULL,
                ds_id INTEGER,
                table_id INTEGER,
                expression_tree TEXT,
                permissions TEXT,
                white_list_user TEXT,
                create_time DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_tenant (
                id INTEGER PRIMARY KEY,
                public_id VARCHAR(32) NOT NULL,
                name VARCHAR(255) NOT NULL,
                status INTEGER NOT NULL DEFAULT 1,
                plan VARCHAR(64) DEFAULT 'default',
                subscription_status VARCHAR(32) DEFAULT 'active',
                billing_mode VARCHAR(32) DEFAULT 'manual',
                trial_end_time INTEGER,
                current_period_end_time INTEGER,
                contract_no VARCHAR(128),
                billing_contact VARCHAR(128),
                billing_email VARCHAR(128),
                subscription_note VARCHAR(2000),
                create_time INTEGER DEFAULT 0,
                update_time INTEGER DEFAULT 0
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_tenant_user (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'member',
                member_remark VARCHAR(255),
                is_primary BOOLEAN NOT NULL DEFAULT 0,
                status INTEGER NOT NULL DEFAULT 1,
                create_time INTEGER NOT NULL DEFAULT 0
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_datasource_tenant_binding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL UNIQUE,
                datasource_id INTEGER NOT NULL,
                create_by INTEGER,
                create_time DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (1, 'first-user', 'First User', '', 'first@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (2, 'editor', 'Editor', '', 'editor@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (3, 'analyst', 'Analyst', '', 'analyst@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (4, 'sysadmin', 'System Admin', '', 'sysadmin@example.com', 1, 0, 1, 'zh-CN', 'system_admin')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_tenant
                (id, public_id, name, status, plan, subscription_status, billing_mode, create_time, update_time)
            VALUES
                (1, 'WSDEFAULT2', 'Default', 1, 'default', 'active', 'manual', 1, 1),
                (2, 'WSWORKSP2', 'Workspace 2', 1, 'default', 'active', 'manual', 1, 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_tenant_user
                (id, tenant_id, user_id, role, is_primary, status, create_time)
            VALUES
                (1, 2, 2, 'member', 1, 1, 1),
                (2, 2, 3, 'member', 0, 1, 1),
                (3, 3, 3, 'member', 1, 1, 1),
                (4, 1, 2, 'member', 1, 1, 1),
                (5, 1, 5, 'admin', 0, 1, 1)
            """
        ))
    return engine


def _datasource(datasource_id=1, create_by=9, tenant_id=1):
    return CoreDatasource(
        id=datasource_id,
        tenant_id=tenant_id,
        name=f"Project {datasource_id}",
        type="pg",
        configuration="{}",
        create_by=create_by,
        recommended_config=1,
    )


def test_datasource_role_defaults_to_viewer_for_existing_membership():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) == "viewer"
        assert permission.has_datasource_role(session, current_user, 1, "project_viewer") is True
        assert permission.has_datasource_role(session, current_user, 1, "project_editor") is False


def test_datasource_tenant_id_returns_scalar_value():
    engine = _engine_with_permission_tables()

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=11))
        session.commit()

        assert datasource_crud._datasource_tenant_id(session, 1) == 11


def test_platform_admin_datasource_list_can_view_all_projects():
    engine = _engine_with_permission_tables()
    system_admin = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)
    collab_admin = SimpleNamespace(id=6, system_role="collab_admin", tenant_id=2)

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        session.add(_datasource(2, tenant_id=2))
        session.commit()

        system_admin_items = asyncio.run(datasource_api.datasource_list.__wrapped__(session, system_admin))
        collab_admin_items = asyncio.run(datasource_api.datasource_list.__wrapped__(session, collab_admin))

        assert [item["id"] for item in system_admin_items] == [1, 2]
        assert [item["id"] for item in collab_admin_items] == [1, 2]


def test_datasource_membership_does_not_cross_tenant_boundary():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        session.add(_datasource(2, tenant_id=2))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        session.add(CoreDatasourceUser(ds_id=2, user_id=2, role="editor"))
        session.commit()

        assert permission.has_datasource_access(session, current_user, 1) is True
        assert permission.has_datasource_access(session, current_user, 2) is False
        assert permission.get_accessible_datasource_ids(session, current_user) == {1}


def test_schema_context_requires_datasource_access():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(2, tenant_id=2))
        session.add(CoreTable(id=20, ds_id=2, checked=True, table_name="secret_orders"))
        session.commit()

        ds = session.get(CoreDatasource, 2)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show orders",
            embedding=False,
        )
        sample_data = datasource_crud.get_tables_sample_data(session, current_user, ds)

    assert schema == ""
    assert tables == []
    assert sample_data == ""


def test_tenant_admin_can_manage_all_datasources_in_current_tenant_only():
    engine = _engine_with_permission_tables()
    tenant_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=1, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        session.add(_datasource(2, tenant_id=2))
        session.commit()

        assert permission.get_accessible_datasource_ids(session, tenant_admin) == {1}
        assert permission.get_datasource_role(session, tenant_admin, 1) == "editor"
        assert permission.has_datasource_role(session, tenant_admin, 1, "project_editor") is True
        assert permission.has_datasource_access(session, tenant_admin, 2) is False


def test_tenant_admin_update_user_datasources_ignores_projects_outside_current_tenant():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=5, system_role="viewer", tenant_id=1, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        session.add(_datasource(2, tenant_id=2))
        session.commit()

        assert permission.update_user_datasources(session, current_user, 2, [1, 2]) == [1]
        session.commit()

        assert permission.list_user_datasource_roles(session, 2, current_user) == {1: "viewer"}


def test_datasource_editor_satisfies_dashboard_edit_role():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="editor"))
        session.commit()

        assert permission.has_datasource_role(session, current_user, 1, "project_editor") is True
        assert permission.has_datasource_role(session, current_user, 1, "project_admin") is False


def test_workspace_member_can_view_current_tenant_project_without_membership_row():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")

    with Session(engine) as session:
        session.add(_datasource(1, create_by=3, tenant_id=1))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) == "viewer"
        assert permission.has_datasource_role(session, current_user, 1, "project_viewer") is True
        assert permission.get_accessible_datasource_ids(session, current_user) == {1}


def test_workspace_member_without_project_membership_cannot_edit_project():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) == "viewer"
        assert permission.has_datasource_role(session, current_user, 1, "project_editor") is False


def test_datasource_list_hides_connection_config_for_normal_users():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    system_admin = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)
    tenant_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=1, tenant_role="owner")

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        session.commit()

        normal_items = asyncio.run(datasource_api.accessible_datasource_list(session, current_user))
        admin_items = asyncio.run(datasource_api.datasource_list.__wrapped__(session, system_admin))
        tenant_admin_items = asyncio.run(datasource_api.accessible_datasource_list(session, tenant_admin))

        assert normal_items[0]["configuration"] is None
        assert admin_items[0]["configuration"] == "{}"
        assert tenant_admin_items[0]["configuration"] is None
        assert normal_items[0]["can_manage_project"] is False
        assert admin_items[0]["can_manage_project"] is False
        assert admin_items[0]["can_manage_metadata"] is True
        assert admin_items[0]["can_bind_workspace"] is True
        assert tenant_admin_items[0]["can_manage_project"] is True
        assert tenant_admin_items[0]["can_manage_metadata"] is False
        assert tenant_admin_items[0]["can_bind_workspace"] is False


def _set_permission_request_context(user):
    request = Request({"type": "http", "headers": []})
    request.state.current_user = user
    return permission_schema.RequestContext.set_request(request)


def test_workspace_admin_schema_metadata_is_metadata_only(monkeypatch):
    engine = _engine_with_permission_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    tenant_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=1, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        _insert_table_permission_fixture(session)
        session.commit()

        token = _set_permission_request_context(tenant_admin)
        try:
            result = asyncio.run(datasource_api.schema_metadata(session, tenant_admin, 1))
        finally:
            permission_schema.RequestContext.reset(token)

        payload = result.model_dump()
        assert payload["id"] == 1
        assert payload["tables"][0]["table_name"] == "orders"
        assert payload["tables"][0]["fields"][0]["field_name"] == "order_id"
        assert "configuration" not in payload
        assert "data" not in payload
        assert "sql" not in payload


def test_workspace_schema_comments_override_physical_custom_comments(monkeypatch):
    engine = _engine_with_permission_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    tenant_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=1, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        _insert_table_permission_fixture(session)
        session.execute(text(
            """
            INSERT INTO sys_tenant_schema_table
                (id, tenant_id, table_name, table_comment, create_time, update_time)
            VALUES
                (9001, 1, 'orders', 'workspace orders comment', 0, 0),
                (9002, 1, 'payments', '', 0, 0)
            """
        ))
        session.execute(text(
            """
            INSERT INTO sys_tenant_schema_field
                (id, tenant_id, table_name, field_name, field_comment, create_time, update_time)
            VALUES
                (9101, 1, 'orders', 'amount', 'workspace amount comment', 0, 0),
                (9102, 1, 'orders', 'order_id', '', 0, 0)
            """
        ))
        session.commit()

        token = _set_permission_request_context(tenant_admin)
        try:
            metadata = asyncio.run(datasource_api.schema_metadata(session, tenant_admin, 1)).model_dump()
        finally:
            permission_schema.RequestContext.reset(token)

        ds = session.get(CoreDatasource, 1)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=tenant_admin,
            ds=ds,
            question="show orders",
            embedding=False,
        )

    orders = next(item for item in metadata["tables"] if item["table_name"] == "orders")
    payments = next(item for item in metadata["tables"] if item["table_name"] == "payments")
    amount = next(item for item in orders["fields"] if item["field_name"] == "amount")
    order_id = next(item for item in orders["fields"] if item["field_name"] == "order_id")

    assert orders["custom_comment"] == "workspace orders comment"
    assert payments["custom_comment"] == ""
    assert amount["custom_comment"] == "workspace amount comment"
    assert order_id["custom_comment"] == ""
    assert tables == ["orders", "payments"]
    assert "# Table: orders, workspace orders comment" in schema
    assert "(amount:numeric, workspace amount comment)" in schema
    assert "(order_id:int)" in schema
    assert "orders, orders" not in schema
    assert "order_id, order_id" not in schema


def test_schema_change_request_is_saved_without_mutating_readonly_datasource(monkeypatch):
    engine = _engine_with_permission_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    tenant_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=1, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        _insert_table_permission_fixture(session)
        session.commit()

        token = _set_permission_request_context(tenant_admin)
        try:
            result = asyncio.run(datasource_api.submit_schema_change(
                session,
                tenant_admin,
                datasource_api.DatasourceSchemaChangeCreate(
                    change_type="create_table",
                    table_name="event_orders",
                    table_comment="订单事件宽表",
                    fields=[
                        datasource_api.DatasourceSchemaChangeField(
                            field_name="event_id",
                            field_type="bigint",
                            field_comment="事件ID",
                        ),
                        datasource_api.DatasourceSchemaChangeField(
                            field_name="event_time",
                            field_type="timestamp",
                            field_comment="事件时间",
                        ),
                    ],
                    request_comment="prepare writable workspace datastore",
                ),
                1,
            ))
        finally:
            permission_schema.RequestContext.reset(token)

        payload = result.model_dump()
        core_table_count = session.exec(
            text("select count(*) from core_table where table_name = 'event_orders'")
        ).one()[0]
        request_count = session.exec(text(
            "select count(*) from sys_tenant_schema_change_request where table_name = 'event_orders'"
        )).one()[0]

    assert payload["change_type"] == "create_table"
    assert payload["status"] == "pending"
    assert payload["payload"]["fields"][0]["field_name"] == "event_id"
    assert core_table_count == 0
    assert request_count == 1


def test_workspace_member_cannot_directly_browse_schema_metadata(monkeypatch):
    engine = _engine_with_permission_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    member = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        session.commit()

        token = _set_permission_request_context(member)
        try:
            with pytest.raises(HTTPException) as schema_exc:
                asyncio.run(datasource_api.schema_metadata(session, member, 1))
            with pytest.raises(HTTPException) as table_exc:
                asyncio.run(datasource_api.table_list(session, member, 1))
            with pytest.raises(HTTPException) as field_exc:
                asyncio.run(datasource_api.field_list(session, member, FieldObj(fieldName=""), 10))
        finally:
            permission_schema.RequestContext.reset(token)

        assert schema_exc.value.status_code == 403
        assert table_exc.value.status_code == 403
        assert field_exc.value.status_code == 403


def test_platform_workspace_delegate_cannot_preview_datasource_rows(monkeypatch):
    engine = _engine_with_permission_tables()
    monkeypatch.setattr(permission_schema, "engine", engine)
    delegate = SimpleNamespace(
        id=4,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=1))
        _insert_table_permission_fixture(session)
        session.commit()

        token = _set_permission_request_context(delegate)
        try:
            with pytest.raises(HTTPException) as exc:
                asyncio.run(datasource_api.preview_data(
                    session,
                    None,
                    delegate,
                    TableObj(table=CoreTable(id=10, ds_id=1, table_name="orders", table_comment="", custom_comment="")),
                    1,
                ))
        finally:
            permission_schema.RequestContext.reset(token)

        assert exc.value.status_code == 403


def test_workspace_binding_replaces_and_cancels_bound_project_permissions():
    engine = _engine_with_permission_tables()
    platform_admin = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.execute(text(
            "INSERT INTO sys_tenant (id, public_id, name, status, plan) VALUES (3, 'WSTENANT3', 'Tenant 3', 1, 'default')"
        ))
        session.add(_datasource(1, tenant_id=1))
        session.add(_datasource(2, tenant_id=1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        session.add(CoreDatasourceUser(ds_id=2, user_id=3, role="editor"))
        session.execute(text(
            """
            INSERT INTO ds_permission
                (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
            VALUES
                (1000, 'project 1 table', 1, 'user', 'table', 1, 10, '{}', '[]', '[]'),
                (1001, 'project 2 table', 1, 'user', 'table', 2, 20, '{}', '[]', '[]')
            """
        ))
        session.execute(text(
            """
            INSERT INTO ds_rules
                (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
            VALUES
                (2000, 1, 'project 1', '', 2, 'TENANT', '[1000]', '[2]', '[]'),
                (2001, 1, 'project 2', '', 2, 'TENANT', '[1001]', '[3]', '[]')
            """
        ))
        session.commit()

        bound = bind_tenant_to_datasource(session, platform_admin, 2, 1)
        session.expire_all()

        assert int(bound.id) == 1
        assert session.execute(text("SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = 2")).scalar_one() == 1
        assert session.get(CoreDatasource, 2).tenant_id == 1
        assert session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id == 1).count() == 0

        bind_tenant_to_datasource(session, platform_admin, 3, 1)
        session.expire_all()

        assert session.execute(text(
            "SELECT tenant_id FROM core_datasource_tenant_binding WHERE datasource_id = 1 ORDER BY tenant_id"
        )).all() == [(2,), (3,)]

        bind_tenant_to_datasource(session, platform_admin, 2, 2)
        session.expire_all()

        assert session.execute(text("SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = 2")).scalar_one() == 2
        assert session.execute(text("SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = 3")).scalar_one() == 1
        assert session.query(CoreDatasourceUser).filter(CoreDatasourceUser.ds_id.in_([1, 2])).count() == 0

        bind_tenant_to_datasource(session, platform_admin, 2, None)
        session.expire_all()

        assert session.execute(text("SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = 2")).first() is None
        assert session.execute(text("SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = 3")).scalar_one() == 1
        assert session.execute(text("SELECT id FROM ds_permission ORDER BY id")).all() == []
        assert session.execute(text("SELECT id FROM ds_rules ORDER BY id")).all() == []


def test_get_datasource_redacts_config_without_mutating_record():
    engine = _engine_with_permission_tables()
    normal_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    admin_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.commit()

        result = asyncio.run(datasource_api.get_datasource.__wrapped__(session, normal_user, 1))
        admin_result = asyncio.run(datasource_api.get_datasource.__wrapped__(session, admin_user, 1))
        session.commit()
        session.expire_all()
        datasource = session.get(CoreDatasource, 1)

        assert result["configuration"] is None
        assert admin_result["configuration"] == "{}"
        assert datasource.configuration == "{}"


def test_update_datasource_ignores_missing_connection_config(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)
    monkeypatch.setattr(datasource_crud, "run_save_ds_embeddings", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.commit()

        datasource_crud.update_ds(
            session=session,
            trans=lambda key: key,
            user=current_user,
            ds=CoreDatasource(
                id=1,
                name="Renamed Project",
                type="pg",
                configuration=None,
                create_by=9,
                recommended_config=1,
            ),
        )
        session.expire_all()
        datasource = session.get(CoreDatasource, 1)

        assert datasource.name == "Renamed Project"
        assert datasource.configuration == "{}"


def test_update_datasource_users_excludes_system_admin_by_role_not_user_id():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        datasource = _datasource(1)
        session.add(datasource)
        session.commit()

        users = permission.update_datasource_users(
            session,
            current_user,
            datasource,
            [1, 2, 3, 4],
            {1: "viewer", 2: "editor", 3: "project_admin", 4: "project_admin"},
        )
        session.commit()

        assert users == [
            {"user_id": 1, "role": "viewer"},
            {"user_id": 2, "role": "editor"},
            {"user_id": 3, "role": "editor"},
        ]
        assert permission.list_datasource_user_ids(session, 1, current_user) == [1, 2, 3]
        assert permission.list_user_datasource_roles(session, 2, current_user) == {1: "editor"}


def test_update_user_datasources_excludes_system_admin_by_role_not_user_id():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(_datasource(2))
        session.commit()

        assert permission.update_user_datasources(session, current_user, 1, [1]) == [1]
        assert permission.update_user_datasources(session, current_user, 4, [1, 2]) == []
        session.commit()

        assert permission.list_user_datasource_roles(session, 1, current_user) == {1: "viewer"}
        assert permission.list_user_datasource_roles(session, 4, current_user) == {}


def test_update_user_datasources_saves_project_role_map_for_new_memberships():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(_datasource(2))
        session.commit()

        assert permission.update_user_datasources(
            session,
            current_user,
            2,
            [1, 2],
            {1: "editor", 2: "unknown"},
        ) == [1, 2]
        session.commit()

        assert permission.list_user_datasource_roles(session, 2, current_user) == {
            1: "editor",
            2: "viewer",
        }


def test_update_user_datasources_updates_existing_project_roles():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        session.commit()

        assert permission.update_user_datasources(
            session,
            current_user,
            2,
            [1],
            {1: "project_editor"},
        ) == [1]
        session.commit()

        assert permission.list_user_datasource_roles(session, 2, current_user) == {1: "editor"}


def test_update_user_datasources_preserves_existing_roles_when_role_map_omitted():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="editor"))
        session.commit()

        assert permission.update_user_datasources(session, current_user, 2, [1]) == [1]
        session.commit()

        assert permission.list_user_datasource_roles(session, 2, current_user) == {1: "editor"}


def test_get_datasource_ids_with_min_role_filters_by_project_role():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(_datasource(2))
        session.add(_datasource(3))
        session.add(_datasource(4, create_by=2))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        session.add(CoreDatasourceUser(ds_id=2, user_id=2, role="editor"))
        session.add(CoreDatasourceUser(ds_id=3, user_id=2, role="admin"))
        session.commit()

        assert permission.get_datasource_ids_with_min_role(session, current_user, "viewer") == {1, 2, 3, 4}
        assert permission.get_datasource_ids_with_min_role(session, current_user, "editor") == {2, 3}
        assert permission.get_datasource_ids_with_min_role(session, current_user, "admin") == set()


def _insert_table_permission_fixture(session: Session):
    session.execute(text(
        """
        INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
        VALUES
            (10, 1, 1, 'orders', 'orders', 'orders'),
            (11, 1, 1, 'payments', 'payments', 'payments')
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_field
            (id, ds_id, table_id, checked, field_name, field_type, field_comment, custom_comment, field_index)
        VALUES
            (100, 1, 10, 1, 'order_id', 'int', 'order_id', 'order_id', 1),
            (101, 1, 10, 1, 'amount', 'numeric', 'amount', 'amount', 2),
            (110, 1, 11, 1, 'payment_id', 'int', 'payment_id', 'payment_id', 1)
        """
    ))


def _insert_permission_scope_fixture(session: Session):
    session.add(_datasource(1, tenant_id=2))
    session.add(_datasource(2, tenant_id=3))
    session.execute(text(
        """
        INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
        VALUES
            (10, 1, 1, 'orders', 'orders', 'orders'),
            (20, 2, 1, 'events', 'events', 'events')
        """
    ))
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1000, 'platform workspace 2 table', 1, 'user', 'table', 1, 10, '{}', '[]', '[]'),
            (1001, 'workspace 2 table', 1, 'user', 'table', 1, 10, '{}', '[]', '[]'),
            (1002, 'platform workspace 3 table', 1, 'user', 'table', 2, 20, '{}', '[]', '[]'),
            (1003, 'workspace 3 table', 1, 'user', 'table', 2, 20, '{}', '[]', '[]')
        """
    ))
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
        VALUES
            (2000, 1, 'platform rule', '', 1, 'PLATFORM', '[1000,1002]', '[2]', '[]'),
            (2001, 1, 'workspace 2 rule', '', 2, 'TENANT', '[1001]', '[2]', '[]'),
            (2002, 1, 'workspace 3 rule', '', 3, 'TENANT', '[1003]', '[2]', '[]')
        """
    ))


def test_permission_rule_groups_are_scoped_like_platform_and_workspace_config():
    engine = _engine_with_permission_tables()
    platform_admin = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)
    workspace_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=2, tenant_role="admin")
    other_workspace_admin = SimpleNamespace(id=6, system_role="viewer", tenant_id=3, tenant_role="admin")

    with Session(engine) as session:
        _insert_permission_scope_fixture(session)
        session.commit()

        workspace_rules = asyncio.run(permission_api.p_list.__wrapped__(session, workspace_admin))
        assert [rule["id"] for rule in workspace_rules] == [2000, 2001]
        platform_rule = workspace_rules[0]
        assert platform_rule["scope"] == "PLATFORM"
        assert platform_rule["permission_list"] == [1000]
        assert platform_rule["can_edit"] is False
        assert platform_rule["can_delete"] is False
        tenant_rule = workspace_rules[1]
        assert tenant_rule["scope"] == "TENANT"
        assert tenant_rule["tenant_id"] == 2
        assert tenant_rule["can_edit"] is True
        assert tenant_rule["can_delete"] is True

        other_workspace_rules = asyncio.run(permission_api.p_list.__wrapped__(session, other_workspace_admin))
        assert [rule["id"] for rule in other_workspace_rules] == [2000, 2002]
        assert other_workspace_rules[0]["permission_list"] == [1002]

        platform_rules = asyncio.run(permission_api.p_list.__wrapped__(session, platform_admin))
        assert [rule["id"] for rule in platform_rules] == [2000]
        assert platform_rules[0]["can_edit"] is True
        assert platform_rules[0]["can_delete"] is True


def test_workspace_admin_cannot_change_platform_permission_rule_group():
    engine = _engine_with_permission_tables()
    workspace_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=2, tenant_role="admin")

    with Session(engine) as session:
        _insert_permission_scope_fixture(session)
        session.commit()

        with pytest.raises(HTTPException) as update_exc:
            asyncio.run(permission_api.save_rule.__wrapped__(
                session,
                workspace_admin,
                {
                    "id": 2000,
                    "name": "changed",
                    "permissions": [
                        {"name": "changed", "type": "table", "ds_id": 1, "table_id": 10},
                    ],
                    "users": [2],
                },
            ))
        assert update_exc.value.status_code == 403

        with pytest.raises(HTTPException) as delete_exc:
            asyncio.run(permission_api.delete.__wrapped__(session, workspace_admin, 2000))
        assert delete_exc.value.status_code == 403


def test_workspace_admin_can_add_and_delete_workspace_permission_rule_group():
    engine = _engine_with_permission_tables()
    workspace_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=2, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=2))
        session.execute(text(
            """
            INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
            VALUES (10, 1, 1, 'orders', 'orders', 'orders')
            """
        ))
        session.commit()

        saved = asyncio.run(permission_api.save_rule.__wrapped__(
            session,
            workspace_admin,
            {
                "name": "workspace created rule",
                "permissions": [
                    {"name": "orders denied", "type": "table", "ds_id": 1, "table_id": 10},
                ],
                "users": [2],
            },
        ))
        assert saved["scope"] == "TENANT"
        assert saved["tenant_id"] == 2
        assert saved["can_edit"] is True
        saved_id = int(saved["id"])
        row = session.execute(
            text("SELECT tenant_id, scope FROM ds_rules WHERE id = :id"),
            {"id": saved_id},
        ).first()
        assert row == (2, "TENANT")

        assert asyncio.run(permission_api.delete.__wrapped__(session, workspace_admin, saved_id)) is True
        assert session.execute(text("SELECT id FROM ds_rules WHERE id = :id"), {"id": saved_id}).first() is None


def test_permission_rule_group_can_be_created_without_users():
    engine = _engine_with_permission_tables()
    workspace_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=2, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=2))
        session.execute(text(
            """
            INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
            VALUES (10, 1, 1, 'orders', 'orders', 'orders')
            """
        ))
        session.commit()

        saved = asyncio.run(permission_api.save_rule.__wrapped__(
            session,
            workspace_admin,
            {
                "name": "workspace rule without users",
                "permissions": [
                    {"name": "orders denied", "type": "table", "ds_id": 1, "table_id": 10},
                ],
            },
        ))

        saved_id = int(saved["id"])
        assert saved["users"] == []
        assert saved["user_list"] == []
        assert saved["can_edit"] is True
        row = session.execute(
            text("SELECT tenant_id, scope, user_list FROM ds_rules WHERE id = :id"),
            {"id": saved_id},
        ).first()
        assert row == (2, "TENANT", "[]")


def test_workspace_permission_rule_can_infer_bound_datasource_from_table():
    engine = _engine_with_permission_tables()
    workspace_admin = SimpleNamespace(id=5, system_role="viewer", tenant_id=2, tenant_role="admin")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=2))
        session.execute(text(
            """
            INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
            VALUES (10, 1, 1, 'orders', 'orders', 'orders')
            """
        ))
        session.commit()

        saved = asyncio.run(permission_api.save_rule.__wrapped__(
            session,
            workspace_admin,
            {
                "name": "workspace rule without datasource id",
                "permissions": [
                    {"name": "orders denied", "type": "table", "table_id": 10},
                ],
            },
        ))

        saved_id = int(saved["id"])
        assert saved["permissions"][0]["ds_id"] == 1
        assert saved["permissions"][0]["ds_name"] is not None
        row = session.execute(
            text(
                """
                SELECT p.ds_id
                FROM ds_permission p
                JOIN ds_rules r ON r.permission_list = '[' || p.id || ']'
                WHERE r.id = :id
                """
            ),
            {"id": saved_id},
        ).first()
        assert row == (1,)


def test_platform_admin_can_manage_platform_permission_rule_group():
    engine = _engine_with_permission_tables()
    platform_admin = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=2))
        session.execute(text(
            """
            INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
            VALUES (10, 1, 1, 'orders', 'orders', 'orders')
            """
        ))
        session.commit()

        saved = asyncio.run(permission_api.save_rule.__wrapped__(
            session,
            platform_admin,
            {
                "name": "platform created rule",
                "permissions": [
                    {"name": "orders denied", "type": "table", "ds_id": 1, "table_id": 10},
                ],
                "users": [2],
            },
        ))
        saved_id = int(saved["id"])
        assert saved["scope"] == "PLATFORM"
        assert saved["tenant_id"] == 1
        assert saved["can_edit"] is True
        assert saved["can_delete"] is True
        row = session.execute(
            text("SELECT tenant_id, scope FROM ds_rules WHERE id = :id"),
            {"id": saved_id},
        ).first()
        assert row == (1, "PLATFORM")

        edited = asyncio.run(permission_api.save_rule.__wrapped__(
            session,
            platform_admin,
            {
                "id": saved_id,
                "name": "platform edited rule",
                "permissions": [
                    {"name": "orders still denied", "type": "table", "ds_id": 1, "table_id": 10},
                ],
                "users": [2],
            },
        ))
        assert edited["id"] == saved_id
        assert edited["name"] == "platform edited rule"
        assert edited["scope"] == "PLATFORM"

        assert asyncio.run(permission_api.delete.__wrapped__(session, platform_admin, saved_id)) is True
        assert session.execute(text("SELECT id FROM ds_rules WHERE id = :id"), {"id": saved_id}).first() is None


def test_user_permission_rules_do_not_cross_workspace_scope():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=2, tenant_role="member")

    with Session(engine) as session:
        session.add(_datasource(1, tenant_id=2))
        _insert_table_permission_fixture(session)
        session.execute(text(
            """
            INSERT INTO ds_permission
                (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
            VALUES
                (1000, 'orders columns', 1, 'user', 'column', 1, 10, '{}', '[]', '[]')
            """
        ))
        session.execute(text(
            """
            INSERT INTO ds_rules
                (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
            VALUES
                (2000, 1, 'other workspace rule', '', 3, 'TENANT', '[1000]', '[2]', '[]')
            """
        ))
        session.commit()

        assert permission.get_user_permission_rules(session, current_user, 1) == []

        session.execute(text(
            """
            INSERT INTO ds_rules
                (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
            VALUES
                (2001, 1, 'platform rule', '', 1, 'PLATFORM', '[1000]', '[2]', '[]')
            """
        ))
        session.commit()

        assert [rule.id for rule in permission.get_user_permission_rules(session, current_user, 1)] == [2001]


def test_delete_permission_records_for_datasources_removes_only_target_project_rules():
    engine = _engine_with_permission_tables()

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(_datasource(2))
        session.execute(text(
            """
            INSERT INTO ds_permission
                (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
            VALUES
                (1000, 'project 1 table', 1, 'user', 'table', 1, 10, '{}', '[]', '[]'),
                (1001, 'project 2 table', 1, 'user', 'table', 2, 20, '{}', '[]', '[]'),
                (1002, 'project 1 row', 1, 'user', 'row', 1, 10, '{}', '[]', '[]')
            """
        ))
        session.execute(text(
            """
            INSERT INTO ds_rules
                (id, enable, name, description, permission_list, user_list, white_list_user)
            VALUES
                (2000, 1, 'mixed projects', '', '[1000,1001]', '[2]', '[]'),
                (2001, 1, 'project 1 only', '', '[1002]', '[2]', '[]')
            """
        ))
        session.commit()

        delete_permission_records_for_datasources(session, [1])
        session.commit()

        remaining_permissions = session.execute(text(
            "SELECT id FROM ds_permission ORDER BY id"
        )).all()
        remaining_rules = session.execute(text(
            "SELECT id, permission_list FROM ds_rules ORDER BY id"
        )).all()

        assert [row[0] for row in remaining_permissions] == [1001]
        assert remaining_rules == [(2000, "[1001]")]


def _insert_user_rule_for_orders(session: Session):
    permissions = json.dumps([
        {"field_id": 100, "field_name": "order_id", "enable": True},
        {"field_id": 101, "field_name": "amount", "enable": False},
    ])
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1000, 'orders columns', 1, 'user', 'column', 1, 10, '{}', :permissions, '[]')
        """
    ), {"permissions": permissions})
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2000, 1, 'user 2 orders only', '', '[1000]', '[2]', '[]')
        """
    ))


def _insert_user_table_deny_for_payments(session: Session):
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1003, 'payments denied', 1, 'user', 'table', 1, 11, '{}', '[]', '[]')
        """
    ))
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2003, 1, 'user 2 payments denied', '', '[1003]', '[2]', '[]')
        """
    ))


def _insert_user_table_deny_for_payments_with_permission_whitelist(session: Session):
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1003, 'payments denied', 1, 'user', 'table', 1, 11, '{}', '[]', '[2]')
        """
    ))
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2003, 1, 'user 2 payments denied', '', '[1003]', '[2]', '[]')
        """
    ))


def _insert_user_row_rule_for_orders(session: Session, *, field_id: int = 100, permission_whitelist: str = "[]"):
    tree = {
        "logic": "AND",
        "items": [
            {
                "type": "item",
                "field_id": field_id,
                "filter_type": "text",
                "term": "eq",
                "value": "US",
            }
        ],
    }
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1004, 'orders rows', 1, 'user', 'row', 1, 10, :tree, '[]', :permission_whitelist)
        """
    ), {"tree": json.dumps(tree), "permission_whitelist": permission_whitelist})
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2004, 1, 'user 2 orders row limit', '', '[1004]', '[2]', '[]')
        """
    ))


def test_row_permission_invalid_config_fails_closed(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_row_rule_for_orders(session, field_id=999)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        try:
            permission.get_row_permission_filters(session, current_user, ds, tables=["orders"])
        except ValueError as exc:
            assert "行权限" in str(exc)
        else:
            raise AssertionError("invalid row permission should fail closed")


def test_row_permission_whitelist_skips_restriction(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_row_rule_for_orders(session, field_id=100, permission_whitelist="[2]")
        session.commit()

        ds = session.get(CoreDatasource, 1)
        assert permission.get_row_permission_filters(session, current_user, ds, tables=["orders"]) == []


def test_table_permission_whitelist_keeps_default_viewer_access(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_table_deny_for_payments_with_permission_whitelist(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show payments",
            embedding=False,
        )

        assert "payments" in tables
        assert "# Table: payments" in schema


def test_user_permission_rules_deny_configured_fields_only(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show orders",
            embedding=False,
        )

        assert tables == ["orders", "payments"]
        assert "# Table: orders" in schema
        assert "# Table: payments" in schema
        assert "order_id" in schema
        assert "amount" not in schema
        assert permission.get_user_scoped_table_ids(session, current_user, 1) == {10, 11}
        assert permission.can_access_table(session, current_user, 1, 10) is True
        assert permission.can_access_table(session, current_user, 1, 11) is True


def test_column_permission_invalid_config_fails_closed(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        session.execute(text(
            """
            INSERT INTO ds_permission
                (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
            VALUES
                (1005, 'bad orders columns', 1, 'user', 'column', 1, 10, '{}', '{bad-json', '[]')
            """
        ))
        session.execute(text(
            """
            INSERT INTO ds_rules
                (id, enable, name, description, permission_list, user_list, white_list_user)
            VALUES
                (2005, 1, 'user 2 bad column rule', '', '[1005]', '[2]', '[]')
            """
        ))
        session.commit()

        ds = session.get(CoreDatasource, 1)
        try:
            datasource_crud.get_table_schema(
                session=session,
                current_user=current_user,
                ds=ds,
                question="show orders",
                embedding=False,
            )
        except ValueError as exc:
            assert "字段权限" in str(exc)
        else:
            raise AssertionError("invalid column permission should fail closed")


def test_normal_user_sample_data_is_not_sent_to_model(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=True: exec_calls.append(sql)
        or {"fields": ["order_id"], "data": [{"order_id": 1}], "sql": sql},
    )

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        sample_data = datasource_crud.get_tables_sample_data(session, current_user, ds)

        assert sample_data == ""
        assert exec_calls == []


def test_sql_permission_scope_denies_hidden_columns(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        _insert_user_table_deny_for_payments(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        _statements, tables, _scope = validate_sql_scope(session, current_user, ds, "select order_id from orders")
        assert tables == {"orders"}

        try:
            validate_sql_scope(session, current_user, ds, "select amount from orders")
        except ValueError as exc:
            assert "无权限字段" in str(exc)
            assert "amount" in str(exc)
        else:
            raise AssertionError("hidden column query should be rejected")


def test_sql_permission_scope_allows_cte_and_output_alias_columns(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        _statements, tables, _scope = validate_sql_scope(
            session,
            current_user,
            ds,
            """
            WITH daily AS (
                SELECT order_id, count(*) AS order_count
                FROM orders
                GROUP BY order_id
            ),
            labeled AS (
                SELECT order_id, order_count, order_count + 1 AS next_count
                FROM daily
            )
            SELECT order_id AS "订单", order_count AS "订单数"
            FROM labeled
            ORDER BY "订单数"
            """,
        )

    assert tables == {"orders"}


def test_sql_permission_scope_denies_hidden_columns_inside_cte(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        with pytest.raises(ValueError) as exc_info:
            validate_sql_scope(
                session,
                current_user,
                ds,
                """
                WITH hidden AS (
                    SELECT order_id, amount AS hidden_amount
                    FROM orders
                )
                SELECT order_id
                FROM hidden
                """,
            )

    assert "无权限字段" in str(exc_info.value)
    assert "amount" in str(exc_info.value)


def test_sql_permission_scope_allows_unqualified_cte_columns_when_joining_physical_table(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        _statements, tables, _scope = validate_sql_scope(
            session,
            current_user,
            ds,
            """
            WITH buckets AS (
                SELECT order_id AS bucket_id
                FROM orders
            )
            SELECT bucket_id, count(o.order_id) AS order_count
            FROM buckets b
            LEFT JOIN orders o ON o.order_id = b.bucket_id
            GROUP BY bucket_id
            ORDER BY bucket_id
            """,
        )

    assert tables == {"orders"}


def test_sql_permission_scope_denies_hidden_unqualified_column_when_joining_cte(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        with pytest.raises(ValueError) as exc_info:
            validate_sql_scope(
                session,
                current_user,
                ds,
                """
                WITH buckets AS (
                    SELECT order_id AS bucket_id
                    FROM orders
                )
                SELECT bucket_id, amount
                FROM buckets b
                JOIN orders o ON o.order_id = b.bucket_id
                """,
            )

    assert "无权限字段" in str(exc_info.value)
    assert "amount" in str(exc_info.value)


def test_sql_permission_scope_allows_values_cte_alias_columns(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        _statements, tables, _scope = validate_sql_scope(
            session,
            current_user,
            ds,
            """
            WITH buckets AS (
                SELECT *
                FROM (VALUES ('low', 1), ('high', 2)) AS t(bucket_name, sort_no)
            ),
            series AS (
                SELECT 'all' AS series_name, 1 AS series_sort
                UNION ALL SELECT 'paid', 2
            ),
            order_counts AS (
                SELECT order_id, count(*) AS order_count
                FROM orders
                GROUP BY order_id
            )
            SELECT b.bucket_name, s.series_name, coalesce(oc.order_count, 0) AS order_count
            FROM buckets b
            CROSS JOIN series s
            LEFT JOIN order_counts oc ON oc.order_id = b.sort_no
            ORDER BY b.sort_no, s.series_sort
            """,
        )

    assert tables == {"orders"}


def test_analysis_assistant_permission_failure_is_structured_and_sanitized(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        try:
            analysis_assistant_api._prepare_sql_for_execution(
                None,
                session,
                current_user,
                ds,
                "select amount from orders",
                ["orders", "payments"],
            )
        except ValueError as exc:
            block = {"summary": "old summary"}
            analysis_assistant_api._mark_query_error_block(block, exc, current_user)
        else:
            raise AssertionError("hidden column query should be rejected")

    assert block["error_type"] == analysis_assistant_api.PERMISSION_DENIED_ERROR_TYPE
    assert block["warning"] == PERMISSION_DENIED_RESULT_MESSAGE
    assert block["agent_guidance"] == PERMISSION_DENIED_AGENT_GUIDANCE
    assert block["error_detail"] == ""
    assert block["summary"] == ""
    assert block["status"] == "failed"
    assert "amount" not in block["warning"]


def test_analysis_assistant_final_prompt_carries_permission_gap(monkeypatch):
    captured = {}

    def fake_llm_text(_llm, messages):
        captured["messages"] = messages
        return "final"

    monkeypatch.setattr(analysis_assistant_api, "_llm_text", fake_llm_text)

    result = analysis_assistant_api._final_answer(
        None,
        "分析经营情况",
        "综合分析",
        [
            {
                "id": "q1",
                "title": "可见收入趋势",
                "purpose": "查看已授权收入走势",
                "summary": "收入上涨。",
                "fields": ["day", "revenue"],
                "data": [{"day": "2026-01-01", "revenue": 100}],
            },
            {
                "id": "q2",
                "title": "受限成本拆解",
                "purpose": "查看成本结构",
                "error_type": analysis_assistant_api.PERMISSION_DENIED_ERROR_TYPE,
                "error": PERMISSION_DENIED_RESULT_MESSAGE,
                "reason": PERMISSION_DENIED_RESULT_MESSAGE,
                "agent_guidance": PERMISSION_DENIED_AGENT_GUIDANCE,
                "fields": [],
                "data": [],
            },
        ],
    )

    user_prompt = captured["messages"][1].content
    assert result == "final"
    assert "受限成本拆解" in user_prompt
    assert "当前用户数据权限受限" in user_prompt
    assert "可能因缺少受限数据而存在偏差" in user_prompt
    assert PERMISSION_DENIED_AGENT_GUIDANCE in user_prompt
    assert "不要猜测或暴露具体受限表名" in user_prompt


def test_analysis_assistant_final_prompt_keeps_complete_lifecycle_rows_and_guardrails(monkeypatch):
    captured = {}

    def fake_llm_text(_llm, messages):
        captured["messages"] = messages
        return "final"

    monkeypatch.setattr(analysis_assistant_api, "_llm_text", fake_llm_text)

    rows = [
        {
            "lifecycle_day": day,
            "daily_payers": 1 if day in {0, 18} else 0,
            "daily_revenue": 169.97 if day == 18 else (17.95 if day == 0 else 0),
            "cumulative_payers": 1 if day < 18 else 2,
            "cumulative_revenue": 17.95 if day < 18 else 187.92,
            "ltv": 0.16 if day < 18 else 1.72,
        }
        for day in range(31)
    ]

    result = analysis_assistant_api._final_answer(
        None,
        "分析某天新增用户后续付费",
        "生命周期分析",
        [
            {
                "id": "q1",
                "title": "生命周期付费趋势",
                "purpose": "查看 D0-D30 生命周期付费趋势",
                "summary": "D18 有收入高点。",
                "fields": [
                    "lifecycle_day",
                    "daily_payers",
                    "daily_revenue",
                    "cumulative_payers",
                    "cumulative_revenue",
                    "ltv",
                ],
                "data": rows,
            },
        ],
    )

    system_prompt = captured["messages"][0].content
    user_prompt = captured["messages"][1].content
    assert result == "final"
    assert '"lifecycle_day":18' in user_prompt
    assert '"daily_revenue":169.97' in user_prompt
    assert "_omitted_middle_rows" not in user_prompt
    assert "不要向业务用户提及 rows" in system_prompt
    assert "不要写成“单笔/单次”" in system_prompt


def test_analysis_assistant_lifecycle_validation_is_skill_declared():
    data_skill = """
<!-- data-skill-validation:{
  "match":["后续付费","LTV"],
  "day_field":["lifecycle_day"],
  "require_continuous_sequence":true,
  "continuous_sequence_message":"生命周期趋势结果缺少连续日期 {missing_days}。请使用 generate_series 或日期序列表补齐观察窗口。",
  "required_fields":["ltv"],
  "required_field_message":"生命周期后续付费分析缺少 {field} 字段。"
} -->
"""
    error = analysis_assistant_api._semantic_validation_error(
        {
            "_user_question": "分析某天新增用户的后续付费和 LTV",
            "title": "新增用户每日付费趋势与 LTV 累积",
            "purpose": "观察生命周期付费和累计收入",
        },
        {
            "fields": ["lifecycle_day", "payers", "daily_revenue", "cumulative_revenue"],
            "data": [
                {"lifecycle_day": 0, "payers": 4, "daily_revenue": 17.95, "cumulative_revenue": 17.95},
                {"lifecycle_day": 1, "payers": 3, "daily_revenue": 14.97, "cumulative_revenue": 32.92},
                {"lifecycle_day": 2, "payers": 3, "daily_revenue": 59.97, "cumulative_revenue": 92.89},
                {"lifecycle_day": 5, "payers": 1, "daily_revenue": 69.98, "cumulative_revenue": 182.86},
            ],
        },
        data_skill,
    )

    assert error
    assert "缺少连续日期" in error
    assert "generate_series" in error


def test_analysis_assistant_business_specific_validation_does_not_run_without_skill_declaration():
    error = analysis_assistant_api._semantic_validation_error(
        {
            "_user_question": "分析某天新增用户的后续付费和 LTV",
            "title": "新增用户每日付费趋势与 LTV 累积",
            "purpose": "观察生命周期付费和累计收入",
        },
        {
            "fields": ["lifecycle_day", "payers", "daily_revenue", "cumulative_revenue"],
            "data": [
                {"lifecycle_day": 0, "payers": 4, "daily_revenue": 17.95, "cumulative_revenue": 17.95},
                {"lifecycle_day": 1, "payers": 3, "daily_revenue": 14.97, "cumulative_revenue": 32.92},
                {"lifecycle_day": 2, "payers": 3, "daily_revenue": 59.97, "cumulative_revenue": 92.89},
                {"lifecycle_day": 5, "payers": 1, "daily_revenue": 69.98, "cumulative_revenue": 182.86},
            ],
        },
    )

    assert error is None


def test_analysis_assistant_lifecycle_validation_accepts_complete_ltv_series():
    data_skill = """
<!-- data-skill-validation:{
  "match":["后续付费","LTV"],
  "day_field":["lifecycle_day"],
  "require_continuous_sequence":true,
  "required_fields":["ltv"],
  "required_field_keywords":[["cumulative_payer","累计付费人数"]]
} -->
"""
    error = analysis_assistant_api._semantic_validation_error(
        {
            "_user_question": "分析某天新增用户的后续付费和 LTV",
            "title": "新增用户生命周期付费趋势",
            "purpose": "观察生命周期累计付费人数、累计收入和 LTV",
        },
        {
            "fields": [
                "lifecycle_day",
                "daily_payers",
                "daily_revenue",
                "cumulative_payers",
                "cumulative_revenue",
                "ltv",
            ],
            "data": [
                {
                    "lifecycle_day": day,
                    "daily_payers": 1 if day in {0, 2} else 0,
                    "daily_revenue": 10 if day in {0, 2} else 0,
                    "cumulative_payers": 1 if day < 2 else 2,
                    "cumulative_revenue": 10 if day < 2 else 20,
                    "ltv": 0.1 if day < 2 else 0.2,
                }
                for day in range(0, 6)
            ],
        },
        data_skill,
    )

    assert error is None


def test_analysis_assistant_db_permission_failure_is_structured_and_sanitized():
    block = {"title": "受限数据检查", "summary": "old summary"}
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    analysis_assistant_api._mark_query_error_block(
        block,
        RuntimeError("psycopg.errors.InsufficientPrivilege: permission denied for relation secret_orders"),
        current_user,
    )

    assert block["status"] == "failed"
    assert block["error_type"] == analysis_assistant_api.PERMISSION_DENIED_ERROR_TYPE
    assert block["warning"] == PERMISSION_DENIED_RESULT_MESSAGE
    assert block["agent_guidance"] == PERMISSION_DENIED_AGENT_GUIDANCE
    assert block["error_detail"] == ""
    assert block["summary"] == ""
    assert "secret_orders" not in block["warning"]


def test_analysis_assistant_data_profile_uses_query_executor(monkeypatch):
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_role="admin", tenant_id=1)
    datasource = SimpleNamespace(id=1, type="pg")
    calls = []

    def fake_execute_user_query_or_raise(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            result={
                "fields": ["f0_max", "f0_min"],
                "data": [{"f0_max": "2026-01-31", "f0_min": "2026-01-01"}],
            }
        )

    monkeypatch.setattr(analysis_assistant_api, "execute_user_query_or_raise", fake_execute_user_query_or_raise)

    profile = analysis_assistant_api._get_data_profile(
        session=object(),
        current_user=current_user,
        datasource=datasource,
        schema="# Table: public.orders\n[\n(order_date:timestamp),\n(amount:numeric)\n]\n",
        allowed_tables=["orders"],
    )

    assert "orders.order_date" in profile
    assert calls
    assert calls[0]["allowed_tables"] == ["orders"]
    assert calls[0]["apply_row_permissions"] is True
    assert "::text" not in calls[0]["sql"]
    assert 'MAX("order_date") AS f0_max' in calls[0]["sql"]


def test_user_schema_filters_relationships_outside_table_scope(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    relations = [
        {
            "shape": "edge",
            "source": {"cell": 10, "port": 100},
            "target": {"cell": 11, "port": 110},
        }
    ]

    with Session(engine) as session:
        datasource = _datasource(1, create_by=9)
        datasource.table_relation = relations
        session.add(datasource)
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        _insert_user_table_deny_for_payments(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show orders",
            embedding=False,
        )

        assert tables == ["orders"]
        assert "【Foreign keys】" not in schema
        assert "payments.payment_id" not in schema
        assert "orders.order_id=payments.payment_id" not in schema


def test_user_schema_filters_relationships_outside_column_scope(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    relations = [
        {
            "shape": "edge",
            "source": {"cell": 10, "port": 101},
            "target": {"cell": 11, "port": 110},
        }
    ]

    with Session(engine) as session:
        datasource = _datasource(1, create_by=9)
        datasource.table_relation = relations
        session.add(datasource)
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        session.execute(
            text(
                """
                INSERT INTO ds_permission
                    (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
                VALUES
                    (1001, 'orders amount hidden', 1, 'user', 'column', 1, 10, '{}', :orders_permissions, '[]'),
                    (1002, 'payments visible', 1, 'user', 'column', 1, 11, '{}', :payments_permissions, '[]')
                """
            ),
            {
                "orders_permissions": json.dumps([
                    {"field_id": 100, "field_name": "order_id", "enable": True},
                    {"field_id": 101, "field_name": "amount", "enable": False},
                ]),
                "payments_permissions": json.dumps([
                    {"field_id": 110, "field_name": "payment_id", "enable": True},
                ]),
            },
        )
        session.execute(
            text(
                """
                INSERT INTO ds_rules
                    (id, enable, name, description, permission_list, user_list, white_list_user)
                VALUES
                    (2001, 1, 'user 2 two tables', '', '[1001,1002]', '[2]', '[]')
                """
            )
        )
        session.commit()

        ds = session.get(CoreDatasource, 1)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show orders and payments",
            embedding=False,
        )

        assert tables == ["orders", "payments"]
        assert "# Table: orders" in schema
        assert "# Table: payments" in schema
        assert "amount" not in schema
        assert "【Foreign keys】" not in schema
        assert "orders.amount=payments.payment_id" not in schema


def test_system_admin_schema_keeps_authorized_relationships(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin", tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    relations = [
        {
            "shape": "edge",
            "source": {"cell": 10, "port": 100},
            "target": {"cell": 11, "port": 110},
        }
    ]

    with Session(engine) as session:
        datasource = _datasource(1, create_by=9)
        datasource.table_relation = relations
        session.add(datasource)
        _insert_table_permission_fixture(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        schema, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show orders and payments",
            embedding=False,
        )

        assert tables == ["orders", "payments"]
        assert "【Foreign keys】" in schema
        assert "orders.order_id=payments.payment_id" in schema


def test_user_without_permission_rules_has_default_table_visibility(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        _, tables = datasource_crud.get_table_schema(
            session=session,
            current_user=current_user,
            ds=ds,
            question="show data",
            embedding=False,
        )

        assert tables == ["orders", "payments"]
        assert permission.get_user_scoped_table_ids(session, current_user, 1) == {10, 11}
        assert permission.can_access_table(session, current_user, 1, 10) is True


def test_preview_denies_configured_denied_tables(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=True: exec_calls.append(sql)
        or {"fields": ["order_id"], "data": [{"order_id": 1}], "sql": sql},
    )

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
        _insert_user_table_deny_for_payments(session)
        session.commit()

        allowed = datasource_crud.preview(
            session,
            current_user,
            1,
            TableObj(table=CoreTable(id=10, ds_id=1, table_name="orders", table_comment="", custom_comment="")),
        )
        denied = datasource_crud.preview(
            session,
            current_user,
            1,
            TableObj(table=CoreTable(id=11, ds_id=1, table_name="payments", table_comment="", custom_comment="")),
        )

        assert allowed["data"] == [{"order_id": 1}]
        assert len(exec_calls) == 1
        assert "orders" in exec_calls[0]
        assert "amount" not in exec_calls[0]
        assert denied == {"fields": [], "data": [], "sql": ""}

