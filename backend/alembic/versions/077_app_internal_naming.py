"""迁移脚本：077_app_internal_naming

迁移版本 ID： a7b8c9d0e1f2
上一版本： f6a7b8c9d0e1
创建时间： 2026-06-16 00:00:00.000000
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
    是什么：_has_table 是 backend/alembic/versions/077_app_internal_naming.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _has_table 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
    """
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    """
    是什么：upgrade 是 backend/alembic/versions/077_app_internal_naming.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 upgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
    是什么：downgrade 是 backend/alembic/versions/077_app_internal_naming.py 中的同步数据库迁移函数。
    谁调用：由 Alembic 迁移框架在执行数据库升级或回滚时调用。
    做了什么：围绕 downgrade 的语义处理数据库迁移相关逻辑，并把结果返回或写入状态。
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
