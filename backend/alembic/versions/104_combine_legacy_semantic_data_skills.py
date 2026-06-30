"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


revision = "e42f8b6c1d9a"
down_revision = "d31c7b9a4e02"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """
    是什么：_has_column 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    """
    是什么：_has_columns 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _has_table(table_name) and all(_has_column(table_name, column_name) for column_name in column_names)


def _generate_combined_legacy_semantic_skills() -> None:
    """
    是什么：_generate_combined_legacy_semantic_skills 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成数据库迁移的结果，比如答案、SQL、图表或建议。
    """
    if not _has_columns(
        "custom_prompt",
        (
            "tenant_id",
            "type",
            "create_time",
            "name",
            "description",
            "target_scope",
            "active",
            "ai_model_id",
            "create_by",
            "visibility_scope",
            "prompt",
            "specific_ds",
            "datasource_ids",
        ),
    ):
        return
    if not _has_columns(
        "terminology",
        ("id", "tenant_id", "scope", "pid", "word", "description", "specific_ds", "datasource_ids", "enabled"),
    ):
        return
    if not _has_columns(
        "data_training",
        ("id", "tenant_id", "scope", "datasource", "question", "description", "enabled"),
    ):
        return
    if not _has_columns("core_datasource", ("id", "name")):
        return

    op.execute(
        sa.text(
            """
            WITH term_base AS (
                SELECT
                    t.id AS source_id,
                    t.tenant_id,
                    CASE
                        WHEN COALESCE(t.scope, 'TENANT') = 'PLATFORM' THEN 'PLATFORM_PUBLIC'
                        ELSE 'ADMIN_PUBLIC'
                    END AS visibility_scope,
                    CASE
                        WHEN COALESCE(t.specific_ds, FALSE)
                         AND jsonb_array_length(COALESCE(t.datasource_ids, '[]'::jsonb)) > 0
                        THEN TRUE
                        ELSE FALSE
                    END AS specific_ds,
                    COALESCE(t.datasource_ids, '[]'::jsonb) AS datasource_ids,
                    btrim(t.word) AS word,
                    NULLIF(btrim(COALESCE(t.description, '')), '') AS term_description,
                    COALESCE(
                        string_agg(btrim(child.word), ', ' ORDER BY child.word)
                            FILTER (WHERE child.id IS NOT NULL AND NULLIF(btrim(child.word), '') IS NOT NULL),
                        ''
                    ) AS synonyms
                FROM terminology AS t
                LEFT JOIN terminology AS child
                    ON child.pid = t.id
                   AND COALESCE(child.enabled, TRUE) = TRUE
                WHERE t.pid IS NULL
                  AND COALESCE(t.enabled, TRUE) = TRUE
                  AND NULLIF(btrim(t.word), '') IS NOT NULL
                GROUP BY t.id
            ),
            term_rows AS (
                SELECT
                    term_base.source_id,
                    term_base.tenant_id,
                    term_base.visibility_scope,
                    CASE
                        WHEN term_base.specific_ds THEN NULLIF(ds.value, '')::bigint
                        ELSE NULL
                    END AS datasource_id,
                    '<!-- legacy-terminology:' || term_base.source_id || ' -->' || E'\n'
                    || '- **' || term_base.word || '**'
                    || CASE WHEN term_base.synonyms <> '' THEN '（同义词：' || term_base.synonyms || '）' ELSE '' END
                    || CASE
                        WHEN term_base.term_description IS NOT NULL THEN '：' || term_base.term_description
                        ELSE ''
                       END AS term_line
                FROM term_base
                LEFT JOIN LATERAL jsonb_array_elements_text(term_base.datasource_ids) AS ds(value)
                    ON term_base.specific_ds
            ),
            term_groups AS (
                SELECT
                    tenant_id,
                    visibility_scope,
                    datasource_id,
                    string_agg(term_line, E'\n' ORDER BY source_id) AS terms
                FROM term_rows
                GROUP BY tenant_id, visibility_scope, datasource_id
            ),
            sql_rows AS (
                SELECT
                    dt.id AS source_id,
                    dt.tenant_id,
                    CASE
                        WHEN COALESCE(dt.scope, 'TENANT') = 'PLATFORM' THEN 'PLATFORM_PUBLIC'
                        ELSE 'ADMIN_PUBLIC'
                    END AS visibility_scope,
                    dt.datasource::bigint AS datasource_id,
                    '<!-- legacy-data-training:' || dt.id || ' -->' || E'\n'
                    || '### 问题：' || btrim(dt.question) || E'\n\n'
                    || '````sql' || E'\n'
                    || btrim(dt.description) || E'\n'
                    || '````' AS sql_example
                FROM data_training AS dt
                WHERE COALESCE(dt.enabled, TRUE) = TRUE
                  AND NULLIF(btrim(dt.question), '') IS NOT NULL
                  AND NULLIF(btrim(COALESCE(dt.description, '')), '') IS NOT NULL
            ),
            sql_groups AS (
                SELECT
                    tenant_id,
                    visibility_scope,
                    datasource_id,
                    string_agg(sql_example, E'\n\n' ORDER BY source_id) AS sql_examples
                FROM sql_rows
                GROUP BY tenant_id, visibility_scope, datasource_id
            ),
            semantic_groups AS (
                SELECT tenant_id, visibility_scope, datasource_id FROM term_groups
                UNION
                SELECT tenant_id, visibility_scope, datasource_id FROM sql_groups
            ),
            rendered AS (
                SELECT
                    g.tenant_id,
                    g.visibility_scope,
                    g.datasource_id,
                    g.datasource_id IS NOT NULL AS specific_ds,
                    CASE
                        WHEN g.datasource_id IS NULL THEN '[]'::jsonb
                        ELSE to_jsonb(ARRAY[g.datasource_id])
                    END AS datasource_ids,
                    '<!-- data-skill-source:legacy-semantic:'
                        || g.visibility_scope || ':' || g.tenant_id || ':'
                        || COALESCE(g.datasource_id::text, 'global') || ' -->' AS marker,
                    CASE
                        WHEN g.datasource_id IS NOT NULL
                            THEN left('数据 Skill：' || COALESCE(ds.name, '数据项目 ' || g.datasource_id::text), 255)
                        WHEN g.visibility_scope = 'PLATFORM_PUBLIC'
                            THEN 'SaaS 数据 Skill：通用业务口径'
                        ELSE '工作空间数据 Skill：通用业务口径'
                    END AS skill_name,
                    CASE
                        WHEN g.datasource_id IS NOT NULL
                            THEN '由旧版术语和 SQL 示例合并生成；适用于数据项目「'
                                 || COALESCE(ds.name, '数据项目 ' || g.datasource_id::text)
                                 || '」。原始记录保留不删除。'
                        WHEN g.visibility_scope = 'PLATFORM_PUBLIC'
                            THEN '由旧版 SaaS 术语和 SQL 示例合并生成；原始记录保留不删除。'
                        ELSE '由旧版工作空间术语和 SQL 示例合并生成；原始记录保留不删除。'
                    END AS skill_description,
                    '<!-- data-skill-source:legacy-semantic:'
                        || g.visibility_scope || ':' || g.tenant_id || ':'
                        || COALESCE(g.datasource_id::text, 'global') || ' -->' || E'\n'
                    || '# ' ||
                    CASE
                        WHEN g.datasource_id IS NOT NULL
                            THEN '数据 Skill：' || COALESCE(ds.name, '数据项目 ' || g.datasource_id::text)
                        WHEN g.visibility_scope = 'PLATFORM_PUBLIC'
                            THEN 'SaaS 数据 Skill：通用业务口径'
                        ELSE '工作空间数据 Skill：通用业务口径'
                    END || E'\n\n'
                    || '本 Skill 由旧版术语和 SQL 示例合并生成；原 terminology 与 data_training 记录保留不删除。' || E'\n\n'
                    || '## 使用方式' || E'\n'
                    || '- 先按“术语与口径”理解用户问题里的指标、同义词、字段含义和统计口径。' || E'\n'
                    || '- 生成 SQL 时优先复用“SQL 示例”中的表连接、过滤条件、时间字段、聚合粒度和指标别名。' || E'\n'
                    || '- 生成图表时优先把 SQL 输出中的时间或分类字段作为维度，把数值字段作为度量；如果示例或术语没有覆盖图表字段，请只基于查询结果字段选择，不要臆造口径。' || E'\n'
                    || '- 如果本 Skill 与当前数据库 Schema、数据权限或用户已选数据源冲突，以当前 SaaS 权限和 Schema 为准。' || E'\n\n'
                    || '## 适用数据项目' || E'\n'
                    || CASE
                        WHEN g.datasource_id IS NOT NULL
                            THEN '- ' || COALESCE(ds.name, '数据项目 ' || g.datasource_id::text)
                                 || '（ID：' || g.datasource_id::text || '）' || E'\n\n'
                        ELSE '- 当前层级下所有已授权数据项目' || E'\n\n'
                       END
                    || '## 术语与口径' || E'\n'
                    || COALESCE(tg.terms, '- 暂无旧版术语记录。') || E'\n\n'
                    || '## SQL 示例' || E'\n'
                    || COALESCE(sg.sql_examples, '- 暂无旧版 SQL 示例记录。') || E'\n'
                    AS skill_prompt
                FROM semantic_groups AS g
                LEFT JOIN term_groups AS tg
                    ON tg.tenant_id = g.tenant_id
                   AND tg.visibility_scope = g.visibility_scope
                   AND tg.datasource_id IS NOT DISTINCT FROM g.datasource_id
                LEFT JOIN sql_groups AS sg
                    ON sg.tenant_id = g.tenant_id
                   AND sg.visibility_scope = g.visibility_scope
                   AND sg.datasource_id IS NOT DISTINCT FROM g.datasource_id
                LEFT JOIN core_datasource AS ds ON ds.id = g.datasource_id
            ),
            updated AS (
                UPDATE custom_prompt AS cp
                SET tenant_id = r.tenant_id,
                    name = r.skill_name,
                    description = r.skill_description,
                    target_scope = 'ALL',
                    active = TRUE,
                    ai_model_id = NULL,
                    create_by = NULL,
                    visibility_scope = r.visibility_scope,
                    prompt = r.skill_prompt,
                    specific_ds = r.specific_ds,
                    datasource_ids = r.datasource_ids
                FROM rendered AS r
                WHERE cp.type = 'DATA_SKILL'
                  AND position(r.marker in COALESCE(cp.prompt, '')) > 0
                RETURNING cp.id
            )
            INSERT INTO custom_prompt (
                tenant_id,
                type,
                create_time,
                name,
                description,
                target_scope,
                active,
                ai_model_id,
                create_by,
                visibility_scope,
                prompt,
                specific_ds,
                datasource_ids
            )
            SELECT
                r.tenant_id,
                'DATA_SKILL',
                NOW(),
                r.skill_name,
                r.skill_description,
                'ALL',
                TRUE,
                NULL,
                NULL,
                r.visibility_scope,
                r.skill_prompt,
                r.specific_ds,
                r.datasource_ids
            FROM rendered AS r
            WHERE NOT EXISTS (
                SELECT 1
                FROM custom_prompt AS cp
                WHERE cp.type = 'DATA_SKILL'
                  AND position(r.marker in COALESCE(cp.prompt, '')) > 0
            )
            """
        )
    )


def _disable_generated_duplicate_data_skills() -> None:
    """
    是什么：_disable_generated_duplicate_data_skills 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not _has_columns("custom_prompt", ("type", "name", "description", "prompt")):
        return
    op.execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET active = FALSE
            WHERE type = 'DATA_SKILL'
              AND position('<!-- data-skill-source:legacy-semantic:' in COALESCE(prompt, '')) = 0
              AND (
                position('<!-- data-skill-source:terminology:' in COALESCE(prompt, '')) > 0
                OR position('<!-- data-skill-source:data-training:' in COALESCE(prompt, '')) > 0
                OR position('<!-- data-skill-source:custom-prompt-generate-sql:' in COALESCE(prompt, '')) > 0
              )
            """
        )
    )


def upgrade() -> None:
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    _generate_combined_legacy_semantic_skills()
    _disable_generated_duplicate_data_skills()


def downgrade() -> None:
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    pass
