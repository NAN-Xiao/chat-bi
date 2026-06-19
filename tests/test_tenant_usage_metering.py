import asyncio
import os
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, create_engine

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.system.api import tenant as tenant_api
from apps.system.crud.tenant_usage import (
    check_tenant_usage_quota,
    list_tenant_usage_by_user,
    list_tenant_usage_daily,
    record_tenant_usage,
    token_total,
)
from apps.system.models.tenant import TenantModel
from apps.system.models.tenant_usage import TenantUsageDailyModel
from common.core.config import settings


def _engine_with_usage_table():
    engine = create_engine("sqlite://")
    TenantUsageDailyModel.__table__.create(engine)
    return engine


def _engine_with_usage_and_tenant_tables():
    engine = create_engine("sqlite://")
    TenantModel.__table__.create(engine)
    TenantUsageDailyModel.__table__.create(engine)
    return engine


def _engine_with_chat_usage_tables():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sys_user (id INTEGER PRIMARY KEY, account TEXT, name TEXT)"))
        connection.execute(
            text(
                """
                CREATE TABLE chat_record (
                    id INTEGER PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    chat_id INTEGER,
                    create_by INTEGER,
                    create_time DATETIME,
                    finish_time DATETIME,
                    engine_type TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE chat_log (
                    id INTEGER PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    type TEXT,
                    operate TEXT,
                    pid INTEGER,
                    token_usage TEXT,
                    local_operation BOOLEAN DEFAULT 0,
                    error BOOLEAN DEFAULT 0,
                    start_time DATETIME,
                    finish_time DATETIME
                )
                """
            )
        )
    return engine


def test_tenant_usage_records_increment_daily_metrics(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    engine = _engine_with_usage_table()

    with Session(engine) as session:
        assert record_tenant_usage(
            session,
            tenant_id=10,
            metric="chat.generate_sql",
            usage_date="2026-06-18",
            request_count=1,
            success_count=1,
            total_tokens=120,
        )
        assert record_tenant_usage(
            session,
            tenant_id=10,
            metric="chat.generate_sql",
            usage_date="2026-06-18",
            request_count=1,
            failure_count=1,
            total_tokens=30,
        )
        session.commit()

        rows = list_tenant_usage_daily(session, tenant_id=10, start_date="2026-06-18", end_date="2026-06-18")

    assert len(rows) == 1
    assert rows[0].metric == "chat.generate_sql"
    assert rows[0].request_count == 2
    assert rows[0].success_count == 1
    assert rows[0].failure_count == 1
    assert rows[0].total_tokens == 150


def test_tenant_usage_skips_when_table_missing(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    engine = create_engine("sqlite://")

    with Session(engine) as session:
        assert record_tenant_usage(session, tenant_id=10, metric="chat.generate_sql") is False
        assert list_tenant_usage_daily(session, tenant_id=10) == []


def test_token_total_accepts_common_usage_shapes():
    assert token_total({"total_tokens": "42"}) == 42
    assert token_total(7) == 7
    assert token_total({"input_tokens": 1}) == 0
    assert token_total(None) == 0


def test_tenant_usage_by_user_scopes_current_workspace_only():
    engine = _engine_with_chat_usage_tables()

    with Session(engine) as session:
        session.exec(text("INSERT INTO sys_user (id, account, name) VALUES (7, 'alice', 'Alice')"))
        session.exec(
            text(
                """
                INSERT INTO chat_record (id, tenant_id, chat_id, create_by, create_time, finish_time, engine_type)
                VALUES
                    (101, 200, 1, 7, '2026-06-18 09:00:00', '2026-06-18 09:01:00', 'postgres'),
                    (102, 300, 2, 7, '2026-06-18 10:00:00', '2026-06-18 10:01:00', 'postgres')
                """
            )
        )
        session.exec(
            text(
                """
                INSERT INTO chat_log (
                    id, tenant_id, type, operate, pid, token_usage, local_operation, error, start_time, finish_time
                )
                VALUES
                    (201, 200, '0', '0', 101, '{"total_tokens": 120}', 0, 0, '2026-06-18 09:00:00', '2026-06-18 09:01:00'),
                    (202, 300, '0', '0', 102, '{"total_tokens": 900}', 0, 0, '2026-06-18 10:00:00', '2026-06-18 10:01:00')
                """
            )
        )
        session.commit()

        rows = list_tenant_usage_by_user(
            session,
            tenant_id=200,
            start_date="2026-06-18",
            end_date="2026-06-18",
        )

    assert len(rows) == 1
    assert rows[0]["tenant_id"] == 200
    assert rows[0]["user_id"] == 7
    assert rows[0]["user_account"] == "alice"
    assert rows[0]["total_tokens"] == 120
    assert rows[0]["request_count"] == 1


def test_usage_quota_blocks_when_daily_action_limit_is_reached(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_PLAN_LIMITS", '{"default":{"daily":{"chat":2}}}')
    engine = _engine_with_usage_table()

    with Session(engine) as session:
        record_tenant_usage(
            session,
            tenant_id=10,
            metric="chat.generate_sql",
            usage_date="2026-06-18",
            request_count=2,
            success_count=2,
        )
        session.commit()

        state = check_tenant_usage_quota(
            session,
            tenant_id=10,
            action="chat",
            now=datetime(2026, 6, 18),
        )

    assert state.allowed is False
    assert state.window == "daily"
    assert state.used == 2
    assert state.limit == 2


def test_usage_quota_uses_tenant_plan_and_action_metric_group(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_PLAN_LIMITS", '{"basic":{"monthly":{"analysis":3}}}')
    engine = _engine_with_usage_and_tenant_tables()

    with Session(engine) as session:
        session.add(TenantModel(id=20, code="tenant-basic", name="Tenant Basic", status=1, plan="basic"))
        record_tenant_usage(
            session,
            tenant_id=20,
            metric="analysis_assistant.request",
            usage_date="2026-06-01",
            request_count=2,
        )
        record_tenant_usage(
            session,
            tenant_id=20,
            metric="chat.analysis",
            usage_date="2026-06-18",
            request_count=1,
        )
        session.commit()

        state = check_tenant_usage_quota(
            session,
            tenant_id=20,
            action="analysis",
            now=datetime(2026, 6, 18),
        )

    assert state.allowed is False
    assert state.plan == "basic"
    assert state.window == "monthly"
    assert state.used == 3
    assert state.limit == 3


def test_past_due_subscription_does_not_auto_stop_high_cost_features(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_ENABLED", True)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_PLAN_LIMITS", "")
    engine = _engine_with_usage_and_tenant_tables()

    with Session(engine) as session:
        session.add(
            TenantModel(
                id=30,
                code="tenant-past-due",
                name="Tenant Past Due",
                status=1,
                plan="basic",
                subscription_status="past_due",
                current_period_end_time=1,
            )
        )
        session.commit()

        state = check_tenant_usage_quota(session, tenant_id=30, action="chat")

    assert state.allowed is True
    assert state.subscription_status == "past_due"


def test_suspended_subscription_blocks_high_cost_features_even_without_quota(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_ENABLED", False)
    monkeypatch.setattr(settings, "TENANT_USAGE_QUOTA_PLAN_LIMITS", "")
    engine = _engine_with_usage_and_tenant_tables()

    with Session(engine) as session:
        session.add(
            TenantModel(
                id=31,
                code="tenant-suspended",
                name="Tenant Suspended",
                status=1,
                plan="enterprise",
                subscription_status="suspended",
            )
        )
        session.commit()

        state = check_tenant_usage_quota(session, tenant_id=31, action="analysis")

    assert state.allowed is False
    assert state.reason == "subscription_suspended"
    assert state.window == "subscription"
    assert state.subscription_status == "suspended"


def test_tenant_usage_endpoint_scopes_tenant_admin(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    engine = _engine_with_usage_table()

    with Session(engine) as session:
        record_tenant_usage(
            session,
            tenant_id=200,
            metric="analysis_assistant.request",
            usage_date="2026-06-18",
            request_count=2,
            success_count=2,
        )
        record_tenant_usage(
            session,
            tenant_id=300,
            metric="analysis_assistant.request",
            usage_date="2026-06-18",
            request_count=9,
            success_count=9,
        )
        session.commit()

        tenant_admin = SimpleNamespace(id=2, system_role="viewer", tenant_id=200, tenant_role="admin")
        current_tenant = SimpleNamespace(id=200, code="tenant-b", name="Tenant B", role="admin")
        rows = asyncio.run(
            tenant_api.tenant_usage(
                session=session,
                current_user=tenant_admin,
                current_tenant=current_tenant,
                start_date=None,
                end_date=None,
                metric=None,
                limit=500,
            )
        )

        assert len(rows) == 1
        assert rows[0].tenant_id == 200
        assert rows[0].request_count == 2

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                tenant_api.tenant_usage(
                    session=session,
                    current_user=tenant_admin,
                    current_tenant=current_tenant,
                    tenant_id=300,
                    start_date=None,
                    end_date=None,
                    metric=None,
                    limit=500,
                )
            )
        assert exc.value.status_code == 403


def test_tenant_usage_endpoint_allows_platform_admin_filter(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_USAGE_METERING_ENABLED", True)
    engine = _engine_with_usage_table()

    with Session(engine) as session:
        record_tenant_usage(session, tenant_id=200, metric="task.enqueued", usage_date="2026-06-18", task_count=1)
        record_tenant_usage(session, tenant_id=300, metric="task.enqueued", usage_date="2026-06-18", task_count=2)
        session.commit()

        platform_admin = SimpleNamespace(id=1, system_role="system_admin", tenant_id=1, tenant_role="owner")
        current_tenant = SimpleNamespace(id=1, code="default", name="Default", role="owner")
        rows = asyncio.run(
            tenant_api.tenant_usage(
                session=session,
                current_user=platform_admin,
                current_tenant=current_tenant,
                tenant_id=300,
                start_date=None,
                end_date=None,
                metric=None,
                limit=500,
            )
        )

    assert len(rows) == 1
    assert rows[0].tenant_id == 300
    assert rows[0].task_count == 2
