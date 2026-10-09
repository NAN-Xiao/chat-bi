"""将平台默认显示版本升级为 v2.1.0，保留自定义版本。"""

import sqlalchemy as sa
from alembic import op


revision = '172appversion210'
down_revision = '171accountcolortheme'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE sys_arg SET pval = 'v2.1.0' "
            "WHERE pkey = 'platform.app_version' AND pval = 'v1.3.0'"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE sys_arg SET pval = 'v1.3.0' "
            "WHERE pkey = 'platform.app_version' AND pval = 'v2.1.0'"
        )
    )
