import json
import os
from types import SimpleNamespace

from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.datasource.crud.query_execution import execute_scoped_query
from common.core.config import settings

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"


def _engine_with_query_permission_tables():
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
    return engine


def _insert_query_fixture(session: Session):
    session.execute(text(
        """
        INSERT INTO core_datasource
            (id, name, type, type_name, configuration, create_by, recommended_config)
        VALUES
            (1, 'Project 1', 'pg', 'PostgreSQL', '{}', 9, 1)
        """
    ))
    session.execute(text("INSERT INTO core_datasource_user (ds_id, user_id, role) VALUES (1, 2, 'viewer')"))
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
            (102, 1, 10, 1, 'region', 'varchar', 'region', 'region', 3),
            (110, 1, 11, 1, 'payment_id', 'int', 'payment_id', 'payment_id', 1)
        """
    ))


def _insert_column_rule(session: Session):
    permissions = json.dumps([
        {"field_id": 100, "field_name": "order_id", "enable": True},
        {"field_id": 101, "field_name": "amount", "enable": False},
        {"field_id": 102, "field_name": "region", "enable": True},
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
            (2000, 1, 'user 2 orders columns', '', '[1000]', '[2]', '[]')
        """
    ))


def _insert_row_rule(session: Session):
    tree = {
        "logic": "AND",
        "items": [
            {
                "type": "item",
                "field_id": 102,
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
            (1001, 'orders rows', 1, 'user', 'row', 1, 10, :tree, '[]', '[]')
        """
    ), {"tree": json.dumps(tree)})
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2001, 1, 'user 2 orders rows', '', '[1001]', '[2]', '[]')
        """
    ))


def _executor(calls: list[str], rows: int = 1, options: list[dict] | None = None):
    def inner(
        _datasource,
        sql,
        origin_column=False,
        execution_timeout_seconds=None,
        fetch_limit=None,
    ):
        calls.append(sql)
        if options is not None:
            options.append({
                "origin_column": origin_column,
                "execution_timeout_seconds": execution_timeout_seconds,
                "fetch_limit": fetch_limit,
            })
        return {
            "fields": ["order_id"],
            "data": [{"order_id": index} for index in range(rows)],
        }

    return inner


def test_execute_scoped_query_allows_select_and_clamps_rows():
    engine = _engine_with_query_permission_tables()
    user = SimpleNamespace(id=2, isAdmin=False)
    calls: list[str] = []

    with Session(engine) as session:
        _insert_query_fixture(session)
        session.commit()

        result = execute_scoped_query(
            session=session,
            current_user=user,
            datasource_id=1,
            sql="select order_id from orders",
            purpose="test",
            row_limit=2,
            executor=_executor(calls, rows=5),
        )

    assert result["status"] == "success"
    assert result["row_count"] == 2
    assert result["truncated"] is True
    assert calls == ["SELECT order_id FROM orders LIMIT 2"]


def test_execute_scoped_query_passes_timeout_and_fetch_limit_to_executor():
    engine = _engine_with_query_permission_tables()
    user = SimpleNamespace(id=2, isAdmin=False)
    calls: list[str] = []
    options: list[dict] = []

    with Session(engine) as session:
        _insert_query_fixture(session)
        session.commit()

        result = execute_scoped_query(
            session=session,
            current_user=user,
            datasource_id=1,
            sql="select order_id from orders limit 5000",
            purpose="test",
            row_limit=25,
            executor=_executor(calls, rows=1, options=options),
        )

    assert result["status"] == "success"
    assert calls == ["SELECT order_id FROM orders LIMIT 25"]
    assert options == [{
        "origin_column": False,
        "execution_timeout_seconds": settings.SQL_QUERY_EXECUTION_TIMEOUT_SECONDS,
        "fetch_limit": 25,
    }]


def test_execute_scoped_query_rejects_multi_statement_and_write_sql():
    engine = _engine_with_query_permission_tables()
    user = SimpleNamespace(id=2, isAdmin=False)
    calls: list[str] = []

    with Session(engine) as session:
        _insert_query_fixture(session)
        session.commit()
        multi = execute_scoped_query(
            session=session,
            current_user=user,
            datasource_id=1,
            sql="select order_id from orders; select payment_id from payments",
            purpose="test",
            executor=_executor(calls),
        )
        write = execute_scoped_query(
            session=session,
            current_user=user,
            datasource_id=1,
            sql="delete from orders",
            purpose="test",
            executor=_executor(calls),
        )

    assert multi["status"] == "failed"
    assert write["status"] == "failed"
    assert calls == []


def test_execute_scoped_query_denies_restricted_fields_without_leaking_to_normal_user():
    engine = _engine_with_query_permission_tables()
    user = SimpleNamespace(id=2, isAdmin=False)
    calls: list[str] = []

    with Session(engine) as session:
        _insert_query_fixture(session)
        _insert_column_rule(session)
        session.commit()

        result = execute_scoped_query(
            session=session,
            current_user=user,
            datasource_id=1,
            sql="select amount from orders",
            purpose="test",
            executor=_executor(calls),
        )

    assert result["status"] == "failed"
    assert result["message"] == "SQL 超出当前数据权限范围"
    assert "amount" not in result["message"]
    assert calls == []


def test_execute_scoped_query_applies_row_permissions_and_revalidates_rewrite():
    engine = _engine_with_query_permission_tables()
    user = SimpleNamespace(id=2, isAdmin=False)
    calls: list[str] = []

    with Session(engine) as session:
        _insert_query_fixture(session)
        _insert_row_rule(session)
        session.commit()

        result = execute_scoped_query(
            session=session,
            current_user=user,
            datasource_id=1,
            sql="select order_id from orders",
            purpose="test",
            executor=_executor(calls),
        )

    assert result["status"] == "success"
    assert len(calls) == 1
    assert "FROM (SELECT * FROM orders WHERE" in calls[0]
    assert "LIMIT 1000" in calls[0]
    assert "region" in calls[0]
