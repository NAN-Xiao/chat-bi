"""
脚本说明：验证 SQL 修复上下文、错误分类、脱敏、指纹与提示契约。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from sqlglot.errors import ParseError, TokenError

from apps.chat.service.chat_date_filter import ChatDateFilterConfigurationError
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
    validate_mysql_compatible_sql,
    validate_sql_for_datasource,
    validate_mysql_date_format_grouping,
)
from apps.datasource.crud.permission_errors import SqlSchemaScopeError
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
        (TokenError("Missing quote"), SqlRepairReason.SQL_PARSE),
        (DataSkillSqlValidationError(_violation()), SqlRepairReason.DATA_SKILL_VALIDATION),
        (
            SingleMessageError("日期参数配置无效：missing_parameters"),
            SqlRepairReason.DATE_FILTER_CONFIGURATION,
        ),
        (
            SingleMessageError("日期参数配置无效：database_current_date"),
            SqlRepairReason.DATE_FILTER_CONFIGURATION,
        ),
        (
            SingleMessageError("日期参数配置无效：metric_chart"),
            SqlRepairReason.DATE_FILTER_CONFIGURATION,
        ),
        (
            SingleMessageError("日期参数配置无效：realtime_requires_hourly_time_series"),
            SqlRepairReason.DATE_FILTER_CONFIGURATION,
        ),
        *[
            (
                SingleMessageError(f"日期参数配置无效：{code}"),
                SqlRepairReason.DATE_FILTER_CONFIGURATION,
            )
            for code in (
                "missing_date_filter",
                "invalid_date_filter",
                "missing_time_field",
                "invalid_parameter_type",
                "mixed_parameter_families",
                "parameter_type_mismatch",
                "incomplete_parameters",
                "missing_date_expression",
                "invalid_date_expression",
            )
        ],
        (
            ChatDateFilterConfigurationError("missing_parameters"),
            SqlRepairReason.DATE_FILTER_CONFIGURATION,
        ),
    ],
)
def test_prepare_error_classification(error: Exception, expected: SqlRepairReason) -> None:
    assert classify_prepare_sql_error(error) == expected


def test_prepare_error_classification_rejects_unknown_errors() -> None:
    assert classify_prepare_sql_error(SingleMessageError("模型服务暂时不可用")) is None
    assert classify_prepare_sql_error(ValueError("unexpected response")) is None


def test_prepare_schema_scope_error_is_repairable() -> None:
    error = SqlSchemaScopeError(
        "SQL 引用了当前 Schema 中不存在或无法解析的字段：p.channel",
        fields={"p.channel"},
    )

    assert classify_prepare_sql_error(error) == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT

    message = build_sql_repair_message(SqlRepairContext(
        reason=SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT,
        dialect="postgresql",
        failed_sql="SELECT MAX(p.channel) FROM fact_payments p",
        error_message=str(error),
        violation=None,
        attempt=1,
    ))
    assert "当前 Schema 明确提供的表和字段" in message
    assert "无关字段" in message


@pytest.mark.parametrize(
    "message",
    [
        "上游失败：日期参数配置无效：missing_parameters",
        "日期参数配置无效：database_current_date，请稍后重试",
        "日期参数配置无效：metric_chart | unrelated failure",
    ],
)
def test_prepare_error_classification_rejects_embedded_date_filter_markers(message: str) -> None:
    assert classify_prepare_sql_error(SingleMessageError(message)) is None


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


def test_recursive_alias_error_requires_non_recursive_repair() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT,
        dialect="mysql",
        failed_sql="WITH RECURSIVE date_series(dt) AS (...) SELECT * FROM date_series",
        error_message="missing column aliases in recursive WITH query",
        violation=None,
        attempt=1,
    )

    message = build_sql_repair_message(context)

    assert "禁止使用 WITH RECURSIVE" in message
    assert "仅补充 CTE 列别名后重试" in message
    assert "非递归数字序列" in message


def test_execute_error_accepts_analyticdb_group_by_expression_text() -> None:
    wrapped = AppDBError("query failed")
    wrapped.__cause__ = _MysqlError(
        "DATE_FORMAT(...) must be an aggregate expression or appear in GROUP BY clause",
        1815,
    )

    assert classify_execute_sql_error(wrapped) == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT


def test_execute_error_accepts_database_rejected_unsigned_cast() -> None:
    wrapped = AppDBError("query failed")
    wrapped.__cause__ = RuntimeError("target database does not support UNSIGNED cast target")

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


def test_mysql_date_format_grouping_accepts_projection_derived_from_grouped_columns() -> None:
    sql = """
    SELECT CAST(
               DATE_FORMAT(
                   DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY),
                   '%Y%m%d'
               ) AS SIGNED
           ) AS mature_date,
           e.uid AS user_id
    FROM event e
    GROUP BY e.dt, e.uid
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


def test_build_date_filter_repair_message_contains_explicit_contract() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATE_FILTER_CONFIGURATION,
        dialect="mysql",
        failed_sql="SELECT COUNT(*) FROM event WHERE dt = 20260730",
        error_message="日期参数配置无效：missing_parameters",
        violation=None,
        attempt=0,
    )

    message = build_sql_repair_message(context)

    assert "{{dashboard_start_yyyymmdd}}" in message
    assert "{{dashboard_end_yyyymmdd}}" in message
    assert "metric" in message
    assert "date_filter" in message
    assert "CURDATE" in message
    assert "不得省略日期过滤" in message
    assert "past_7_days" in message


def test_build_realtime_hourly_repair_message_requires_time_series() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATE_FILTER_CONFIGURATION,
        dialect="mysql",
        failed_sql="SELECT SUM(amount) FROM event_realtime",
        error_message="日期参数配置无效：realtime_requires_hourly_time_series",
        violation=None,
        attempt=0,
    )

    message = build_sql_repair_message(context)

    assert "用户明确要求按小时或时间趋势" in message
    assert "按 event_realtime.time 分组的非 metric 小时序列" in message
    assert "完整 date_filter" in message


def test_generic_dialect_repair_does_not_globally_forbid_unsigned() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT,
        dialect="mysql",
        failed_sql="SELECT CAST(dt AS UNSIGNED) FROM event",
        error_message="syntax error near SELECT",
        violation=None,
        attempt=0,
    )

    message = build_sql_repair_message(context)

    assert "禁止 CAST(... AS UNSIGNED)" not in message
    assert "拒绝当前 UNSIGNED 用法" not in message


def test_dialect_repair_mentions_unsigned_only_after_database_rejects_it() -> None:
    context = SqlRepairContext(
        reason=SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT,
        dialect="mysql",
        failed_sql="SELECT CAST(dt AS UNSIGNED) FROM event",
        error_message="database does not support UNSIGNED cast target",
        violation=None,
        attempt=0,
    )

    message = build_sql_repair_message(context)

    assert "目标数据库已在执行错误中拒绝当前 UNSIGNED 用法" in message


@pytest.mark.parametrize(
    "sql",
    [
        "WITH RECURSIVE days AS "
        "(SELECT 1 UNION ALL SELECT day_value + 1 FROM days) SELECT * FROM days",
        "SELECT DATE_FORMAT(dt, '%v') FROM event",
    ],
)
def test_mysql_compatible_sql_rejects_known_adb_incompatibilities(sql: str) -> None:
    with pytest.raises(SqlStructureValidationError):
        validate_mysql_compatible_sql(sql)


def test_mysql_compatible_sql_allows_unsigned_casts_supported_by_mysql() -> None:
    validate_mysql_compatible_sql(
        "SELECT CAST({{dashboard_start_yyyymmdd}} AS UNSIGNED) AS start_dt, "
        "CAST({{dashboard_end_yyyymmdd}} AS UNSIGNED) AS end_dt"
    )
    validate_sql_for_datasource("SELECT CAST(1 AS UNSIGNED) AS value", "mysql")


def test_mysql_compatible_sql_requires_recursive_cte_column_aliases() -> None:
    validate_mysql_compatible_sql(
        "WITH RECURSIVE days(day_value) AS "
        "(SELECT 1 UNION ALL SELECT day_value + 1 FROM days) "
        "SELECT day_value FROM days"
    )


def test_mysql_compatible_sql_rejects_recursive_date_time_scaffolds() -> None:
    with pytest.raises(SqlStructureValidationError, match="日期时间骨架默认禁止"):
        validate_mysql_compatible_sql(
            "WITH RECURSIVE date_seq(dt, date_value) AS "
            "(SELECT 1, DATE '2026-08-01' UNION ALL "
            "SELECT dt + 1, DATE_ADD(date_value, INTERVAL 1 DAY) FROM date_seq) "
            "SELECT * FROM date_seq"
        )


def test_mysql_compatible_sql_allows_non_recursive_ctes_in_recursive_with() -> None:
    sql = (
        "WITH RECURSIVE seq(n) AS (SELECT 1 AS n UNION ALL SELECT n + 1 AS n FROM seq), "
        "metrics AS (SELECT 1 AS value) SELECT * FROM seq CROSS JOIN metrics"
    )
    validate_mysql_compatible_sql(sql)

    validate_mysql_compatible_sql(
        "WITH RECURSIVE seq(n) AS (SELECT 1 AS n UNION ALL SELECT n + 1 AS n FROM seq), "
        "metrics(value) AS (SELECT 1 AS value) SELECT * FROM seq CROSS JOIN metrics"
    )


def test_mysql_compatible_sql_rejects_raw_fact_range_join_to_time_scaffold() -> None:
    sql = """
    WITH params AS (
        SELECT CAST('2026-08-01' AS DATE) AS start_date,
               CAST('2026-08-08' AS DATE) AS end_date
    ),
    week_offsets AS (
        SELECT 0 AS offset_week UNION ALL SELECT 1
    ),
    calendar AS (
        SELECT DATE_ADD(p.start_date, INTERVAL w.offset_week * 7 DAY) AS week_start
        FROM params p CROSS JOIN week_offsets w
    )
    SELECT c.week_start, COUNT(*) AS event_count
    FROM event e
    JOIN calendar c
      ON e.dt >= c.week_start
     AND e.dt < DATE_ADD(c.week_start, INTERVAL 7 DAY)
    GROUP BY c.week_start
    """
    with pytest.raises(SqlStructureValidationError, match="时间骨架"):
        validate_mysql_compatible_sql(sql)


def test_mysql_compatible_sql_allows_aggregated_cte_range_join_to_time_scaffold() -> None:
    sql = """
    WITH calendar AS (
        SELECT CAST('2026-08-01' AS DATE) AS week_start
    ),
    metrics AS (
        SELECT CAST('2026-08-03' AS DATE) AS metric_date, 1 AS value
    )
    SELECT c.week_start, COALESCE(SUM(m.value), 0) AS value
    FROM metrics m
    JOIN calendar c
      ON m.metric_date >= c.week_start
     AND m.metric_date < DATE_ADD(c.week_start, INTERVAL 7 DAY)
    GROUP BY c.week_start
    """
    validate_mysql_compatible_sql(sql)


def test_mysql_compatible_sql_rejects_dynamic_week_interval_but_allows_day_interval() -> None:
    with pytest.raises(SqlStructureValidationError, match="INTERVAL <列或表达式> WEEK"):
        validate_mysql_compatible_sql(
            "WITH offsets(n) AS (SELECT 1) "
            "SELECT DATE_SUB(CAST('2026-08-01' AS DATE), INTERVAL offsets.n WEEK) "
            "FROM offsets"
        )
    validate_mysql_compatible_sql(
        "WITH offsets(n) AS (SELECT 1) "
        "SELECT DATE_SUB(CAST('2026-08-01' AS DATE), INTERVAL (offsets.n * 7) DAY) "
        "FROM offsets"
    )


def test_mysql_compatible_sql_converts_tokenizer_internal_errors_to_repairable_errors() -> None:
    with pytest.raises(SqlStructureValidationError, match="结构解析"):
        validate_mysql_compatible_sql(
            "WITH RECURSIVE days(日期) AS ("
            "SELECT STR_TO_DATE('2026-08-01', '%Y%m%d') "
            "UNION ALL SELECT DATE_ADD(日期，INTERVAL 1 DAY) FROM days) "
            "SELECT 日期 FROM days"
        )


def test_validate_sql_for_datasource_uses_mysql_rules() -> None:
    with pytest.raises(SqlStructureValidationError):
        validate_sql_for_datasource(
            "SELECT DATE_SUB(CAST('2026-08-01' AS DATE), INTERVAL n WEEK) FROM offsets",
            "mysql",
        )
    validate_sql_for_datasource("SELECT 1", "postgresql")


def test_execute_sql_error_classifier_accepts_structure_validation_errors() -> None:
    assert (
        classify_execute_sql_error(SqlStructureValidationError("INTERVAL <列或表达式> WEEK"))
        is SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    )


def test_execute_sql_error_classifier_accepts_adb_dynamic_week_message() -> None:
    assert (
        classify_execute_sql_error(Exception("not support : INTERVAL w.offset_week WEEK"))
        is SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    )


def test_mysql_compatible_sql_ignores_unsigned_inside_literal_or_comment() -> None:
    validate_mysql_compatible_sql(
        "SELECT 'CAST(value AS UNSIGNED)' AS example_text "
        "FROM event /* AS UNSIGNED is documentation */"
    )


def test_mysql_compatible_sql_rejects_ambiguous_duplicate_cte_outputs() -> None:
    sql = (
        "WITH left_metrics AS (SELECT 1 AS 渠道), "
        "right_metrics AS (SELECT 2 AS 渠道) "
        "SELECT 渠道 FROM left_metrics l JOIN right_metrics r ON 1 = 1"
    )
    with pytest.raises(SqlStructureValidationError, match="同名输出列"):
        validate_mysql_compatible_sql(sql)

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
