"""迁移脚本：010_upgrade_user_language

迁移版本 ID： 8dc3b1bdbfef
上一版本： 804b08ac329d
创建时间： 2025-06-10 11:21:35.257604
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# Alembic 使用的迁移版本标识。
revision = '8dc3b1bdbfef'
down_revision = '804b08ac329d'
branch_labels = None
depends_on = None


def upgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：upgrade 是 backend/alembic/versions/010_upgrade_user_language.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.add_column('sys_user', sa.Column('language', sa.VARCHAR(length=255), server_default=sa.text("'zh-CN'"), nullable=False))

    # ### Alembic 命令结束 ###


def downgrade():
    # ### Alembic 自动生成的命令，请按需调整！###

    """
    是什么：downgrade 是 backend/alembic/versions/010_upgrade_user_language.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    op.drop_column('sys_user', 'language')

    # ### Alembic 命令结束 ###
