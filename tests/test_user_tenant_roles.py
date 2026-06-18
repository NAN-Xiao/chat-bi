import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from apps.system.api import user as user_api
from apps.system.models.tenant import TenantUserModel
from apps.system.models.user import UserModel
from apps.system.schemas.system_schema import UserCreator, UserEditor, UserStatus


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE sys_user (
                id INTEGER PRIMARY KEY,
                account VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                status INTEGER NOT NULL,
                origin INTEGER NOT NULL DEFAULT 0,
                create_time INTEGER NOT NULL,
                language VARCHAR(255),
                system_role VARCHAR(32) NOT NULL DEFAULT 'viewer',
                system_variables TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_tenant (
                id INTEGER PRIMARY KEY,
                code VARCHAR(64) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                status INTEGER NOT NULL DEFAULT 1,
                plan VARCHAR(64) NOT NULL DEFAULT 'default',
                create_time INTEGER NOT NULL,
                update_time INTEGER NOT NULL
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
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                status INTEGER NOT NULL DEFAULT 1,
                create_time INTEGER NOT NULL
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
                id INTEGER PRIMARY KEY,
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
            INSERT INTO sys_tenant
                (id, code, name, status, plan, create_time, update_time)
            VALUES
                (10, 'tenant-a', 'Tenant A', 1, 'default', 1, 1),
                (20, 'tenant-b', 'Tenant B', 1, 'default', 1, 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (1, 'platform-admin', 'Platform Admin', '', 'platform@example.com', 1, 0, 1, 'zh-CN', 'system_admin'),
                (2, 'tenant-admin', 'Tenant Admin', '', 'tenant-admin@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (3, 'tenant-member', 'Tenant Member', '', 'tenant-member@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (4, 'tenant-owner', 'Tenant Owner', '', 'tenant-owner@example.com', 1, 0, 1, 'zh-CN', 'viewer')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_tenant_user
                (id, tenant_id, user_id, role, is_primary, status, create_time)
            VALUES
                (101, 10, 1, 'owner', TRUE, 1, 1),
                (102, 10, 2, 'admin', TRUE, 1, 1),
                (103, 10, 3, 'member', TRUE, 1, 1),
                (104, 20, 3, 'member', FALSE, 1, 1),
                (105, 10, 4, 'owner', FALSE, 1, 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_datasource
                (id, tenant_id, name, description, type, type_name, configuration, create_by, status, recommended_config)
            VALUES
                (501, 10, 'DS A', '', 'postgresql', 'PostgreSQL', '{}', 2, 'success', 1),
                (502, 20, 'DS B', '', 'postgresql', 'PostgreSQL', '{}', 2, 'success', 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_datasource_user
                (id, ds_id, user_id, role, create_by)
            VALUES
                (601, 501, 3, 'viewer', 2),
                (602, 502, 3, 'viewer', 2)
            """
        ))
    return engine


def _tenant_admin():
    return SimpleNamespace(id=2, system_role="viewer", tenant_id=10, tenant_role="admin")


def _platform_admin():
    return SimpleNamespace(id=1, system_role="system_admin", tenant_id=10, tenant_role="owner")


def _trans(key, **_kwargs):
    return key


def test_tenant_admin_creates_enterprise_admin_without_platform_role():
    engine = _engine()
    with Session(engine) as session:
        created = asyncio.run(user_api.create(
            session=session,
            current_user=_tenant_admin(),
            creator=UserCreator(
                account="created-admin",
                name="Created Admin",
                email="created-admin@example.com",
                status=1,
                system_role="system_admin",
                tenant_role="admin",
            ),
            trans=_trans,
        ))

        db_user = session.get(UserModel, created.id)
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 10,
                TenantUserModel.user_id == created.id,
            )
        ).one()

        assert db_user.system_role == "viewer"
        assert membership.role == "admin"


def test_platform_admin_can_grant_platform_collab_role_and_owner_membership():
    engine = _engine()
    with Session(engine) as session:
        created = asyncio.run(user_api.create(
            session=session,
            current_user=_platform_admin(),
            creator=UserCreator(
                account="platform-collab",
                name="Platform Collab",
                email="platform-collab@example.com",
                status=1,
                system_role="collab_admin",
                tenant_role="owner",
            ),
            trans=_trans,
        ))

        db_user = session.get(UserModel, created.id)
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 10,
                TenantUserModel.user_id == created.id,
            )
        ).one()

        assert db_user.system_role == "collab_admin"
        assert membership.role == "owner"


def test_tenant_admin_updates_tenant_role_without_escalating_platform_role():
    engine = _engine()
    endpoint = inspect.unwrap(user_api.update)
    with Session(engine) as session:
        asyncio.run(endpoint(
            session=session,
            current_user=_tenant_admin(),
            editor=UserEditor(
                id=3,
                account="tenant-member",
                name="Tenant Member",
                email="tenant-member@example.com",
                status=1,
                origin=0,
                system_role="system_admin",
                tenant_role="admin",
            ),
            trans=_trans,
        ))

        db_user = session.get(UserModel, 3)
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 10,
                TenantUserModel.user_id == 3,
            )
        ).one()

        assert db_user.system_role == "viewer"
        assert membership.role == "admin"


def test_tenant_admin_cannot_update_tenant_owner_even_when_role_is_kept():
    engine = _engine()
    endpoint = inspect.unwrap(user_api.update)
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoint(
                session=session,
                current_user=_tenant_admin(),
                editor=UserEditor(
                    id=4,
                    account="tenant-owner",
                    name="Tenant Owner Changed",
                    email="tenant-owner@example.com",
                    status=1,
                    origin=0,
                    system_role="viewer",
                    tenant_role="owner",
                ),
                trans=_trans,
            ))

        assert exc.value.status_code == 403
        db_user = session.get(UserModel, 4)
        membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 10,
                TenantUserModel.user_id == 4,
            )
        ).one()
        assert db_user.name == "Tenant Owner"
        assert membership.role == "owner"


def test_tenant_admin_removes_member_without_deleting_global_user_or_other_tenant_membership():
    engine = _engine()
    endpoint = inspect.unwrap(user_api.delete)
    with Session(engine) as session:
        asyncio.run(endpoint(session=session, current_user=_tenant_admin(), id=3))

        assert session.get(UserModel, 3) is not None
        tenant_a_membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 10,
                TenantUserModel.user_id == 3,
            )
        ).one()
        tenant_b_membership = session.exec(
            select(TenantUserModel).where(
                TenantUserModel.tenant_id == 20,
                TenantUserModel.user_id == 3,
            )
        ).one()
        assert tenant_a_membership.status == 0
        assert tenant_b_membership.status == 1

        tenant_a_permission = session.exec(
            text("SELECT id FROM core_datasource_user WHERE ds_id = 501 AND user_id = 3")
        ).first()
        tenant_b_permission = session.exec(
            text("SELECT id FROM core_datasource_user WHERE ds_id = 502 AND user_id = 3")
        ).first()
        assert tenant_a_permission is None
        assert tenant_b_permission is not None


def test_tenant_admin_cannot_disable_global_platform_account_status():
    engine = _engine()
    endpoint = inspect.unwrap(user_api.statusChange)
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(endpoint(
                session=session,
                current_user=_tenant_admin(),
                trans=_trans,
                statusDto=UserStatus(id=3, status=0),
            ))

        assert exc.value.status_code == 403
        assert session.get(UserModel, 3).status == 1
