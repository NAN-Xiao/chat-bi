"""077_app_internal_naming

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
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
