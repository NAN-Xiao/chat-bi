"""为普通看板增加 SQL 执行数据源。"""

import sqlalchemy as sa

from alembic import op


revision = "149dashboardexecutiondatasource"
down_revision = "148roisingleton"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "core_dashboard",
        sa.Column("execution_datasource_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("core_dashboard", "execution_datasource_id")
