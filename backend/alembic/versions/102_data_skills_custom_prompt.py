"""102_data_skills_custom_prompt

Revision ID: ac22d4e6f810
Revises: fb31c2d4e5a6
Create Date: 2026-06-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "ac22d4e6f810"
down_revision = "fb31c2d4e5a6"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _drop_legacy_enum_check(table_name: str, column_name: str, new_value: str) -> None:
    if not _has_table(table_name):
        return
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_check_constraints(table_name):
        sqltext = str(constraint.get("sqltext") or "")
        name = constraint.get("name")
        if not name:
            continue
        if column_name in sqltext and new_value not in sqltext:
            op.drop_constraint(name, table_name, type_="check")


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    return _has_table(table_name) and all(_has_column(table_name, column_name) for column_name in column_names)


def _generate_skills_from_terminology() -> None:
    if not _has_columns(
        "terminology",
        ("id", "tenant_id", "scope", "pid", "word", "description", "specific_ds", "datasource_ids", "enabled"),
    ):
        return
    if not _has_table("custom_prompt"):
        return

    op.execute(
        sa.text(
            """
            WITH source_rows AS (
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
            rendered AS (
                SELECT
                    source_id,
                    tenant_id,
                    visibility_scope,
                    specific_ds,
                    datasource_ids,
                    '<!-- data-skill-source:terminology:' || source_id || ' -->' AS marker,
                    left('术语 Skill：' || word, 255) AS skill_name,
                    '由旧版术语配置自动生成；原术语记录保留不删除。' AS skill_description,
                    '<!-- data-skill-source:terminology:' || source_id || ' -->' || E'\n'
                    || '# 术语 Skill：' || word || E'\n\n'
                    || '本 Skill 由旧版术语配置自动生成；原术语记录仍保留在 terminology 表中。' || E'\n\n'
                    || '## 术语' || E'\n'
                    || '- 名称：' || word || E'\n'
                    || CASE WHEN synonyms <> '' THEN '- 同义词：' || synonyms || E'\n' ELSE '' END
                    || CASE
                        WHEN term_description IS NOT NULL THEN '- 口径说明：' || term_description || E'\n'
                        ELSE ''
                       END
                    AS skill_prompt
                FROM source_rows
            ),
            updated AS (
                UPDATE custom_prompt AS cp
                SET tenant_id = r.tenant_id,
                    name = r.skill_name,
                    description = r.skill_description,
                    target_scope = 'ALL',
                    active = TRUE,
                    ai_model_id = NULL,
                    visibility_scope = r.visibility_scope,
                    prompt = r.skill_prompt,
                    specific_ds = r.specific_ds,
                    datasource_ids = r.datasource_ids
                FROM rendered AS r
                WHERE cp.type = 'DATA_SKILL'
                  AND position(r.marker in COALESCE(cp.prompt, '')) > 0
                RETURNING cp.id, r.source_id
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


def _generate_skills_from_data_training() -> None:
    if not _has_columns(
        "data_training",
        ("id", "tenant_id", "scope", "datasource", "question", "description", "enabled"),
    ):
        return
    if not _has_table("custom_prompt"):
        return

    op.execute(
        sa.text(
            """
            WITH source_rows AS (
                SELECT
                    dt.id AS source_id,
                    dt.tenant_id,
                    CASE
                        WHEN COALESCE(dt.scope, 'TENANT') = 'PLATFORM' THEN 'PLATFORM_PUBLIC'
                        ELSE 'ADMIN_PUBLIC'
                    END AS visibility_scope,
                    dt.datasource,
                    btrim(dt.question) AS question,
                    NULLIF(btrim(COALESCE(dt.description, '')), '') AS sql_text
                FROM data_training AS dt
                WHERE COALESCE(dt.enabled, TRUE) = TRUE
                  AND NULLIF(btrim(dt.question), '') IS NOT NULL
                  AND NULLIF(btrim(COALESCE(dt.description, '')), '') IS NOT NULL
            ),
            rendered AS (
                SELECT
                    source_id,
                    tenant_id,
                    visibility_scope,
                    datasource IS NOT NULL AS specific_ds,
                    CASE
                        WHEN datasource IS NULL THEN '[]'::jsonb
                        ELSE to_jsonb(ARRAY[datasource::bigint])
                    END AS datasource_ids,
                    '<!-- data-skill-source:data-training:' || source_id || ' -->' AS marker,
                    left('SQL Skill：' || question, 255) AS skill_name,
                    '由旧版 SQL 示例自动生成；原 SQL 示例记录保留不删除。' AS skill_description,
                    '<!-- data-skill-source:data-training:' || source_id || ' -->' || E'\n'
                    || '# SQL Skill：' || question || E'\n\n'
                    || '本 Skill 由旧版 SQL 示例库自动生成；原 SQL 示例记录仍保留在 data_training 表中。' || E'\n\n'
                    || '## 适用问题' || E'\n'
                    || question || E'\n\n'
                    || '## 参考 SQL' || E'\n'
                    || '```sql' || E'\n'
                    || sql_text || E'\n'
                    || '```' || E'\n'
                    AS skill_prompt
                FROM source_rows
            ),
            updated AS (
                UPDATE custom_prompt AS cp
                SET tenant_id = r.tenant_id,
                    name = r.skill_name,
                    description = r.skill_description,
                    target_scope = 'ALL',
                    active = TRUE,
                    ai_model_id = NULL,
                    visibility_scope = r.visibility_scope,
                    prompt = r.skill_prompt,
                    specific_ds = r.specific_ds,
                    datasource_ids = r.datasource_ids
                FROM rendered AS r
                WHERE cp.type = 'DATA_SKILL'
                  AND position(r.marker in COALESCE(cp.prompt, '')) > 0
                RETURNING cp.id, r.source_id
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


def _generate_skills_from_sql_prompts() -> None:
    if not _has_columns(
        "custom_prompt",
        (
            "id",
            "tenant_id",
            "type",
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

    op.execute(
        sa.text(
            """
            WITH source_rows AS (
                SELECT
                    cp.id AS source_id,
                    cp.tenant_id,
                    COALESCE(cp.visibility_scope, 'ADMIN_PUBLIC') AS visibility_scope,
                    cp.create_by,
                    COALESCE(cp.target_scope, 'SMART_QA') AS target_scope,
                    cp.ai_model_id,
                    CASE
                        WHEN COALESCE(cp.specific_ds, FALSE)
                         AND jsonb_array_length(COALESCE(cp.datasource_ids, '[]'::jsonb)) > 0
                        THEN TRUE
                        ELSE FALSE
                    END AS specific_ds,
                    COALESCE(cp.datasource_ids, '[]'::jsonb) AS datasource_ids,
                    COALESCE(NULLIF(btrim(cp.name), ''), 'SQL 提示词') AS prompt_name,
                    NULLIF(btrim(COALESCE(cp.description, '')), '') AS prompt_description,
                    btrim(cp.prompt) AS prompt_text
                FROM custom_prompt AS cp
                WHERE cp.type = 'GENERATE_SQL'
                  AND COALESCE(cp.active, FALSE) = TRUE
                  AND NULLIF(btrim(COALESCE(cp.prompt, '')), '') IS NOT NULL
            ),
            rendered AS (
                SELECT
                    source_id,
                    tenant_id,
                    visibility_scope,
                    create_by,
                    target_scope,
                    ai_model_id,
                    specific_ds,
                    datasource_ids,
                    '<!-- data-skill-source:custom-prompt-generate-sql:' || source_id || ' -->' AS marker,
                    left('SQL 提示词 Skill：' || prompt_name, 255) AS skill_name,
                    '由旧版 SQL 提示词自动生成；原提示词记录保留不删除。' AS skill_description,
                    '<!-- data-skill-source:custom-prompt-generate-sql:' || source_id || ' -->' || E'\n'
                    || '# SQL 提示词 Skill：' || prompt_name || E'\n\n'
                    || '本 Skill 由旧版 SQL 提示词自动生成；原提示词记录仍保留在 custom_prompt 表中。' || E'\n\n'
                    || CASE
                        WHEN prompt_description IS NOT NULL THEN '## 描述' || E'\n' || prompt_description || E'\n\n'
                        ELSE ''
                       END
                    || '## 提示词内容' || E'\n'
                    || prompt_text || E'\n'
                    AS skill_prompt
                FROM source_rows
            ),
            updated AS (
                UPDATE custom_prompt AS cp
                SET tenant_id = r.tenant_id,
                    name = r.skill_name,
                    description = r.skill_description,
                    target_scope = r.target_scope,
                    active = TRUE,
                    ai_model_id = r.ai_model_id,
                    create_by = r.create_by,
                    visibility_scope = r.visibility_scope,
                    prompt = r.skill_prompt,
                    specific_ds = r.specific_ds,
                    datasource_ids = r.datasource_ids
                FROM rendered AS r
                WHERE cp.type = 'DATA_SKILL'
                  AND position(r.marker in COALESCE(cp.prompt, '')) > 0
                RETURNING cp.id, r.source_id
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
                r.target_scope,
                TRUE,
                r.ai_model_id,
                r.create_by,
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


def upgrade():
    if _has_table("chat_record") and not _has_column("chat_record", "data_skill_id"):
        op.add_column("chat_record", sa.Column("data_skill_id", sa.BigInteger(), nullable=True))

    _drop_legacy_enum_check("custom_prompt", "type", "DATA_SKILL")
    _drop_legacy_enum_check("chat_log", "operate", "14")
    _generate_skills_from_terminology()
    _generate_skills_from_data_training()
    _generate_skills_from_sql_prompts()


def downgrade():
    if _has_table("chat_record") and _has_column("chat_record", "data_skill_id"):
        op.drop_column("chat_record", "data_skill_id")
