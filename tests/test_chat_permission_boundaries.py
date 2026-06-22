import json
import os
import datetime
import asyncio
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine
from fastapi import HTTPException

from apps.chat.api import chat as chat_api
from apps.chat.curd import chat as chat_crud
from apps.chat.models.chat_model import Chat, ChatRecord
from apps.chat.task.llm import format_chart_data_for_agent_prompt
from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_AGENT_GUIDANCE,
    looks_like_permission_scope_error,
    permission_denied_result,
)


def _engine_with_chat_permission_tables():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[Chat.__table__, ChatRecord.__table__])
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE chat_log (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
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


def test_failed_chart_data_is_preserved_for_agent_prompt():
    payload = {
        "status": "failed",
        "error_type": "permission_denied",
        "fields": [],
        "data": [],
        "message": "当前用户对该项目的表或字段权限受限，无法返回这部分数据。",
        "reason": "当前用户对该项目的表或字段权限受限，无法返回这部分数据。",
    }

    result = json.loads(format_chart_data_for_agent_prompt(payload))

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["message"] == payload["message"]
    assert result["warning"] == payload["message"]
    assert result["agent_guidance"] == PERMISSION_DENIED_AGENT_GUIDANCE
    assert "data" not in result


def test_db_permission_errors_are_detected_and_warning_is_preserved():
    assert looks_like_permission_scope_error(
        "psycopg.errors.InsufficientPrivilege: permission denied for relation secret_orders"
    )

    payload = permission_denied_result()
    result = chat_crud.format_json_data(payload)

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["warning"] == payload["warning"]
    assert result["agent_guidance"] == payload["agent_guidance"]


def test_chat_cached_data_is_rechecked_against_current_permissions():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

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

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["message"] == "SQL 超出当前数据权限范围"
    assert "amount" not in result["message"]


def test_chat_history_scrubs_cached_artifacts_after_permission_change():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

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
    assert record["data"]["error_type"] == "permission_denied"


def test_chat_excel_export_rechecks_current_permissions():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    trans = lambda key: key

    with Session(engine) as session:
        _insert_permission_fixture(session)
        session.add(ChatRecord(
            id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            sql="select amount from orders",
            chart=json.dumps({"axis": {"y": {"name": "amount", "value": "amount"}}}),
            data=json.dumps({"fields": ["amount"], "data": [{"amount": 99}]}),
        ))
        session.commit()

        caught = None
        try:
            asyncio.run(
                chat_api.export_excel.__wrapped__(
                    session=session,
                    current_user=current_user,
                    chat_record_id=1,
                    chat_id=1,
                    trans=trans,
                )
            )
        except chat_api.HTTPException as exc:
            caught = exc

    assert caught is not None
    assert caught.status_code == 500
    assert caught.detail == "SQL 超出当前数据权限范围"
    assert "amount" not in caught.detail


def test_normal_user_chat_log_history_hides_internal_messages():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

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


def test_chat_log_history_queries_use_scalar_tenant_id():
    engine = _engine_with_chat_permission_tables()

    with Session(engine) as session:
        session.add(Chat(
            id=1,
            tenant_id=11,
            create_by=2,
            create_time=datetime.datetime(2026, 6, 18),
            datasource=1,
            engine_type="PostgreSQL",
            brief="retention",
        ))
        session.add(ChatRecord(
            id=10,
            tenant_id=11,
            chat_id=1,
            create_by=2,
            datasource=1,
            question="6月18号用户留存数据",
        ))
        session.execute(
            text(
                """
                INSERT INTO chat_log (id, tenant_id, type, operate, pid, messages, local_operation, error)
                VALUES
                    (101, 11, '0', '0', 10, :sql_message, 0, 0),
                    (102, 11, '0', '1', 10, :chart_message, 0, 0)
                """
            ),
            {
                "sql_message": json.dumps([{"role": "user", "content": "retention"}]),
                "chart_message": json.dumps([{"role": "assistant", "content": "chart"}]),
            },
        )
        session.commit()

        assert chat_crud._record_tenant_id(session, 10) == 11
        sql_logs = chat_crud.list_generate_sql_logs(session, 1)
        chart_logs = chat_crud.list_generate_chart_logs(session, 1)

    assert [log.id for log in sql_logs] == [101]
    assert [log.id for log in chart_logs] == [102]


def test_chat_list_is_scoped_to_current_workspace_even_for_same_user(monkeypatch):
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=20)
    monkeypatch.setattr(chat_crud, "get_accessible_datasource_ids", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(Chat(
            id=1,
            tenant_id=10,
            create_by=2,
            create_time=datetime.datetime(2026, 6, 18),
            datasource=None,
            engine_type="",
            brief="tenant-10-record",
        ))
        session.add(Chat(
            id=2,
            tenant_id=20,
            create_by=2,
            create_time=datetime.datetime(2026, 6, 19),
            datasource=None,
            engine_type="",
            brief="tenant-20-record",
        ))
        session.commit()

        result = chat_crud.list_chats(session, current_user)

    assert [chat.id for chat in result] == [2]


def test_old_questions_are_scoped_to_current_workspace_even_for_same_user():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=20)

    with Session(engine) as session:
        session.add(ChatRecord(
            id=1,
            tenant_id=10,
            chat_id=1,
            create_by=2,
            datasource=1,
            question="tenant 10 question",
            create_time=datetime.datetime(2026, 6, 18),
        ))
        session.add(ChatRecord(
            id=2,
            tenant_id=20,
            chat_id=2,
            create_by=2,
            datasource=1,
            question="tenant 20 question",
            create_time=datetime.datetime(2026, 6, 19),
        ))
        session.commit()

        result = chat_crud.get_old_questions(session, 1, current_user)

    assert result == ["tenant 20 question"]


def test_chat_detail_requires_current_tenant():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=2)

    with Session(engine) as session:
        session.add(Chat(
            id=1,
            tenant_id=1,
            create_by=2,
            create_time=datetime.datetime(2026, 1, 1),
            datasource=None,
            engine_type="",
            brief="tenant-one",
        ))
        session.commit()

        try:
            chat_crud.get_chat_with_records(session, 1, current_user, None, with_data=True)
        except Exception as exc:
            assert "not Owned by the current user" in str(exc)
        else:
            raise AssertionError("cross-tenant chat detail should be denied")


def test_chat_record_data_requires_current_tenant():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=2)

    with Session(engine) as session:
        _insert_permission_fixture(session)
        session.add(ChatRecord(
            id=1,
            tenant_id=1,
            chat_id=1,
            create_by=2,
            datasource=1,
            sql="select amount from orders",
            data=json.dumps({"fields": ["amount"], "data": [{"amount": 99}]}),
        ))
        session.commit()

        result = chat_crud.get_chart_data_with_user(session, current_user, 1)

    assert result == {}


def test_chat_business_service_requires_explicit_tenant_context():
    engine = _engine_with_chat_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)

    with Session(engine) as session:
        session.add(Chat(
            id=1,
            tenant_id=1,
            create_by=2,
            create_time=datetime.datetime(2026, 1, 1),
            datasource=None,
            engine_type="",
            brief="default-tenant",
        ))
        session.commit()

        try:
            chat_crud.get_chat_with_records(session, 1, current_user, None, with_data=True)
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("business chat access should require an explicit tenant context")
