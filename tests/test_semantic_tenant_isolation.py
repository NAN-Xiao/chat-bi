from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    find_custom_prompts,
)


def _engine_with_custom_prompt_table():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE custom_prompt (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                type VARCHAR(20),
                create_time DATETIME,
                name VARCHAR(255),
                description TEXT,
                target_scope VARCHAR(32),
                active BOOLEAN,
                visible BOOLEAN DEFAULT 1,
                ai_model_id INTEGER,
                create_by INTEGER,
                visibility_scope VARCHAR(32),
                prompt TEXT,
                embedding TEXT,
                embedding_signature VARCHAR(128),
                specific_ds BOOLEAN,
                datasource_ids TEXT
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO custom_prompt
                (id, tenant_id, type, name, description, target_scope, active,
                 create_by, visibility_scope, prompt, specific_ds, datasource_ids)
            VALUES
                (1, 1, 'GENERATE_SQL', 'Tenant 1 Prompt', '', 'SMART_QA', 1,
                 10, 'ADMIN_PUBLIC', 'tenant-one-only', 0, '[]'),
                (2, 2, 'GENERATE_SQL', 'Tenant 2 Prompt', '', 'SMART_QA', 1,
                 20, 'ADMIN_PUBLIC', 'tenant-two-only', 0, '[]')
            """
        ))
    return engine


def test_runtime_custom_prompt_is_scoped_by_current_tenant():
    engine = _engine_with_custom_prompt_table()

    with Session(engine) as session:
        tenant_one_prompt, tenant_one_logs, _model = find_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            None,
            CustomPromptTargetScopeEnum.SMART_QA,
            1,
            current_user_id=10,
            can_manage_all=True,
            tenant_id=1,
        )
        cross_tenant_prompt, cross_tenant_logs, _model = find_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            None,
            CustomPromptTargetScopeEnum.SMART_QA,
            2,
            current_user_id=10,
            can_manage_all=True,
            tenant_id=1,
        )
        tenant_two_prompt, _tenant_two_logs, _model = find_custom_prompts(
            session,
            CustomPromptTypeEnum.GENERATE_SQL,
            None,
            CustomPromptTargetScopeEnum.SMART_QA,
            2,
            current_user_id=20,
            can_manage_all=True,
            tenant_id=2,
        )

    assert "tenant-one-only" in tenant_one_prompt
    assert tenant_one_logs == ["名称：Tenant 1 Prompt\n补充提示词：tenant-one-only"]
    assert cross_tenant_prompt == ""
    assert cross_tenant_logs == []
    assert "tenant-two-only" in tenant_two_prompt
