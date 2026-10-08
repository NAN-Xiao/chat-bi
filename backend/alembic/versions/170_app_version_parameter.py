"""Seed the configurable platform display version."""

import sqlalchemy as sa
from alembic import op

from common.utils.snowflake import snowflake


revision = '170appversionparameter'
down_revision = '169platformfunnelexamples'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO sys_arg (id, pkey, pval, ptype, sort_no)
            SELECT :id, 'platform.app_version', 'v1.3.0', 'str', 1
            WHERE NOT EXISTS (SELECT 1 FROM sys_arg WHERE pkey = 'platform.app_version')
            """
        ),
        {'id': snowflake.generate_id()},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM sys_arg WHERE pkey = 'platform.app_version' AND pval = 'v1.3.0'")
    )
