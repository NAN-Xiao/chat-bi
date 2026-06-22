"""115_disable_legacy_split_data_skills

Revision ID: a8d7e6c5b4a3
Revises: f6b8d0e2a4c5
Create Date: 2026-06-22 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a8d7e6c5b4a3"
down_revision = "f6b8d0e2a4c5"
branch_labels = None
depends_on = None


LEGACY_MARKERS = (
    "<!-- data-skill-source:terminology:",
    "<!-- data-skill-source:data-training:",
    "<!-- data-skill-source:custom-prompt-generate-sql:",
    "<!-- data-skill-source:legacy-semantic:",
    "<!-- data-skill-source:semantic-theme:saas:",
    "<!-- legacy-data-training:",
    "<!-- legacy-terminology:",
    "<!-- legacy-sql-prompt:",
)


def upgrade() -> None:
    conn = op.get_bind()
    conditions = " OR ".join(f"prompt LIKE :marker_{index}" for index, _marker in enumerate(LEGACY_MARKERS))
    params = {f"marker_{index}": f"%{marker}%" for index, marker in enumerate(LEGACY_MARKERS)}
    conn.execute(
        sa.text(
            f"""
            UPDATE custom_prompt
            SET active = false
            WHERE type = 'DATA_SKILL'
              AND COALESCE(active, false) = true
              AND ({conditions})
            """
        ),
        params,
    )


def downgrade() -> None:
    return None
