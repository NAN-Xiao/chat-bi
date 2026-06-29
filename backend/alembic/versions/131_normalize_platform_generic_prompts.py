"""131_normalize_platform_generic_prompts

Revision ID: d4f7a9c2e1b3
Revises: c7e9a2d4f6b8
Create Date: 2026-06-27 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d4f7a9c2e1b3"
down_revision = "c7e9a2d4f6b8"
branch_labels = None
depends_on = None


def _bind():
    return op.get_bind()


def _inspector():
    return sa.inspect(_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_columns(table_name: str, column_names: tuple[str, ...]) -> bool:
    if not _has_table(table_name):
        return False
    existing = {column["name"] for column in _inspector().get_columns(table_name)}
    return set(column_names).issubset(existing)


def upgrade() -> None:
    if not _has_columns(
        "custom_prompt",
        ("tenant_id", "visibility_scope", "specific_ds", "datasource_ids"),
    ):
        return

    empty_datasource_ids = "'[]'::jsonb" if _bind().dialect.name == "postgresql" else "'[]'"
    op.execute(
        f"""
        UPDATE custom_prompt
        SET tenant_id = 1,
            specific_ds = false,
            datasource_ids = {empty_datasource_ids}
        WHERE visibility_scope = 'PLATFORM_PUBLIC'
        """
    )


def downgrade() -> None:
    pass
