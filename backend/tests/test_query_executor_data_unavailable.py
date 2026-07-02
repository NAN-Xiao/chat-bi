"""
脚本说明：验证查询执行器对缺表/缺字段错误的用户友好归类。
"""
from __future__ import annotations

from apps.datasource.crud.query_executor import (
    looks_like_data_unavailable_error,
    user_data_unavailable_message,
)
from common.error import ParseSQLResultError
from common.user_facing_errors import (
    DATA_UNAVAILABLE_ERROR_TYPE,
    PERMISSION_DENIED_ERROR_TYPE,
    classify_error,
)


class _PgError(Exception):
    def __init__(self, message: str, sqlstate: str):
        super().__init__(message)
        self.sqlstate = sqlstate


class _MysqlError(Exception):
    pass


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


def test_sqlstate_is_used_before_text_fallback() -> None:
    """
    是什么：结构化 SQLSTATE 命中时，不依赖驱动错误文本措辞。
    """
    classification = classify_error(_PgError("localized driver text", "42P01"))

    assert classification.error_type == DATA_UNAVAILABLE_ERROR_TYPE
    assert classification.source == "sqlstate"
    assert classification.code == "42P01"


def test_errno_is_used_for_mysql_permission_and_missing_column() -> None:
    """
    是什么：MySQL errno 应能区分缺字段和权限错误。
    """
    assert classify_error(_MysqlError(1054, "localized")).error_type == DATA_UNAVAILABLE_ERROR_TYPE
    assert classify_error(_MysqlError(1142, "localized")).error_type == PERMISSION_DENIED_ERROR_TYPE


def test_wrapped_parse_sql_result_error_preserves_structured_cause() -> None:
    """
    是什么：DBAPI 分支包装成 ParseSQLResultError 后，仍能沿 __cause__ 读取 errno。
    """
    try:
        try:
            raise _MysqlError(1146, "localized")
        except Exception as exc:
            raise ParseSQLResultError(str(exc)) from exc
    except ParseSQLResultError as wrapped:
        classification = classify_error(wrapped)

    assert classification.error_type == DATA_UNAVAILABLE_ERROR_TYPE
    assert classification.source == "errno"
    assert classification.code == 1146
