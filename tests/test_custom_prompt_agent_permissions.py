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
    find_data_skills,
)
from apps.chat.models.chat_model import ChatQuestion
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
            CREATE TABLE custom_prompt_user_preference (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                custom_prompt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                update_time DATETIME,
                UNIQUE(custom_prompt_id, user_id)
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


def _platform_admin():
    return SimpleNamespace(id=1, system_role="system_admin", tenant_id=1, tenant_role="owner")


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


def test_platform_agent_is_visible_to_tenants_but_read_only_and_runtime_usable():
    engine = _engine()
    with Session(engine) as session:
        platform_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_platform_admin(),
            info=_prompt_info(
                name="Platform Foundation Agent",
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                specific_ds=True,
                datasource_ids=[501],
            ),
        ))

        row = session.get(CustomPrompt, platform_id)
        assert row.tenant_id == 1
        assert row.visibility_scope == CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC.value
        assert row.specific_ds is False
        assert row.datasource_ids == []

        _page, _size, _total, _pages, rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            current_user_id=2,
            can_manage_public=True,
            tenant_id=10,
        )
        visible = next(item for item in rows if item.id == platform_id)
        assert visible.can_manage is False
        assert visible.prompt == "Use strict business terms."

        _page, _size, _total, _pages, workspace_rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            current_user_id=2,
            can_manage_public=True,
            tenant_id=10,
            visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
        )
        assert all(item.id != platform_id for item in workspace_rows)

        with pytest.raises(HTTPException) as delete_exc:
            asyncio.run(_unwrap(custom_prompt_api.delete)(
                session=session,
                current_user=_tenant_admin(10),
                id_list=[platform_id],
            ))
        assert delete_exc.value.status_code == 404

        prompt, logs, _model = find_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            prompt_id=platform_id,
            current_user_id=3,
            tenant_id=10,
        )
        assert "Use strict business terms." in prompt
        assert logs == ["名称：Platform Foundation Agent\n补充提示词：Use strict business terms."]


def test_data_skill_runtime_uses_markdown_skill_block():
    engine = _engine()
    with Session(engine) as session:
        skill_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Revenue Skill",
                description="Revenue metric contract",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt=(
                    "# Revenue Skill\n\n"
                    "## Metric\n"
                    "Revenue must use paid_amount from fact_payment.\n\n"
                    "```sql\n"
                    "select sum(paid_amount) as revenue from fact_payment;\n"
                    "```"
                ),
            ),
        ))

        skill_text, logs, _model = find_data_skills(
            session,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            skill_id=skill_id,
            current_user_id=3,
            tenant_id=10,
        )

        assert "<Data-Skills>" in skill_text
        assert "<Other-Infos>" not in skill_text
        assert "# Revenue Skill" in skill_text
        assert "paid_amount" in skill_text
        assert logs == [
            "名称：Revenue Skill\n描述：Revenue metric contract\nSkill 内容："
            "# Revenue Skill\n\n"
            "## Metric\n"
            "Revenue must use paid_amount from fact_payment.\n\n"
            "```sql\n"
            "select sum(paid_amount) as revenue from fact_payment;\n"
            "```"
        ]


def test_user_disabled_data_skill_is_hidden_from_options_and_runtime():
    engine = _engine()
    with Session(engine) as session:
        skill_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Revenue Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt="# Revenue Skill\nUse paid_amount.",
            ),
        ))

        asyncio.run(custom_prompt_api.set_activation(
            session=session,
            current_user=_member(3, 10),
            prompt_id=skill_id,
            enabled=False,
            scope="user",
        ))

        options = custom_prompt_api.list_custom_prompt_options(
            session,
            CustomPromptTargetScopeEnum.SMART_QA,
            CustomPromptTypeEnum.DATA_SKILL,
            current_user_id=3,
            tenant_id=10,
        )
        skill_text, logs, _model = find_data_skills(
            session,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            skill_id=skill_id,
            current_user_id=3,
            tenant_id=10,
        )

        assert all(option.id != skill_id for option in options)
        assert skill_text == ""
        assert logs == []


def test_data_skills_auto_match_all_active_skills_when_no_skill_is_selected():
    engine = _engine()
    with Session(engine) as session:
        platform_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_platform_admin(),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="SaaS Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC,
                prompt="# SaaS Skill\nUse SaaS defaults.",
            ),
        ))
        revenue_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Revenue Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt="# Revenue Skill\nUse paid_amount.",
            ),
        ))
        retention_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Retention Skill",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt="# Retention Skill\nUse login events.",
            ),
        ))
        personal_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_member(3, 10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="My Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.USER_PRIVATE,
                prompt="# My Skill\nUse my personal preference.",
            ),
        ))
        disabled_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Disabled Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt="# Disabled Skill\nShould not appear.",
            ),
        ))
        asyncio.run(custom_prompt_api.set_activation(
            session=session,
            current_user=_member(3, 10),
            prompt_id=disabled_id,
            enabled=False,
            scope="user",
        ))

        skill_text, logs, _model = find_data_skills(
            session,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            skill_id=None,
            current_user_id=3,
            tenant_id=10,
        )

        assert "<Data-Skills>" in skill_text
        assert "SaaS Skill" in skill_text
        assert "Revenue Skill" in skill_text
        assert "Retention Skill" in skill_text
        assert "My Skill" in skill_text
        assert "Disabled Skill" not in skill_text
        assert len(logs) == 4
        assert any("SaaS Skill" in log for log in logs)
        assert any("Revenue Skill" in log for log in logs)
        assert any("Retention Skill" in log for log in logs)
        assert any("My Skill" in log for log in logs)
        assert platform_id and revenue_id and retention_id and personal_id


def test_data_skill_runtime_hides_split_legacy_semantic_skills_after_combining():
    engine = _engine()
    with Session(engine) as session:
        combined_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="数据 Skill：Tenant A Project",
                description="由旧版术语和 SQL 示例合并生成；适用于数据项目「Tenant A Project」。原始记录保留不删除。",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                active=True,
                specific_ds=True,
                datasource_ids=[501],
                prompt=(
                    "<!-- data-skill-source:legacy-semantic:ADMIN_PUBLIC:10:501 -->\n"
                    "# 数据 Skill：Tenant A Project\n\n"
                    "## 术语与口径\n"
                    "<!-- legacy-terminology:1 -->\n"
                    "- **收入**：使用 paid_amount\n\n"
                    "## SQL 示例\n"
                    "<!-- legacy-data-training:1 -->\n"
                    "### 问题：收入趋势\n\n"
                    "````sql\n"
                    "select date(created_at), sum(paid_amount) from fact_payment group by 1;\n"
                    "````"
                ),
            ),
        ))
        terminology_split_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="术语 Skill：收入",
                description="由旧版术语配置自动生成；原术语记录保留不删除。",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                active=True,
                specific_ds=True,
                datasource_ids=[501],
                prompt="<!-- data-skill-source:terminology:1 -->\n# 术语 Skill：收入\nUse paid_amount.",
            ),
        ))
        sql_split_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="SQL Skill：收入趋势",
                description="由旧版 SQL 示例自动生成；原 SQL 示例记录保留不删除。",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                active=True,
                specific_ds=True,
                datasource_ids=[501],
                prompt=(
                    "<!-- data-skill-source:data-training:1 -->\n"
                    "# SQL Skill：收入趋势\n"
                    "select sum(paid_amount) from fact_payment;"
                ),
            ),
        ))
        sql_prompt_split_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="SQL 提示词 Skill：报表agent",
                description="由旧版 SQL 提示词自动生成；原提示词记录保留不删除。",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                active=True,
                prompt=(
                    "<!-- data-skill-source:custom-prompt-generate-sql:10 -->\n"
                    "# SQL 提示词 Skill：报表agent\n"
                    "Prefer report SQL style."
                ),
            ),
        ))
        themed_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Tenant A 空间数据 Skill：收入付费与 LTV",
                description="由旧版术语和 SQL 示例按主题生成。",
                target_scope=CustomPromptTargetScopeEnum.ALL,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                active=True,
                specific_ds=True,
                datasource_ids=[501],
                prompt=(
                    "<!-- data-skill-source:semantic-theme:tenant:10:501:revenue-ltv -->\n"
                    "# Tenant A 空间数据 Skill：收入付费与 LTV\n"
                    "Use paid_amount."
                ),
            ),
        ))

        skill_text, logs, _model = find_data_skills(
            session,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            skill_id=None,
            current_user_id=3,
            tenant_id=10,
        )

        assert "Tenant A 空间数据 Skill：收入付费与 LTV" in skill_text
        assert "paid_amount" in skill_text
        assert "数据 Skill：Tenant A Project" not in skill_text
        assert "SQL Skill：收入趋势" not in skill_text
        assert "术语 Skill：收入" not in skill_text
        assert "SQL 提示词 Skill：报表agent" not in skill_text
        assert len(logs) == 1
        assert combined_id and terminology_split_id and sql_split_id and sql_prompt_split_id and themed_id


def test_explicit_visibility_filter_returns_one_skill_layer_only():
    engine = _engine()
    with Session(engine) as session:
        platform_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_platform_admin(),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="SaaS Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC,
                prompt="# SaaS Skill",
            ),
        ))
        workspace_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Workspace Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt="# Workspace Skill",
            ),
        ))
        personal_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_member(3, 10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="My Skill",
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.USER_PRIVATE,
                prompt="# My Skill",
            ),
        ))

        _page, _size, _total, _pages, platform_rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.DATA_SKILL,
            current_user_id=3,
            tenant_id=10,
            visibility_scope=CustomPromptVisibilityScopeEnum.PLATFORM_PUBLIC,
        )
        _page, _size, _total, _pages, workspace_rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.DATA_SKILL,
            current_user_id=3,
            tenant_id=10,
            visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
        )
        _page, _size, _total, _pages, personal_rows = custom_prompt_api.page_custom_prompts(
            session,
            CustomPromptTypeEnum.DATA_SKILL,
            current_user_id=3,
            tenant_id=10,
            visibility_scope=CustomPromptVisibilityScopeEnum.USER_PRIVATE,
        )

        assert {row.id for row in platform_rows} == {platform_id}
        assert {row.id for row in workspace_rows} == {workspace_id}
        assert {row.id for row in personal_rows} == {personal_id}


def test_globally_disabled_data_skill_is_hidden_from_runtime():
    engine = _engine()
    with Session(engine) as session:
        skill_id = asyncio.run(_unwrap(custom_prompt_api.create_or_update)(
            session=session,
            current_user=_tenant_admin(10),
            info=_prompt_info(
                type=CustomPromptTypeEnum.DATA_SKILL,
                name="Disabled Revenue Skill",
                active=False,
                target_scope=CustomPromptTargetScopeEnum.SMART_QA,
                visibility_scope=CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC,
                prompt="# Revenue Skill\nUse paid_amount.",
            ),
        ))

        skill_text, logs, _model = find_data_skills(
            session,
            datasource=501,
            target_scope=CustomPromptTargetScopeEnum.SMART_QA,
            skill_id=skill_id,
            current_user_id=3,
            tenant_id=10,
        )

        assert skill_text == ""
        assert logs == []


def test_sql_prompt_ignores_legacy_terms_and_sql_examples_when_data_skill_is_present():
    question = ChatQuestion(
        chat_id=1,
        question="收入是多少？",
        engine="PostgreSQL",
        db_schema="# Table: fact_payment\n[(paid_amount: numeric, 支付金额)]",
        sample_data="[]",
        terminologies="<terminologies>LEGACY TERM SHOULD NOT APPEAR</terminologies>",
        data_training="<sql-examples>LEGACY SQL SHOULD NOT APPEAR</sql-examples>",
        data_skill="<Data-Skills># Revenue Skill\nUse paid_amount.</Data-Skills>",
    )

    templates = question.sql_sys_question("postgresql")
    prompt_text = "\n".join(templates.values())

    assert "LEGACY TERM SHOULD NOT APPEAR" not in prompt_text
    assert "LEGACY SQL SHOULD NOT APPEAR" not in prompt_text
    assert "Revenue Skill" in prompt_text
    assert "<Data-Skills>" in prompt_text


def test_chart_prompt_uses_data_skill_and_ignores_legacy_terms_and_sql_examples():
    question = ChatQuestion(
        chat_id=1,
        question="收入是多少？",
        engine="PostgreSQL",
        db_schema="# Table: fact_payment\n[(paid_amount: numeric, 支付金额)]",
        sql="select sum(paid_amount) as revenue from fact_payment",
        terminologies="<terminologies>LEGACY TERM SHOULD NOT APPEAR</terminologies>",
        data_training="<sql-examples>LEGACY SQL SHOULD NOT APPEAR</sql-examples>",
        data_skill=(
            "<Data-Skills># Revenue Skill\n"
            "Use paid_amount as revenue.\n"
            "Prefer metric cards for single revenue totals.</Data-Skills>"
        ),
    )

    prompt_text = "\n".join(question.chart_sys_question().values())
    prompt_text += "\n" + question.chart_user_question(
        chart_type="metric",
        schema="# Table: fact_payment\n[(paid_amount: numeric, 支付金额)]",
    )

    assert "LEGACY TERM SHOULD NOT APPEAR" not in prompt_text
    assert "LEGACY SQL SHOULD NOT APPEAR" not in prompt_text
    assert "Revenue Skill" in prompt_text
    assert "Prefer metric cards" in prompt_text
    assert "<Data-Skills>" in prompt_text
