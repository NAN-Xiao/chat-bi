import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from apps.system.api import audit as audit_api
from common.audit.models.log_model import OperationStatus, OperationType, SystemLog, SystemLogsResource


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SystemLog.__table__.create(engine)
    SystemLogsResource.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sys_user (id INTEGER PRIMARY KEY, name VARCHAR(255))"))
        conn.execute(text(
            """
            CREATE TABLE sys_tenant_user (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status INTEGER NOT NULL DEFAULT 1
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_user (id, name)
            VALUES (1, 'Platform Admin'), (2, 'Tenant A Admin'), (3, 'Tenant B Admin')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_tenant_user (id, tenant_id, user_id, status)
            VALUES (101, 10, 2, 1), (102, 20, 3, 1)
            """
        ))
    return engine


def _request():
    return SimpleNamespace(query_params={})


def _tenant_admin(tenant_id=10):
    return SimpleNamespace(id=2, system_role="viewer", tenant_id=tenant_id, tenant_role="admin")


def _platform_admin():
    return SimpleNamespace(id=1, system_role="system_admin", tenant_id=10, tenant_role="owner")


def _add_log(session: Session, tenant_id: int, detail: str):
    session.add(
        SystemLog(
            tenant_id=tenant_id,
            operation_type=OperationType.UPDATE.value,
            operation_detail=detail,
            user_id=2,
            user_name="Tenant Admin",
            operation_status=OperationStatus.SUCCESS.value,
            module="member",
        )
    )
    session.commit()


def test_tenant_admin_audit_page_is_scoped_to_current_tenant():
    engine = _engine()
    endpoint = inspect.unwrap(audit_api.page)
    with Session(engine) as session:
        _add_log(session, tenant_id=10, detail="tenant-a-only")
        _add_log(session, tenant_id=20, detail="tenant-b-only")

        result = asyncio.run(endpoint(
            session=session,
            request=_request(),
            current_user=_tenant_admin(tenant_id=10),
            page_num=1,
            page_size=20,
        ))

        assert result["total_count"] == 1
        assert [row["operation_detail_info"] for row in result["data"]] == ["tenant-a-only"]


def test_platform_admin_audit_page_can_view_all_tenants():
    engine = _engine()
    endpoint = inspect.unwrap(audit_api.page)
    with Session(engine) as session:
        _add_log(session, tenant_id=10, detail="tenant-a-only")
        _add_log(session, tenant_id=20, detail="tenant-b-only")

        result = asyncio.run(endpoint(
            session=session,
            request=_request(),
            current_user=_platform_admin(),
            page_num=1,
            page_size=20,
        ))

        assert result["total_count"] == 2
        assert {row["operation_detail_info"] for row in result["data"]} == {
            "tenant-a-only",
            "tenant-b-only",
        }


def test_tenant_admin_audit_user_options_are_scoped_to_current_tenant():
    engine = _engine()
    endpoint = inspect.unwrap(audit_api.users)
    with Session(engine) as session:
        result = asyncio.run(endpoint(session=session, current_user=_tenant_admin(tenant_id=10)))

        assert result == [{"id": 2, "name": "Tenant A Admin"}]


def test_tenant_audit_requires_explicit_workspace_context():
    engine = _engine()
    endpoint = inspect.unwrap(audit_api.page)
    with Session(engine) as session:
        _add_log(session, tenant_id=1, detail="default-tenant-log")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoint(
                session=session,
                request=_request(),
                current_user=_tenant_admin(tenant_id=None),
                page_num=1,
                page_size=20,
            ))

        assert exc.value.status_code == 403
