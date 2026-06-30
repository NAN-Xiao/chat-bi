"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'b7c1f2d3e4a5'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    op.create_table(
        'core_datasource_user',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('ds_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('oid', sa.BigInteger(), nullable=False),
        sa.Column('create_by', sa.BigInteger(), nullable=True),
        sa.Column('create_time', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ds_id', 'user_id', name='uq_core_datasource_user_ds_user'),
    )
    op.create_index('idx_core_datasource_user_user_id', 'core_datasource_user', ['user_id'], unique=False)
    op.create_index('idx_core_datasource_user_ds_id', 'core_datasource_user', ['ds_id'], unique=False)

    # 保留此前由行列权限规则隐含授予的访问关系。
    op.execute(
        """
        INSERT INTO core_datasource_user (ds_id, user_id, oid, create_by, create_time)
        SELECT DISTINCT p.ds_id, users.user_id::bigint, COALESCE(d.oid, r.oid, 1), 1, NOW()
        FROM ds_rules r
        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(NULLIF(r.user_list, '')::jsonb, '[]'::jsonb)) users(user_id)
        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(NULLIF(r.permission_list, '')::jsonb, '[]'::jsonb)) perms(permission_id)
        JOIN ds_permission p ON p.id = perms.permission_id::bigint
        JOIN core_datasource d ON d.id = p.ds_id
        WHERE COALESCE(r.enable, TRUE) = TRUE
          AND COALESCE(p.enable, TRUE) = TRUE
          AND p.ds_id IS NOT NULL
          AND users.user_id ~ '^[0-9]+$'
        ON CONFLICT (ds_id, user_id) DO NOTHING
        """
    )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    op.drop_index('idx_core_datasource_user_ds_id', table_name='core_datasource_user')
    op.drop_index('idx_core_datasource_user_user_id', table_name='core_datasource_user')
    op.drop_table('core_datasource_user')
