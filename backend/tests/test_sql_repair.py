"""
脚本说明：验证 SQL 修复上下文、错误分类、脱敏、指纹与提示契约。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from sqlglot.errors import ParseError

from apps.chat.task import llm
from apps.chat.task.sql_repair import (
    SQL_REPAIR_MAX_ATTEMPTS,
    DataSkillSqlValidationError,
    DataSkillSqlViolation,
    SqlRepairContext,
    SqlRepairReason,
    SqlStructureValidationError,
    build_sql_repair_message,
    classify_execute_sql_error,
    classify_prepare_sql_error,
    sanitize_sql_repair_error,
    sql_repair_fingerprint,
    validate_mysql_date_format_grouping,
)
from common.error import (
    AppDBConnectionError,
    AppDBError,
    DataUnavailableError,
    ParseSQLResultError,
    SingleMessageError,
)


class _PgError(Exception):
    def __init__(self, message: str, sqlstate: str):
        super().__init__(message)
        self.sqlstate = sqlstate


class _MysqlError(Exception):
    def __init__(self, message: str, errno: int):
        super().__init__(message)
        self.errno = errno


def _violation() -> DataSkillSqlViolation:
    return DataSkillSqlViolation(
        message="口径错误",
        rule_index=0,
        missing_required_contains=("required",),
        missing_required_patterns=(r"count\s*\(",),
        matched_forbidden_contains=("forbidden",),
        matched_forbidden_patterns=(r"select\s+\*",),
        matched_forbidden_groups=(("legacy_table", "legacy_field"),),
    )


def test_public_models_preserve_structured_violation() -> None:
    violation = _violation()
    error = DataSkillSqlValidationError(violation)

    assert SQL_REPAIR_MAX_ATTEMPTS == 2
    assert error.violation == violation
    assert str(error) == "口径错误"
    assert DataSkillSqlValidationError("纯文本口径错误").violation is None
    assert str(DataSkillSqlValidationError("纯文本口径错误")) == "纯文本口径错误"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            SingleMessageError("SQL answer is not a valid json object"),
            SqlRepairReason.SQL_RESPONSE_FORMAT,
        ),
        (SingleMessageError("SQL response is empty"), SqlRepairReason.SQL_RESPONSE_FORMAT),
        (SingleMessageError("Empty SQL text"), SqlRepairReason.SQL_RESPONSE_FORMAT),
        (SingleMessageError("Parse SQL Error: invalid token"), SqlRepairReason.SQL_PARSE),
        (ParseError("Expected TYPE"), SqlRepairReason.SQL_PARSE),
        (DataSkillSqlValidationError(_violation()), SqlRepairReason.DATA_SKILL_VALIDATION),
    ],
)
def test_prepare_error_classification(error: Exception, expected: SqlRepairReason) -> None:
    assert classify_prepare_sql_error(error) == expected


def test_prepare_error_classification_rejects_unknown_errors() -> None:
    assert classify_prepare_sql_error(SingleMessageError("模型服务暂时不可用")) is None
    assert classify_prepare_sql_error(ValueError("unexpected response")) is None


@pytest.mark.parametrize("sqlstate", ["42601", "42804", "42883", "42P18"])
def test_execute_error_accepts_supported_sqlstates(sqlstate: str) -> None:
    assert (
        classify_execute_sql_error(_PgError("localized database error", sqlstate))
        == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    )


@pytest.mark.parametrize("errno", [1064, 1305, 1582])
def test_execute_error_accepts_supported_mysql_errnos(errno: int) -> None:
    assert (
        classify_execute_sql_error(_MysqlError("localized database error", errno))
        == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    )


@pytest.mark.parametrize(
    "message",
    [
        "missing column aliases in recursive WITH query",
        "SQL parse error near SELECT",
        "You have an error in your SQL syntax near 'FROM'",
        "function date_trunc does not exist for this dialect",
        "syntax error at or near SELECT",
        "Column 'e.time' cannot be resolved",
    ],
)
def test_execute_error_accepts_explicit_syntax_or_dialect_text(message: str) -> None:
    wrapped = AppDBError("query failed")
    wrapped.__cause__ = RuntimeError(message)

    assert classify_execute_sql_error(wrapped) == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT


def test_execute_error_accepts_analyticdb_group_by_expression_text() -> None:
    wrapped = AppDBError("query failed")
    wrapped.__cause__ = _MysqlError(
        "DATE_FORMAT(...) must be an aggregate expression or appear in GROUP BY clause",
        1815,
    )

    assert classify_execute_sql_error(wrapped) == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT


def test_mysql_date_format_grouping_rejects_mismatched_projection_expression() -> None:
    sql = """
    SELECT DATE_FORMAT(FROM_UNIXTIME(u.first_pay_time / 1000), '%Y-%m-%d') AS pay_date,
           COUNT(DISTINCT u.uid) AS payer_count
    FROM user u
    WHERE DATE_FORMAT(FROM_UNIXTIME(u.first_pay_time / 1000), '%Y%m%d') BETWEEN '20260701' AND '20260721'
    GROUP BY DATE_FORMAT(FROM_UNIXTIME(u.first_pay_time / 1000), '%Y%m%d')
    """

    with pytest.raises(SqlStructureValidationError, match="DATE_FORMAT"):
        validate_mysql_date_format_grouping(sql)


def test_mysql_date_format_grouping_accepts_matching_projection_expression() -> None:
    sql = """
    SELECT DATE_FORMAT(FROM_UNIXTIME(u.first_pay_time / 1000), '%Y-%m-%d') AS pay_date,
           COUNT(DISTINCT u.uid) AS payer_count
    FROM user u
    WHERE DATE_FORMAT(FROM_UNIXTIME(u.first_pay_time / 1000), '%Y%m%d') BETWEEN '20260701' AND '20260721'
    GROUP BY DATE_FORMAT(FROM_UNIXTIME(u.first_pay_time / 1000), '%Y-%m-%d')
    """

    validate_mysql_date_format_grouping(sql)


def test_execute_error_rejects_unrelated_cannot_be_resolved_text() -> None:
    error = _MysqlError("storage backend cannot be resolved", 1815)

    assert classify_execute_sql_error(error) is None


@pytest.mark.parametrize(
    "error",
    [
        DataUnavailableError("unknown column"),
        AppDBConnectionError("connection refused"),
        TimeoutError("query timeout"),
        PermissionError("permission denied"),
        _PgError('relation "missing_table" does not exist', "42P01"),
        _PgError("permission denied for table orders", "42501"),
        RuntimeError("unknown column 'missing_field' in field list"),
        RuntimeError("access denied for user"),
    ],
)
def test_execute_error_excludes_non_repairable_platform_errors(error: Exception) -> None:
    assert classify_execute_sql_error(error) is None


def test_execute_error_rejects_unrelated_database_failure() -> None:
    assert classify_execute_sql_error(AppDBError("database process crashed")) is None


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("job 42883 failed"),
        RuntimeError(1064),
        RuntimeError("parser error at metadata offset 3"),
    ],
)
def test_execute_error_rejects_untrusted_numeric_and_parser_text(error: Exception) -> None:
    assert classify_execute_sql_error(error) is None


@pytest.mark.parametrize("attribute", ["code", "number"])
def test_execute_error_rejects_untrusted_generic_error_code_attributes(attribute: str) -> None:
    error = RuntimeError("unrelated failure")
    setattr(error, attribute, 1064)

    assert classify_execute_sql_error(error) is None


@pytest.mark.parametrize(
    "message",
    [
        "JSON parse error while decoding driver metadata",
        "failed parsing JSON metadata",
        "error parsing JSON metadata",
        "connection timeout with syntax error",
        "database connection refused with syntax error",
        "connection refused with syntax error",
        "could not connect because of syntax error",
        "connect timed out before syntax error was reported",
        "read timed out while reporting syntax error",
        "query timeout with syntax error",
        "statement timeout with syntax error",
    ],
)
def test_execute_error_rejects_metadata_connection_and_timeout_text_in_cause(
    message: str,
) -> None:
    wrapped = AppDBError("query failed")
    wrapped.__cause__ = RuntimeError(message)

    assert classify_execute_sql_error(wrapped) is None


@pytest.mark.parametrize("chain_attribute", ["__cause__", "orig", "original"])
@pytest.mark.parametrize(
    "message",
    [
        "connection refused with syntax error",
        "query timeout with syntax error",
        "JSON parse error while decoding driver metadata",
        "parse error",
    ],
)
def test_execute_error_text_exclusion_precedes_sqlstate_across_error_chain(
    chain_attribute: str,
    message: str,
) -> None:
    wrapped = AppDBError("query failed")
    setattr(wrapped, chain_attribute, _PgError(message, "42601"))

    assert classify_execute_sql_error(wrapped) is None


def test_error_redaction_walks_error_chain_and_redacts_credentials() -> None:
    outer = RuntimeError("outer password=top-secret")
    cause = RuntimeError(
        "mysql://root:uri-secret@host/db "
        "passwd='pass-secret' pwd: pwd-secret api_key=key-secret "
        'token="token secret with spaces" '
        r'password=\"escaped-secret\" client_secret=client-secret '
        "access_token=access-secret authorization=Bearer auth-secret"
    )
    context = RuntimeError("context password: context-secret")
    outer.__cause__ = cause
    cause.__context__ = context

    message = sanitize_sql_repair_error(outer)

    for secret in (
        "top-secret",
        "uri-secret",
        "pass-secret",
        "pwd-secret",
        "key-secret",
        "token secret with spaces",
        "escaped-secret",
        "client-secret",
        "access-secret",
        "auth-secret",
        "context-secret",
    ):
        assert secret not in message
    assert message.count("[REDACTED]") >= 11
    assert "mysql://root:[REDACTED]@host/db" in message


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('Authorization: Bearer "token with spaces"', "Authorization: Bearer [REDACTED]"),
        ('Proxy-Authorization: Basic "token with spaces"', "Proxy-Authorization: Basic [REDACTED]"),
    ],
)
def test_error_redaction_preserves_authorization_scheme(message: str, expected: str) -> None:
    sanitized = sanitize_sql_repair_error(RuntimeError(message))

    assert "token with spaces" not in sanitized
    assert expected in sanitized


def test_error_redaction_handles_multiterm_authorization_values() -> None:
    message = sanitize_sql_repair_error(
        RuntimeError("Authorization: token with spaces | access_token=secret-token")
    )

    assert "token with spaces" not in message
    assert "secret-token" not in message
    assert "Authorization: [REDACTED]" in message


def test_error_redaction_limits_output_to_2000_characters() -> None:
    message = sanitize_sql_repair_error(RuntimeError("x" * 2500))

    assert len(message) == 2000


def test_sql_repair_fingerprint_is_stable_for_case_and_whitespace() -> None:
    first = SqlRepairContext(
        SqlRepairReason.SQL_PARSE,
        "MySQL",
        "SELECT  1\nFROM dual",
        "Parse   Error",
        None,
        0,
    )
    second = SqlRepairContext(
        SqlRepairReason.SQL_PARSE,
        "mysql",
        " select 1 from DUAL ",
        " parse error ",
        None,
        1,
    )

    assert sql_repair_fingerprint(first) == sql_repair_fingerprint(second)


def test_sql_repair_fingerprint_changes_when_reason_changes() -> None:
    base = SqlRepairContext(
        SqlRepairReason.SQL_PARSE,
        "mysql",
        "SELECT 1",
        "parse error",
        None,
        0,
    )
    changed = SqlRepairContext(
        SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT,
        "mysql",
        "SELECT 1",
        "parse error",
        None,
        0,
    )

    assert sql_repair_fingerprint(base) != sql_repair_fingerprint(changed)


def test_build_sql_repair_message_contains_sanitized_json_contract() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATA_SKILL_VALIDATION,
        dialect="postgres",
        failed_sql="SELECT * FROM orders",
        error_message="postgres://root:secret@host/db password=another-secret",
        violation=_violation(),
        attempt=1,
    )

    message = build_sql_repair_message(context)
    payload = json.loads(message.split("```json\n", maxsplit=1)[1].split("\n```", maxsplit=1)[0])

    assert "重写完整 SQL JSON" in message
    assert "不要返回解释、Markdown 或局部 SQL" in message
    assert "secret" not in message
    assert "another-secret" not in message
    assert payload == {
        "reason": "data_skill_validation",
        "dialect": "postgres",
        "failed_sql": "SELECT * FROM orders",
        "error": "postgres://root:[REDACTED]@host/db password=[REDACTED]",
        "attempt": 1,
        "max_attempts": 2,
        "violation": {
            "message": "口径错误",
            "rule_index": 0,
            "missing_required_contains": ["required"],
            "missing_required_patterns": [r"count\s*\("],
            "matched_forbidden_contains": ["forbidden"],
            "matched_forbidden_patterns": [r"select\s+\*"],
            "matched_forbidden_groups": [["legacy_table", "legacy_field"]],
        },
    }

def test_regenerate_sql_after_error_streaming_reasoning_uses_structured_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.sql_message = []
    context = SqlRepairContext(
        reason=SqlRepairReason.DATA_SKILL_VALIDATION,
        dialect="postgres",
        failed_sql="SELECT * FROM orders",
        error_message="口径错误",
        violation=_violation(),
        attempt=1,
    )
    calls: list[tuple[object, bool, bool]] = []

    def _generate_sql_text_streaming_reasoning(
        session: object,
        in_chat: bool,
        append_question: bool = True,
    ):
        calls.append((session, in_chat, append_question))
        yield "reasoning-chunk"
        return "repaired-sql"

    monkeypatch.setattr(
        service,
        "generate_sql_text_streaming_reasoning",
        _generate_sql_text_streaming_reasoning,
    )
    session = object()

    result = service.regenerate_sql_after_error_streaming_reasoning(
        session,
        context,
        in_chat=True,
    )

    assert next(result) == "reasoning-chunk"
    with pytest.raises(StopIteration) as exc_info:
        next(result)

    assert exc_info.value.value == "repaired-sql"
    assert calls == [(session, True, False)]
    assert len(service.sql_message) == 1
    assert isinstance(service.sql_message[0], HumanMessage)
    assert service.sql_message[0].content == build_sql_repair_message(context)


def test_execute_sql_preserves_wrapped_exception_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.ds = SimpleNamespace(id=1001)
    service.table_name_list = ["orders"]
    service.chat_question = SimpleNamespace(sql="SELECT * FROM orders")
    original_error = RuntimeError("database syntax failed")

    def _execute_external_user_query_or_raise(**_kwargs):
        raise original_error

    monkeypatch.setattr(
        llm,
        "execute_external_user_query_or_raise",
        _execute_external_user_query_or_raise,
    )

    with pytest.raises(AppDBError) as exc_info:
        service.execute_sql(session=object(), sql="SELECT * FROM orders")

    assert exc_info.value.__cause__ is original_error
    assert "RuntimeError: database syntax failed" in str(exc_info.value)


def test_execute_sql_reraises_parse_result_error_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.ds = SimpleNamespace(id=1001)
    service.table_name_list = ["orders"]
    service.chat_question = SimpleNamespace(sql="SELECT * FROM orders")
    original_error = ParseSQLResultError("invalid result")

    def _execute_external_user_query_or_raise(**_kwargs):
        raise original_error

    monkeypatch.setattr(
        llm,
        "execute_external_user_query_or_raise",
        _execute_external_user_query_or_raise,
    )

    with pytest.raises(ParseSQLResultError) as exc_info:
        service.execute_sql(session=object(), sql="SELECT * FROM orders")

    assert exc_info.value is original_error
