"""
脚本说明：提供领域无关的 SQL 修复上下文、错误分类、脱敏、指纹和提示构造能力。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from apps.chat.service.chat_date_filter import ChatDateFilterConfigurationError
from common.error import AppDBConnectionError, DataUnavailableError, SingleMessageError
from common.user_facing_errors import (
    DATA_UNAVAILABLE_ERROR_TYPE,
    PERMISSION_DENIED_ERROR_TYPE,
    classify_error,
)

SQL_REPAIR_MAX_ATTEMPTS = 2
_MAX_ERROR_LENGTH = 2000
_REPAIRABLE_SQLSTATES = {"42601", "42804", "42883", "42P18"}
_REPAIRABLE_ERRNOS = {1064, 1305, 1582}
_NON_REPAIRABLE_ERROR_TYPES = {
    PERMISSION_DENIED_ERROR_TYPE,
    DATA_UNAVAILABLE_ERROR_TYPE,
}
_PREPARE_RESPONSE_FORMAT_MARKERS = (
    "sql answer is not a valid json object",
    "sql response is not a valid json object",
    "sql answer is not valid json",
    "sql response is not valid json",
)
_PREPARE_EMPTY_SQL_PATTERNS = (
    re.compile(r"\b(?:sql|sql answer|sql response|sql text|sql query)\s+(?:is\s+)?empty\b", re.IGNORECASE),
    re.compile(r"\bempty\s+sql(?:\s+(?:answer|response|text|query))?\b", re.IGNORECASE),
)
_NON_REPAIRABLE_EXECUTE_TEXT_PATTERNS = (
    re.compile(r"\bjson\s+parse\s+error\b", re.IGNORECASE),
    re.compile(r"\b(?:failed to|failed|error while|error parsing|error|unable to)\s+(?:parse|parsing|decode|decoding)\s+(?:json\s+)?metadata\b", re.IGNORECASE),
    re.compile(r"\b(?:json\s+metadata|metadata)\s+(?:parse|parsing|decode|decoding)\s+(?:failed|error)\b", re.IGNORECASE),
    re.compile(r"\bparse\s+error\b.{0,100}\b(?:driver\s+)?metadata\b", re.IGNORECASE),
    re.compile(r"\bconnection\s+timeout\b", re.IGNORECASE),
    re.compile(r"\bdatabase\s+connection\s+refused\b", re.IGNORECASE),
    re.compile(r"\bconnection\s+refused\b", re.IGNORECASE),
    re.compile(r"\bcould\s+not\s+connect\b", re.IGNORECASE),
    re.compile(r"\bconnect\s+timed\s+out\b", re.IGNORECASE),
    re.compile(r"\bread\s+timed\s+out\b", re.IGNORECASE),
    re.compile(r"\btimed\s+out\b", re.IGNORECASE),
    re.compile(r"\btimeout\b", re.IGNORECASE),
    re.compile(r"\bquery\s+timeout\b", re.IGNORECASE),
    re.compile(r"\bstatement\s+timeout\b", re.IGNORECASE),
)
_GENERIC_PARSE_ERROR_PATTERN = re.compile(r"\bparse\s+error\b", re.IGNORECASE)
_EXPLICIT_SQL_PARSE_ERROR_PATTERN = re.compile(r"\bsql\s+parse\s+error\b", re.IGNORECASE)
_EXECUTE_SYNTAX_OR_DIALECT_PATTERNS = (
    re.compile(r"missing column aliases in recursive\s+with\s+query", re.IGNORECASE),
    re.compile(r"\bsql\s+parse\s+error\b", re.IGNORECASE),
    re.compile(r"\b(?:sql|query|database)\s+syntax\s+error\b", re.IGNORECASE),
    re.compile(r"\bsyntax error\s+(?:at|near|in|for)\b", re.IGNORECASE),
    re.compile(r"\byou have an error in your sql syntax\b", re.IGNORECASE),
    re.compile(r"\bunexpected (?:token|keyword)\b", re.IGNORECASE),
    re.compile(r"\bunsupported\b.{0,80}\bdialect\b", re.IGNORECASE),
    re.compile(r"\bnot supported\b.{0,80}\bdialect\b", re.IGNORECASE),
    re.compile(r"\bdoes not exist for (?:this|the) dialect\b", re.IGNORECASE),
    re.compile(r"\bfunction\b.{0,160}\bdoes not exist\b", re.IGNORECASE),
    re.compile(r"\bno function matches\b", re.IGNORECASE),
    re.compile(r"\bincorrect (?:parameter count|parameters)\b.{0,80}\bfunction\b", re.IGNORECASE),
    re.compile(r"\bwrong number of arguments\b.{0,80}\bfunction\b", re.IGNORECASE),
    re.compile(
        r"\bcolumn\s+['\"`]?[^'\"`\s]+['\"`]?\s+cannot be resolved\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmust be an aggregate expression or appear in (?:the )?group by clause\b",
        re.IGNORECASE,
    ),
)
_PREPARE_DATE_FILTER_CONFIGURATION_PATTERN = re.compile(
    r"日期参数配置无效\s*[：:]\s*(?:"
    r"missing_parameters|database_current_date|metric_chart|"
    r"realtime_requires_hourly_time_series|"
    r"missing_date_filter|invalid_date_filter|missing_time_field|"
    r"invalid_parameter_type|mixed_parameter_families|parameter_type_mismatch|"
    r"incomplete_parameters|missing_date_expression"
    r")",
    re.IGNORECASE,
)
_URI_PASSWORD_PATTERN = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^\s/:@]+:)(?P<secret>[^\s/@]+)(?=@)",
    re.IGNORECASE,
)
_AUTHORIZATION_VALUE_PATTERN = re.compile(
    r"(?P<key>\b(?:authorization|proxy-authorization)\b)"
    r"(?!(?:\s*[:=]\s*)(?:bearer|basic)\b)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^|]+?)(?=\s+\b(?:password|passwd|pwd|api_key|token|client_secret|access_token|authorization|proxy-authorization)\b\s*[:=]|\s*\|\s*|$)",
    re.IGNORECASE,
)
_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"(?P<key>\b(?:authorization|proxy-authorization)\b)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<scheme>bearer|basic)\s+"
    r"(?P<secret>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;&]+)",
    re.IGNORECASE,
)


_NAMED_SECRET_PATTERN = re.compile(
    r"(?P<key>\b(?:password|passwd|pwd|api_key|token|client_secret|access_token)\b)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>"
    r"\\(?P<escaped_quote>[\"'])(?P<escaped_secret>.*?)\\(?P=escaped_quote)"
    r"|\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
    re.IGNORECASE,
)


class SqlRepairReason(str, Enum):
    SQL_RESPONSE_FORMAT = "sql_response_format"
    SQL_PARSE = "sql_parse"
    DATA_SKILL_VALIDATION = "data_skill_validation"
    DATE_FILTER_CONFIGURATION = "date_filter_configuration"
    DATABASE_SYNTAX_OR_DIALECT = "database_syntax_or_dialect"


@dataclass(frozen=True)
class DataSkillSqlViolation:
    message: str
    rule_index: int
    missing_required_contains: tuple[str, ...]
    missing_required_patterns: tuple[str, ...]
    matched_forbidden_contains: tuple[str, ...]
    matched_forbidden_patterns: tuple[str, ...]
    matched_forbidden_groups: tuple[tuple[str, ...], ...]


class DataSkillSqlValidationError(SingleMessageError):
    def __init__(self, violation: DataSkillSqlViolation | str):
        self.violation = violation if isinstance(violation, DataSkillSqlViolation) else None
        super().__init__(violation.message if self.violation is not None else str(violation))


class SqlStructureValidationError(SingleMessageError):
    """SQL 结构不符合当前数据库方言要求。"""


@dataclass(frozen=True)
class SqlRepairContext:
    reason: SqlRepairReason
    dialect: str
    failed_sql: str
    error_message: str
    violation: DataSkillSqlViolation | None
    attempt: int
    max_attempts: int = SQL_REPAIR_MAX_ATTEMPTS


def _walk_error_chain(error: Any):
    seen: set[int] = set()
    pending = [error]
    while pending:
        item = pending.pop(0)
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        for attribute in ("orig", "original", "__cause__", "__context__"):
            nested = getattr(item, attribute, None)
            if nested is not None:
                pending.append(nested)


def _error_chain_message(error: Any) -> str:
    messages: list[str] = []
    for item in _walk_error_chain(error):
        text = str(item or "").strip()
        if text and text not in messages:
            messages.append(text)
    return " | ".join(messages)


def _redact_named_secret(match: re.Match[str]) -> str:
    value = match.group("value")
    quote = value[0] if len(value) >= 2 and value[0] in {"\"", "'"} and value[-1] == value[0] else ""
    return f"{match.group('key')}{match.group('separator')}{quote}[REDACTED]{quote}"


def sanitize_sql_repair_error(error: Any) -> str:
    message = _error_chain_message(error)
    message = _URI_PASSWORD_PATTERN.sub(r"\g<prefix>[REDACTED]", message)
    message = _AUTHORIZATION_VALUE_PATTERN.sub(_redact_named_secret, message)
    message = _AUTHORIZATION_HEADER_PATTERN.sub(r"\g<key>\g<separator>\g<scheme> [REDACTED]", message)
    message = _NAMED_SECRET_PATTERN.sub(_redact_named_secret, message)
    return message[:_MAX_ERROR_LENGTH]


def classify_prepare_sql_error(error: Exception) -> SqlRepairReason | None:
    if any(isinstance(item, ChatDateFilterConfigurationError) for item in _walk_error_chain(error)):
        return SqlRepairReason.DATE_FILTER_CONFIGURATION
    if any(isinstance(item, DataSkillSqlValidationError) for item in _walk_error_chain(error)):
        return SqlRepairReason.DATA_SKILL_VALIDATION
    if any(isinstance(item, ParseError) for item in _walk_error_chain(error)):
        return SqlRepairReason.SQL_PARSE
    if any(isinstance(item, SqlStructureValidationError) for item in _walk_error_chain(error)):
        return SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT

    message = _error_chain_message(error)
    lowered = message.lower()
    if any(marker in lowered for marker in _PREPARE_RESPONSE_FORMAT_MARKERS):
        return SqlRepairReason.SQL_RESPONSE_FORMAT
    if any(pattern.search(message) for pattern in _PREPARE_EMPTY_SQL_PATTERNS):
        return SqlRepairReason.SQL_RESPONSE_FORMAT
    if any(
        _PREPARE_DATE_FILTER_CONFIGURATION_PATTERN.fullmatch(str(item or "").strip())
        for item in _walk_error_chain(error)
    ):
        return SqlRepairReason.DATE_FILTER_CONFIGURATION
    if "parse sql error" in lowered:
        return SqlRepairReason.SQL_PARSE
    return None


def _normalized_mysql_expression(expression: exp.Expression) -> str:
    return " ".join(
        expression.sql(dialect="mysql", normalize=True, pretty=False).lower().split()
    )


def validate_mysql_date_format_grouping(sql: str) -> None:
    """校验 MySQL/AnalyticDB 的 DATE_FORMAT 投影可由分组键确定。"""
    for statement in sqlglot.parse(sql, read="mysql"):
        for select in statement.find_all(exp.Select):
            group = select.args.get("group")
            if group is None:
                continue
            grouped_expressions = {
                _normalized_mysql_expression(expression)
                for expression in group.expressions
            }
            directly_grouped_columns = {
                _normalized_mysql_expression(expression)
                for expression in group.expressions
                if isinstance(expression, exp.Column)
            }
            for projection in select.expressions:
                expression = projection.unalias()
                if any(isinstance(node, exp.AggFunc) for node in expression.walk()):
                    continue
                if not any(isinstance(node, exp.TimeToStr) for node in expression.walk()):
                    continue
                if _normalized_mysql_expression(expression) in grouped_expressions:
                    continue
                referenced_columns = {
                    _normalized_mysql_expression(column)
                    for column in expression.find_all(exp.Column)
                }
                if referenced_columns and referenced_columns <= directly_grouped_columns:
                    continue
                raise SqlStructureValidationError(
                    "MySQL/AnalyticDB 的非聚合 DATE_FORMAT 投影必须以完全相同的表达式出现在 "
                    "GROUP BY 中，或其依赖的原始字段必须直接分组；不得仅按另一个不同的日期表达式分组。"
                )


def _candidate_sqlstates(error: Any) -> set[str]:
    sqlstates: set[str] = set()
    for item in _walk_error_chain(error):
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(item, attribute, None)
            if value:
                sqlstates.add(str(value).upper())
        diagnostic = getattr(item, "diag", None)
        value = getattr(diagnostic, "sqlstate", None) if diagnostic is not None else None
        if value:
            sqlstates.add(str(value).upper())
    return sqlstates


def _candidate_errnos(error: Any) -> set[int]:
    errnos: set[int] = set()
    for item in _walk_error_chain(error):
        for attribute in ("errno",):
            value = getattr(item, attribute, None)
            if isinstance(value, int):
                errnos.add(value)
            elif isinstance(value, str) and value.isdigit():
                errnos.add(int(value))
    return errnos


def classify_execute_sql_error(error: Exception) -> SqlRepairReason | None:
    excluded_types = (DataUnavailableError, AppDBConnectionError, TimeoutError, PermissionError)
    if any(isinstance(item, excluded_types) for item in _walk_error_chain(error)):
        return None

    message = _error_chain_message(error)
    if any(pattern.search(message) for pattern in _NON_REPAIRABLE_EXECUTE_TEXT_PATTERNS):
        return None
    if _GENERIC_PARSE_ERROR_PATTERN.search(message) and not _EXPLICIT_SQL_PARSE_ERROR_PATTERN.search(message):
        return None

    platform_classification = classify_error(error)
    if platform_classification.error_type in _NON_REPAIRABLE_ERROR_TYPES:
        return None

    if _candidate_sqlstates(error) & _REPAIRABLE_SQLSTATES:
        return SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    if _candidate_errnos(error) & _REPAIRABLE_ERRNOS:
        return SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT

    if any(pattern.search(message) for pattern in _EXECUTE_SYNTAX_OR_DIALECT_PATTERNS):
        return SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    return None


def _normalize_fingerprint_text(value: str) -> str:
    return " ".join(str(value or "").split()).lower()


def sql_repair_fingerprint(context: SqlRepairContext) -> str:
    payload = {
        "reason": context.reason.value,
        "dialect": _normalize_fingerprint_text(context.dialect),
        "failed_sql": _normalize_fingerprint_text(context.failed_sql),
        "error": _normalize_fingerprint_text(sanitize_sql_repair_error(context.error_message)),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_sql_repair_message(context: SqlRepairContext) -> str:
    payload = {
        "reason": context.reason.value,
        "dialect": context.dialect,
        "failed_sql": context.failed_sql,
        "error": sanitize_sql_repair_error(context.error_message),
        "attempt": context.attempt,
        "max_attempts": context.max_attempts,
        "violation": asdict(context.violation) if context.violation is not None else None,
    }
    if context.reason is SqlRepairReason.DATE_FILTER_CONFIGURATION:
        payload["repair_requirements"] = [
            (
                "具备时间字段的非 metric 图表必须返回完整 date_filter，SQL 日期边界必须使用与 "
                "date_parameter_type 匹配的看板日期 token；yyyymmdd_number 使用 "
                "{{dashboard_start_yyyymmdd}} 和 {{dashboard_end_yyyymmdd}}。"
            ),
            (
                "问题要求趋势、走势、变化或按日/周/月/小时时间序列但未明确时间窗口时，必须默认使用最近七天，"
                "date_expression 使用 {\"version\":1,\"mode\":\"preset\",\"preset\":\"past_7_days\"}；"
                "不得省略日期过滤，也不得改为查询全历史。"
            ),
            (
                "metric 图表不得返回 date_filter，也不得使用看板日期 token；保留用户要求的固定时间语义。"
            ),
            (
                "date_filter 存在时不得使用 CURDATE、CURRENT_DATE、NOW、CURRENT_TIMESTAMP、"
                "LOCALTIME、LOCALTIMESTAMP、GETDATE 或 GETUTCDATE。"
            ),
        ]
        if "realtime_requires_hourly_time_series" in context.error_message:
            payload["repair_requirements"].append(
                "用户请求实时数据但上一版返回了 metric；除非问题明确要求总额、合计、单值、指标卡或当前累计，"
                "必须返回按时间字段分组的非 metric 小时序列，并提供完整 date_filter。"
            )
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    date_contract_guidance = ""
    if context.reason is SqlRepairReason.DASHBOARD_DATE_CONTRACT:
        date_contract_guidance = (
            "固定语义 metric 不得返回 date_filter；可变时间图表必须让 SQL 使用与 "
            "date_parameter_type 匹配的看板日期 token，并让 time_field 对应实际过滤字段；"
            "date_filter 存在时不得使用 CURDATE、CURRENT_DATE、NOW 或同类当前时间函数。\n"
        )
    return (
        "上一版 SQL 未通过校验或执行，请根据下方修复上下文重写完整 SQL JSON。\n"
        "只修复上下文指出的问题，继续遵守当前数据源、权限和 Data Skills 约束，"
        "不得编造表、字段或业务口径。\n"
        f"{date_contract_guidance}"
        "请仅返回完整 SQL JSON，不要返回解释、Markdown 或局部 SQL。\n"
        f"```json\n{serialized}\n```"
    )
