"""
脚本说明：验证查询执行器对缺表/缺字段错误的用户友好归类。
"""
from __future__ import annotations

from apps.datasource.crud.query_executor import (
    looks_like_data_unavailable_error,
    user_data_unavailable_message,
)


def test_undefined_table_is_data_unavailable() -> None:
    """
    是什么：PostgreSQL 缺表错误应归类为数据不可用。
    """
    message = 'psycopg.errors.UndefinedTable: relation "public"."fact_events" does not exist'

    assert looks_like_data_unavailable_error(message) is True
    assert "public.fact_events" in user_data_unavailable_message(message)


def test_generic_column_word_is_not_data_unavailable() -> None:
    """
    是什么：普通错误里出现 column 单词时，不应误判为缺字段。
    """
    message = "database timeout while sorting by column count"

    assert looks_like_data_unavailable_error(message) is False
