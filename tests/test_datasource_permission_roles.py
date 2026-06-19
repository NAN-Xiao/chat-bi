import os
import json
import asyncio
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from apps.datasource.crud import datasource as datasource_crud
from apps.datasource.api import datasource as datasource_api
from apps.datasource.crud import permission
from apps.datasource.crud.analysis_context import resolve_datasource_context
from apps.datasource.crud.sql_permission import validate_sql_scope
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
                (3, 'analyst', 'Analyst', '', 'analyst@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
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


def test_datasource_creator_is_not_implicitly_project_member_without_membership_row():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=2))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) is None
        assert permission.has_datasource_role(session, current_user, 1, "project_viewer") is False


def test_missing_datasource_membership_does_not_default_to_viewer():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(_datasource(1))
        session.commit()

        assert permission.get_datasource_role(session, current_user, 1) is None
        assert permission.has_datasource_role(session, current_user, 1, "project_viewer") is False


def test_datasource_list_hides_connection_config_for_normal_users():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    system_admin = SimpleNamespace(id=4, system_role="system_admin")

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        session.commit()

        normal_items = asyncio.run(datasource_api.datasource_list(session, current_user))
        admin_items = asyncio.run(datasource_api.datasource_list(session, system_admin))

        assert normal_items[0]["configuration"] is None
        assert admin_items[0]["configuration"] == "{}"
        assert normal_items[0]["can_manage_project"] is False
        assert admin_items[0]["can_manage_project"] is True


def test_get_datasource_redacts_config_without_mutating_record():
    engine = _engine_with_permission_tables()
    normal_user = SimpleNamespace(id=2, isAdmin=False)
    admin_user = SimpleNamespace(id=4, system_role="system_admin")

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
    current_user = SimpleNamespace(id=4, system_role="system_admin")
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
            {"user_id": 3, "role": "editor"},
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


def test_update_user_datasources_saves_project_role_map_for_new_memberships():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin")

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

        assert permission.list_user_datasource_roles(session, 2) == {
            1: "editor",
            2: "viewer",
        }


def test_update_user_datasources_updates_existing_project_roles():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin")

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

        assert permission.list_user_datasource_roles(session, 2) == {1: "editor"}


def test_update_user_datasources_preserves_existing_roles_when_role_map_omitted():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=4, system_role="system_admin")

    with Session(engine) as session:
        session.add(_datasource(1))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="editor"))
        session.commit()

        assert permission.update_user_datasources(session, current_user, 2, [1]) == [1]
        session.commit()

        assert permission.list_user_datasource_roles(session, 2) == {1: "editor"}


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

        assert permission.get_datasource_ids_with_min_role(session, current_user, "viewer") == {1, 2, 3}
        assert permission.get_datasource_ids_with_min_role(session, current_user, "editor") == {2, 3}
        assert permission.get_datasource_ids_with_min_role(session, current_user, "admin") == set()


def test_resolve_datasource_context_rejects_invalid_datasource_id():
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        try:
            resolve_datasource_context(session, current_user, "not-a-number")
        except RuntimeError as exc:
            assert str(exc) == "项目 ID 无效"
        else:
            raise AssertionError("invalid datasource id should be rejected as a business error")


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


def test_user_permission_rules_deny_configured_fields_only(monkeypatch):
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

        assert tables == ["orders", "payments"]
        assert "# Table: orders" in schema
        assert "# Table: payments" in schema
        assert "order_id" in schema
        assert "amount" not in schema
        assert permission.get_user_scoped_table_ids(session, current_user, 1) == {10, 11}
        assert permission.can_access_table(session, current_user, 1, 10) is True
        assert permission.can_access_table(session, current_user, 1, 11) is True


def test_normal_user_sample_data_is_not_sent_to_model(monkeypatch):
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
        session.commit()

        ds = session.get(CoreDatasource, 1)
        sample_data = datasource_crud.get_tables_sample_data(session, current_user, ds)

        assert sample_data == ""
        assert exec_calls == []


def test_sql_permission_scope_denies_hidden_columns(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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


def test_sql_permission_scope_allows_select_alias_order_by_for_project_viewer(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda value: value)

    with Session(engine) as session:
        session.add(_datasource(1, create_by=9))
        session.add(CoreDatasourceUser(ds_id=1, user_id=2, role="viewer"))
        _insert_table_permission_fixture(session)
        session.commit()

        ds = session.get(CoreDatasource, 1)
        _statements, tables, _scope = validate_sql_scope(
            session,
            current_user,
            ds,
            """
            select order_id, count(*) as cohort_players
            from orders
            group by order_id
            order by cohort_players desc
            """,
        )

        assert tables == {"orders"}


def test_sql_permission_scope_still_denies_real_hidden_columns_with_alias_order_by(monkeypatch):
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
        try:
            validate_sql_scope(
                session,
                current_user,
                ds,
                """
                select amount, count(*) as cohort_players
                from orders
                group by amount
                order by cohort_players desc
                """,
            )
        except ValueError as exc:
            assert "无权限字段" in str(exc)
            assert "amount" in str(exc)
            assert "cohort_players" not in str(exc)
        else:
            raise AssertionError("hidden column query should still be rejected")


def test_user_schema_filters_relationships_outside_table_scope(monkeypatch):
    engine = _engine_with_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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
    current_user = SimpleNamespace(id=2, isAdmin=False)
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
    current_user = SimpleNamespace(id=4, system_role="system_admin")
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
        assert permission.get_user_scoped_table_ids(session, current_user, 1) == {10, 11}
        assert permission.can_access_table(session, current_user, 1, 10) is True


def test_preview_denies_configured_denied_tables(monkeypatch):
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
