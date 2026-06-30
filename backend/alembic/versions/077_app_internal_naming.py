"""
脚本说明：这个脚本用于数据库迁移，记录表结构怎么升级或回滚。
"""
from alembic import op
import sqlalchemy as sa


# Alembic 使用的迁移版本标识。
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    """
    是什么：_has_table 是一个可以复用的小步骤，负责数据库迁移相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库迁移里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    """
    是什么：upgrade 是这个迁移脚本的数据库升级步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前升级。
    """
    if not _has_table('chat_log'):
        return

    op.execute(
        """
        UPDATE chat_log
        SET messages = migrated.messages
        FROM (
            SELECT
                chat_log.id,
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(item.elem) = 'object'
                             AND item.elem ? 'shuzhi_system'
                             AND NOT item.elem ? 'app_system'
                        THEN (item.elem - 'shuzhi_system') || jsonb_build_object('app_system', item.elem -> 'shuzhi_system')
                        WHEN jsonb_typeof(item.elem) = 'object'
                             AND item.elem ? 'shuzhi_system'
                        THEN item.elem - 'shuzhi_system'
                        ELSE item.elem
                    END
                    ORDER BY item.ordinality
                ) AS messages
            FROM chat_log
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(chat_log.messages) = 'array' THEN chat_log.messages
                    ELSE '[]'::jsonb
                END
            ) WITH ORDINALITY AS item(elem, ordinality)
            WHERE jsonb_typeof(chat_log.messages) = 'array'
            GROUP BY chat_log.id
        ) AS migrated
        WHERE chat_log.id = migrated.id
        """
    )


def downgrade():
    """
    是什么：downgrade 是这个迁移脚本的数据库回滚步骤。
    谁调用：执行 Alembic 迁移命令时，Alembic 会自动调用它。
    做了什么：按脚本里写好的规则把数据库结构向前回滚。
    """
    if not _has_table('chat_log'):
        return

    op.execute(
        """
        UPDATE chat_log
        SET messages = migrated.messages
        FROM (
            SELECT
                chat_log.id,
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(item.elem) = 'object'
                             AND item.elem ? 'app_system'
                             AND NOT item.elem ? 'shuzhi_system'
                        THEN (item.elem - 'app_system') || jsonb_build_object('shuzhi_system', item.elem -> 'app_system')
                        WHEN jsonb_typeof(item.elem) = 'object'
                             AND item.elem ? 'app_system'
                        THEN item.elem - 'app_system'
                        ELSE item.elem
                    END
                    ORDER BY item.ordinality
                ) AS messages
            FROM chat_log
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(chat_log.messages) = 'array' THEN chat_log.messages
                    ELSE '[]'::jsonb
                END
            ) WITH ORDINALITY AS item(elem, ordinality)
            WHERE jsonb_typeof(chat_log.messages) = 'array'
            GROUP BY chat_log.id
        ) AS migrated
        WHERE chat_log.id = migrated.id
        """
    )
