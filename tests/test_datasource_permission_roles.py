import os
import json
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from apps.datasource.crud import datasource as datasource_crud
from apps.datasource.crud import permission
from apps.datasource.models.datasource import CoreDatasource, CoreDatasourceUser, CoreTable, TableObj


def _engine_with_permission_tables():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE core_datasource (
                id INTEGER PRIMARY KEY,
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
            CREATE TABLE ds_rules (
                id INTEGER PRIMARY KEY,
                enable BOOLEAN NOT NULL,
                name VARCHAR NOT NULL,
                description VARCHAR,
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
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (1, 'first-user', 'First User', '', 'first@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (2, 'editor', 'Editor', '', 'editor@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (3, 'project-admin', 'Project Admin', '', 'admin@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (4, 'sysadmin', 'System Admin', '', 'sysadmin@example.com', 1, 0, 1, 'zh-CN', 'system_admin')
            """
        ))
    return engine


def _datasource(datasource_id=1, create_by=9):
    return CoreDatasource(
        id=datasource_id,
        name=f"Project {datasource_id}",
        type="pg",
        configuration="{}",
        create_by=create_by,
        recommended_config=1,
    )


def test_datasource_role_defaults_to_viewer_for_existing_membership():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) == "viewer"
        assert permission.has_datasource_role(session, current_user, 1, "project_viewer") is True
        assert permission.has_datasource_role(session, current_user, 1, "project_editor") is False


def test_datasource_editor_satisfies_dashboard_edit_role():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="editor"))
        session.commit()

        assert permission.has_datasource_role(session, current_user, 1, "project_editor") is True
        assert permission.has_datasource_role(session, current_user, 1, "project_admin") is False


def test_datasource_creator_is_project_admin_without_membership_row():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=2))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) == "admin"
        assert permission.has_datasource_role(session, current_user, 1, "project_admin") is True


def test_missing_datasource_membership_does_not_default_to_viewer():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) is None
        assert permission.has_datasource_role(session, current_user, 1, "project_viewer") is False


def test_update_datasource_users_excludes_system_admin_by_role_not_user_id():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin")

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
            {"user_id": 3, "role": "admin"},
        ]
        assert permission.list_datasource_user_ids(session, 1) == [1, 2, 3]
        assert permission.list_user_datasource_roles(session, 2) == {1: "editor"}


def test_update_user_datasources_excludes_system_admin_by_role_not_user_id():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin")

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(_datasource(2))
        session.commit()

        assert permission.update_user_datasources(session, current_user, 1, [1]) == [1]
        assert permission.update_user_datasources(session, current_user, 4, [1, 2]) == []
        session.commit()

        assert permission.list_user_datasource_roles(session, 1) == {1: "viewer"}
        assert permission.list_user_datasource_roles(session, 4) == {}


def test_get_datasource_ids_with_min_role_filters_by_project_role():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

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
        assert permission.get_datasource_ids_with_min_role(session, current_user, "editor") == {2, 3, 4}
        assert permission.get_datasource_ids_with_min_role(session, current_user, "admin") == {3, 4}


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


def test_user_permission_rules_scope_visible_tables_and_fields(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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

        assert tables == ["orders"]
        assert "# Table: orders" in schema
        assert "order_id" in schema
        assert "amount" not in schema
        assert "payments" not in schema
        assert permission.get_user_scoped_table_ids(session, current_user, 1) == {10}
        assert permission.can_access_table(session, current_user, 1, 10) is True
        assert permission.can_access_table(session, current_user, 1, 11) is False


def test_user_without_permission_rules_keeps_project_table_visibility(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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
        assert permission.get_user_scoped_table_ids(session, current_user, 1) is None


def test_preview_denies_tables_outside_user_scope(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)
    exec_calls = []
    monkeypatch.setattr(
        datasource_crud,
        "exec_sql",
        lambda ds, sql, origin_column=True: exec_calls.append(sql)
        or {"fields": ["order_id"], "data": [{"order_id": 1}], "sql": sql},
    )

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        _insert_user_rule_for_orders(session)
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
