"""增加平台 Skill 的租户排除配置，并收紧预测 Skill 的目标入口。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "161platformskilltenantexclusion"
down_revision = "160platformrecursivealiascompat"
branch_labels = None
depends_on = None


SAMPLE_TENANT_ID = 7473600346187632640
PLATFORM_SCOPE = "PLATFORM_PUBLIC"
DATA_SKILL_TYPE = "DATA_SKILL"
DATE_SKILL_TARGETS = (
    ("<!-- data-skill-source:platform-generic -->", "平台通用 Data Skill：时间字段、观察窗口与日期边界"),
    ("<!-- platform-foundation-skill:sql-date-grouping:v1 -->", "平台通用 SQL 日期与分组规范"),
    ("<!-- data-skill-source:platform:realtime-event-table-selection -->", None),
    ("<!-- data-skill-source:platform:date-field-usage-contract -->", None),
)
PREDICT_SKILL_NAME = "平台通用 Data Skill：预测、成熟样本与置信表达"


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _update_skill_exclusion(marker: str, name: str | None) -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET excluded_tenant_ids = CASE
                WHEN jsonb_typeof(COALESCE(excluded_tenant_ids, '[]'::jsonb)) = 'array'
                     AND NOT COALESCE(excluded_tenant_ids, '[]'::jsonb)
                         @> jsonb_build_array(CAST(:tenant_id AS bigint))
                    THEN COALESCE(excluded_tenant_ids, '[]'::jsonb)
                         || jsonb_build_array(CAST(:tenant_id AS bigint))
                ELSE COALESCE(excluded_tenant_ids, '[]'::jsonb)
            END
            WHERE tenant_id = 1
              AND type = :skill_type
              AND visibility_scope = :visibility_scope
              AND (CAST(:name AS TEXT) IS NULL OR name = :name)
              AND position(:marker in COALESCE(prompt, '')) > 0
            """
        ),
        {
            "tenant_id": SAMPLE_TENANT_ID,
            "skill_type": DATA_SKILL_TYPE,
            "visibility_scope": PLATFORM_SCOPE,
            "name": name,
            "marker": marker,
        },
    )


def upgrade() -> None:
    if not _has_column("custom_prompt", "excluded_tenant_ids"):
        op.add_column(
            "custom_prompt",
            sa.Column(
                "excluded_tenant_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )

    for marker, name in DATE_SKILL_TARGETS:
        _update_skill_exclusion(marker, name)

    op.get_bind().execute(
        sa.text(
            """
            UPDATE custom_prompt
            SET target_scope = 'ANALYSIS_ASSISTANT'
            WHERE tenant_id = 1
              AND type = :skill_type
              AND visibility_scope = :visibility_scope
              AND name = :skill_name
              AND target_scope <> 'ANALYSIS_ASSISTANT'
            """
        ),
        {
            "skill_type": DATA_SKILL_TYPE,
            "visibility_scope": PLATFORM_SCOPE,
            "skill_name": PREDICT_SKILL_NAME,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column("custom_prompt", "excluded_tenant_ids"):
        for marker, name in DATE_SKILL_TARGETS:
            bind.execute(
                sa.text(
                    """
                    UPDATE custom_prompt
                    SET excluded_tenant_ids = COALESCE(
                        (
                            SELECT jsonb_agg(item)
                            FROM jsonb_array_elements(COALESCE(excluded_tenant_ids, '[]'::jsonb)) AS values(item)
                            WHERE item <> to_jsonb(CAST(:tenant_id AS bigint))
                        ),
                        '[]'::jsonb
                    )
                    WHERE tenant_id = 1
                      AND type = :skill_type
                      AND visibility_scope = :visibility_scope
                      AND (CAST(:name AS TEXT) IS NULL OR name = :name)
                      AND position(:marker in COALESCE(prompt, '')) > 0
                    """
                ),
                {
                    "tenant_id": SAMPLE_TENANT_ID,
                    "skill_type": DATA_SKILL_TYPE,
                    "visibility_scope": PLATFORM_SCOPE,
                    "name": name,
                    "marker": marker,
                },
            )
        bind.execute(
            sa.text(
                """
                UPDATE custom_prompt
                SET target_scope = 'ALL'
                WHERE tenant_id = 1
                  AND type = :skill_type
                  AND visibility_scope = :visibility_scope
                  AND name = :skill_name
                  AND target_scope = 'ANALYSIS_ASSISTANT'
                """
            ),
            {
                "skill_type": DATA_SKILL_TYPE,
                "visibility_scope": PLATFORM_SCOPE,
                "skill_name": PREDICT_SKILL_NAME,
            },
        )
        op.drop_column("custom_prompt", "excluded_tenant_ids")
