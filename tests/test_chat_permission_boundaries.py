import json
import os
import datetime
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from apps.chat.curd import chat as chat_crud
from apps.chat.models.chat_model import Chat, ChatRecord


def _engine_with_chat_permission_tables():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[Chat.__table__, ChatRecord.__table__])
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE chat_log (
                id INTEGER PRIMARY KEY,
                type VARCHAR(3),
                operate VARCHAR(3),
                pid INTEGER,
                ai_modal_id INTEGER,
                base_modal VARCHAR(255),
                messages TEXT,
                reasoning_content TEXT,
                start_time DATETIME,
                finish_time DATETIME,
                token_usage TEXT,
                local_operation BOOLEAN,
                error BOOLEAN
            )
            """
        ))
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


def _insert_permission_fixture(session: Session):
    session.execute(text(
        """
        INSERT INTO core_datasource
            (id, name, type, type_name, configuration, create_by, recommended_config)
        VALUES
            (1, 'Project 1', 'pg', 'PostgreSQL', '{}', 9, 1)
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_datasource_user (ds_id, user_id, role)
        VALUES (1, 2, 'viewer')
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
        VALUES (10, 1, 1, 'orders', 'orders', 'orders')
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_field
            (id, ds_id, table_id, checked, field_name, field_type, field_comment, custom_comment, field_index)
        VALUES
            (100, 1, 10, 1, 'order_id', 'int', 'order_id', 'order_id', 1),
            (101, 1, 10, 1, 'amount', 'numeric', 'amount', 'amount', 2)
        """
    ))
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


def test_chat_cached_data_is_rechecked_against_current_permissions(monkeypatch):
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    exec_calls = []
    monkeypatch.setattr(
        chat_crud,
        "exec_sql",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"fields": ["amount"], "data": [{"amount": 99}]},
    )

    with Session(engine) as session:
        _insert_permission_fixture(session)
        session.add(ChatRecord(
            id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            sql="select amount from orders",
            data=json.dumps({"fields": ["amount"], "data": [{"amount": 99}]}),
        ))
        session.commit()

        result = chat_crud.get_chart_data_with_user(session, current_user, 1)

    assert exec_calls == []
    assert result["status"] == "failed"
    assert result["message"] == "SQL 超出当前数据权限范围"
    assert "amount" not in result["message"]


def test_chat_history_scrubs_cached_artifacts_after_permission_change(monkeypatch):
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    monkeypatch.setattr(
        chat_crud,
        "exec_sql",
        lambda ds, sql, origin_column=False: {"fields": ["amount"], "data": [{"amount": 99}]},
    )

    with Session(engine) as session:
        _insert_permission_fixture(session)
        session.add(Chat(
            id=1,
            create_by=2,
            create_time=datetime.datetime(2026, 1, 1),
            datasource=1,
            engine_type="PostgreSQL",
            brief="history",
        ))
        session.add(ChatRecord(
            id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            question="show amount",
            sql="select amount from orders",
            sql_answer=json.dumps({"content": "select amount from orders"}),
            chart=json.dumps({"axis": {"y": {"name": "amount", "value": "amount"}}}),
            data=json.dumps({"fields": ["amount"], "data": [{"amount": 99}]}),
        ))
        session.commit()

        result = chat_crud.get_chat_with_records(session, 1, current_user, None, with_data=True)

    record = result.records[0]
    assert record["question"] == "show amount"
    assert record["sql"] is None
    assert record["chart"] is None
    assert record["sql_answer"] is None
    assert record["error"] == "SQL 超出当前数据权限范围"
    assert record["data"]["fields"] == []
    assert record["data"]["data"] == []


def test_normal_user_chat_log_history_hides_internal_messages():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        _insert_permission_fixture(session)
        session.add(ChatRecord(
            id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            sql="select order_id from orders",
        ))
        session.execute(
            text(
                """
                INSERT INTO chat_log (id, type, operate, pid, messages, local_operation, error)
                VALUES
                    (10, '0', '8', 1, :schema_message, 1, 0),
                    (11, '0', '12', 1, :execute_message, 1, 0)
                """
            ),
            {
                "schema_message": json.dumps("schema contains hidden amount"),
                "execute_message": json.dumps({"sql": "select amount from orders", "count": 3}),
            },
        )
        session.commit()

        result = chat_crud.get_chat_log_history(session, 1, current_user)

    assert result.steps[0].message is None
    assert result.steps[1].message == {"count": 3}
