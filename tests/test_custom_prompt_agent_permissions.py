import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    CustomPromptVisibilityScopeEnum,
    find_custom_prompts,
)
from apps.chat.models.custom_prompt_model import CustomPrompt, CustomPromptInfo
from apps.system.api import custom_prompt as custom_prompt_api


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
            CREATE TABLE custom_prompt (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                type VARCHAR(20),
                create_time DATETIME,
                name VARCHAR(255),
                description TEXT,
                target_scope VARCHAR(32),
                active BOOLEAN,
                ai_model_id INTEGER,
                create_by INTEGER,
                visibility_scope VARCHAR(32),
                prompt TEXT,
                specific_ds BOOLEAN,
                datasource_ids TEXT
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO sys_user
                (id, account, name, password, email, status, origin, create_time, language, system_role)
            VALUES
                (2, 'tenant-admin', 'Tenant Admin', '', 'tenant-admin@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (3, 'member', 'Member', '', 'member@example.com', 1, 0, 1, 'zh-CN', 'viewer'),
                (4, 'other-member', 'Other Member', '', 'other@example.com', 1, 0, 1, 'zh-CN', 'viewer')
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_datasource
                (id, tenant_id, name, description, type, type_name, configuration, create_by, status, recommended_config)
            VALUES
                (501, 10, 'Tenant A Project', '', 'postgresql', 'PostgreSQL', '{}', 2, 'success', 1),
                (601, 20, 'Tenant B Project', '', 'postgresql', 'PostgreSQL', '{}', 2, 'success', 1)
            """
        ))
        conn.execute(text(
            """
            INSERT INTO core_datasource_user (ds_id, user_id, role)
            VALUES
                (501, 3, 'viewer'),
                (601, 3, 'viewer')
            """
        ))
    return engine


def _tenant_admin(tenant_id=10):
    return SimpleNamespace(id=2, system_role="viewer", tenant_id=tenant_id, tenant_role="admin")


def _member(user_id=3, tenant_id=10):
    return SimpleNamespace(id=user_id, system_role="viewer", tenant_id=tenant_id, tenant_role="member")


def _prompt_info(**overrides):
    data = {
        "type": CustomPromptTypeEnum.GENERATE_SQL,
        "name": "Agent",
        "description": "",
        "target_scope": CustomPromptTargetScopeEnum.SMART_QA,
        "active": True,
        "prompt": "Use strict business terms.",
        "specific_ds": False,
        "datasource_ids": [],
        "visibility_scope": CustomPromptVisibilityScopeEnum.USER_PRIVATE,
    }
    data.update(overrides)
    return CustomPromptInfo(**data)


def _unwrap(func):
    return inspect.unwrap(func)


def test_tenant_admin_can_manage_current_tenant_public_prompt():
    engine = _engine()
    with Session(engine) as session:
        created_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                name="Tenant Public Agent",
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
            ),
        ))

        row = session.get(CustomPrompt, created_id)
        assert row.tenant_id == 10
        assert row.visibility_scope == CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC.value

        _page, _size, _total, _pages, rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            current_user_id=2,
            can_manage_public=True,
            tenant_id=10,
        )
        public_row = next(item for item in rows if item.id == created_id)
        assert public_row.can_manage is True
        assert public_row.prompt == "Use strict business terms."


def test_user_private_agent_is_user_scoped_not_project_or_tenant_scoped():
    engine = _engine()
    with Session(engine) as session:
        created_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_member(3, 10),
            info=_prompt_info(
                name="My Portable Agent",
                specific_ds=True,
                datasource_ids=[501],
            ),
        ))

        row = session.get(CustomPrompt, created_id)
        assert row.create_by == 3
        assert row.visibility_scope == CustomPromptVisibilityScopeEnum.USER_PRIVATE.value
        assert row.specific_ds is False
        assert row.datasource_ids == []

        _page, _size, _total, _pages, rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            current_user_id=3,
            can_manage_all=False,
            tenant_id=20,
        )
        visible = next(item for item in rows if item.id == created_id)
        assert visible.is_owner is True
        assert visible.can_manage is True
        assert visible.prompt == "Use strict business terms."

        prompt, logs, _model = find_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            datasource=601,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            prompt_id=created_id,
            current_user_id=3,
            tenant_id=20,
        )
        assert "Use strict business terms." in prompt
        assert logs == ["名称：My Portable Agent\n补充提示词：Use strict business terms."]


def test_tenant_admin_cannot_read_update_or_delete_member_private_agent():
    engine = _engine()
    with Session(engine) as session:
        private_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_member(3, 10),
            info=_prompt_info(name="Member Private Agent"),
        ))

        with pytest.raises(HTTPException) as get_exc:
            asyncio.run(custom_prompt_api.get_one(
                session=session,
                current_user=_tenant_admin(10),
                prompt_id=private_id,
            ))
        assert get_exc.value.status_code == 404

        with pytest.raises(HTTPException) as update_exc:
            asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
                session=session,
                current_user=_tenant_admin(10),
                info=_prompt_info(
                    id=private_id,
                    name="Hijacked Agent",
                    visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                ),
            ))
        assert update_exc.value.status_code == 404

        with pytest.raises(HTTPException) as delete_exc:
            asyncio.run(_unwrap(custom_prompt_api.delete)(
                session=session,
                current_user=_tenant_admin(10),
                id_list=[private_id],
            ))
        assert delete_exc.value.status_code == 404
        assert session.get(CustomPrompt, private_id) is not None


def test_other_user_cannot_use_private_agent_even_when_prompt_id_is_known():
    engine = _engine()
    with Session(engine) as session:
        private_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_member(3, 10),
            info=_prompt_info(name="Known ID Agent"),
        ))

        prompt, logs, _model = find_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            prompt_id=private_id,
            current_user_id=4,
            tenant_id=10,
        )

        assert prompt == ""
        assert logs == []
