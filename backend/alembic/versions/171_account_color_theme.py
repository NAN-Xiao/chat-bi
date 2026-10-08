"""保存账户级深浅配色偏好，现有账户默认浅色。"""
from alembic import op
import sqlalchemy as sa

revision = '171accountcolortheme'
down_revision = '170appversionparameter'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sys_user', sa.Column('color_theme', sa.String(5), nullable=False, server_default='light'))
    op.create_check_constraint('ck_sys_user_color_theme', 'sys_user', "color_theme IN ('light', 'dark')")


def downgrade() -> None:
    op.drop_constraint('ck_sys_user_color_theme', 'sys_user', type_='check')
    op.drop_column('sys_user', 'color_theme')
