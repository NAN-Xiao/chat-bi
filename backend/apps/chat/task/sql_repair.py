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
from sqlglot.errors import ParseError, TokenError
from sqlglot.optimizer.scope import traverse_scope

from apps.chat.service.chat_date_filter import ChatDateFilterConfigurationError
from apps.datasource.crud.permission_errors import SqlSchemaScopeError
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
    re.compile(r"\bcorrelated\s+subquery\b.{0,200}\b(?:unsupported|not supported|does not support)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+support\b.{0,100}\binterval\b", re.IGNORECASE),
    re.compile(r"\b(?:unsupported|not supported|does not support)\b.{0,100}\bweek\b", re.IGNORECASE),
    re.compile(r"\b(?:unknown|unsupported|not supported|does not support)\b.{0,80}\bunsigned\b", re.IGNORECASE),
    re.compile(r"\bunsigned\b.{0,80}\b(?:unknown|unsupported|not supported|does not support)\b", re.IGNORECASE),
    re.compile(r"\billegal pattern component\s*:\s*[vx]\b", re.IGNORECASE),
    re.compile(r"\b(?:column|field)\b.{0,80}\bambiguous\b", re.IGNORECASE),
    re.compile(r"\berror tokeniz(?:ing|er)\b", re.IGNORECASE),
    re.compile(r"\bmissing\s+\S+\s+from\b", re.IGNORECASE),
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
    r"incomplete_parameters|missing_date_expression|invalid_date_expression|"
    r"missing_time_scope|missing_time_range|invalid_time_range|"
    r"time_range_exceeds_business_date|invalid_default_time_range|invalid_current_day_time_range|"
    r"time_range_mismatch|"
    r"sql_time_range_mismatch"
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
    if any(isinstance(item, (ParseError, TokenError)) for item in _walk_error_chain(error)):
        return SqlRepairReason.SQL_PARSE
    if any(isinstance(item, SqlStructureValidationError) for item in _walk_error_chain(error)):
        return SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    if any(isinstance(item, SqlSchemaScopeError) for item in _walk_error_chain(error)):
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


def _normalized_sql_for_structure_validation(sql: str) -> str:
    return re.sub(r"\{\{[^{}]+\}\}", "0", str(sql or ""))


def _nearest_select(expression: exp.Expression) -> exp.Select | None:
    parent = expression.parent
    while parent is not None and not isinstance(parent, exp.Select):
        parent = parent.parent
    return parent if isinstance(parent, exp.Select) else None


def _select_output_names(expression: exp.Expression | None) -> set[str]:
    if isinstance(expression, exp.Select):
        select = expression
    else:
        select = expression.find(exp.Select) if expression is not None else None
    if select is None:
        return set()
    return {
        str(name or "").strip('"\x60[]').lower()
        for name in select.named_selects
        if str(name or "").strip() not in {"", "*"}
    }


def _source_output_names(
    source: exp.Expression | None,
    cte_outputs: dict[str, set[str]],
) -> set[str]:
    if isinstance(source, exp.Table):
        return cte_outputs.get(str(source.name or "").strip('"\x60[]').lower(), set())
    if isinstance(source, exp.Subquery):
        return _select_output_names(source.this)
    return set()


def _ambiguous_unqualified_columns(statement: exp.Expression) -> set[str]:
    cte_outputs = {
        str(cte.alias_or_name or "").strip('"\x60[]').lower(): _select_output_names(cte.this)
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    ambiguous: set[str] = set()
    for select in statement.find_all(exp.Select):
        from_clause = select.args.get("from_")
        sources = (
            [from_clause.this]
            if from_clause is not None and from_clause.this is not None
            else []
        )
        sources.extend(
            join.this
            for join in select.args.get("joins") or []
            if join.this is not None
        )
        counts: dict[str, int] = {}
        for source in sources:
            for name in _source_output_names(source, cte_outputs):
                counts[name] = counts.get(name, 0) + 1
        duplicate_names = {name for name, count in counts.items() if count > 1}
        if not duplicate_names:
            continue
        for column in select.find_all(exp.Column):
            if _nearest_select(column) is not select or column.table:
                continue
            name = str(column.name or "").strip('"\x60[]').lower()
            if name in duplicate_names:
                ambiguous.add(str(column.name or ""))
    return ambiguous


def _time_scaffold_cte_names(statement: exp.Expression) -> set[str]:
    """识别用于日期/小时/周骨架的 CTE，供事实表连接粒度校验使用。"""
    known_names = {
        "calendar",
        "date_series",
        "dates",
        "day_series",
        "hour_series",
        "hours",
        "time_series",
        "week_series",
        "weeks",
        "month_series",
        "months",
        "spine",
    }
    names: set[str] = set()
    for cte in statement.find_all(exp.CTE):
        name = str(cte.alias_or_name or "").strip('"\x60[]').lower()
        if not name:
            continue
        if name in known_names:
            names.add(name)
            continue
        select = cte.this.find(exp.Select)
        if select is None:
            continue
        has_time_expression = any(
            isinstance(node, (exp.DateAdd, exp.DateSub, exp.TimeToStr))
            for node in select.walk()
        )
        has_cross_join = any(
            str(join.args.get("kind") or "").upper() == "CROSS"
            for join in select.args.get("joins") or []
        )
        if has_time_expression and has_cross_join:
            names.add(name)
    return names


def _is_recursive_time_scaffold(cte: exp.CTE) -> bool:
    """识别 MySQL/AnalyticDB 中应优先使用非递归实现的时间骨架。"""
    alias = str(cte.alias_or_name or "").strip('"\x60[]').lower()
    if not alias:
        return False
    known_names = {
        "calendar",
        "date_series",
        "date_seq",
        "dates",
        "day_series",
        "hour_series",
        "hours",
        "time_series",
        "week_series",
        "weeks",
        "month_series",
        "months",
        "spine",
    }
    if alias in known_names:
        return True
    if not any(marker in alias for marker in ("date", "day", "hour", "week", "month", "time", "series", "spine")):
        return False
    return any(isinstance(node, (exp.DateAdd, exp.DateSub, exp.TimeToStr)) for node in cte.this.walk())


def _has_range_predicate(expression: exp.Expression | None) -> bool:
    if expression is None:
        return False
    return any(
        expression.find(predicate) is not None
        for predicate in (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)
    )


def _raw_fact_scaffold_joins(statement: exp.Expression) -> bool:
    """禁止物理事实表直接按范围连接时间骨架，避免明细重复匹配和超时。"""
    scaffold_names = _time_scaffold_cte_names(statement)
    if not scaffold_names:
        return False
    cte_names = {
        str(cte.alias_or_name or "").strip('"\x60[]').lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    for select in statement.find_all(exp.Select):
        from_clause = select.args.get("from_")
        raw_sources = []
        if from_clause is not None and isinstance(from_clause.this, exp.Table):
            source_name = str(from_clause.this.name or "").strip('"\x60[]').lower()
            if source_name and source_name not in cte_names:
                raw_sources.append(from_clause.this)
        for join in select.args.get("joins") or []:
            target = join.this
            if not isinstance(target, exp.Table):
                continue
            target_name = str(target.name or "").strip('"\x60[]').lower()
            if target_name not in scaffold_names or not _has_range_predicate(join.args.get("on")):
                continue
            if raw_sources:
                return True
    return False


def _join_correlated_subquery_columns(statement: exp.Expression) -> set[str]:
    """识别 JOIN 条件或 JOIN 来源中引用外层查询列的子查询。"""
    correlated_columns: set[str] = set()
    for scope in traverse_scope(statement):
        if not scope.is_subquery or not scope.external_columns:
            continue
        node = scope.expression.parent
        while node is not None and not isinstance(node, exp.Select):
            if isinstance(node, exp.Join):
                correlated_columns.update(
                    column.sql(dialect="mysql", normalize=True, pretty=False)
                    for column in scope.external_columns
                )
                break
            node = node.parent
    return correlated_columns


def validate_mysql_compatible_sql(sql: str) -> None:
    """在执行前拦截 AnalyticDB/MySQL 兼容源中可确定的方言和结构错误。"""
    source_sql = str(sql or "")
    try:
        statements = sqlglot.parse(_normalized_sql_for_structure_validation(source_sql), read="mysql")
    except SqlStructureValidationError:
        raise
    except (ParseError, TokenError, AttributeError) as error:
        raise SqlStructureValidationError(
            "SQL 未通过 MySQL/AnalyticDB 结构解析；请检查标点、引号、函数参数和查询块别名，"
            "并只返回修复后的完整 SQL。"
        ) from error

    for statement in statements:
        for cte in statement.find_all(exp.CTE):
            alias = str(cte.alias_or_name or "").strip('"\x60[]').lower()
            if not alias:
                continue
            self_referencing = any(
                str(table.name or "").strip('"\x60[]').lower() == alias
                and not table.db
                and not table.catalog
                for table in cte.this.find_all(exp.Table)
            )
            if not self_referencing:
                continue
            if _is_recursive_time_scaffold(cte):
                raise SqlStructureValidationError(
                    "MySQL/AnalyticDB 日期时间骨架默认禁止 WITH RECURSIVE；"
                    "请改用非递归数字序列、日期维表或其他已验证的时间骨架。"
                )
            with_clause = cte.parent if isinstance(cte.parent, exp.With) else None
            alias_expression = cte.args.get("alias")
            columns = alias_expression.args.get("columns") if alias_expression is not None else None
            if with_clause is None or not with_clause.args.get("recursive") or not columns:
                raise SqlStructureValidationError(
                    "自引用 CTE 必须使用 WITH RECURSIVE，并在 CTE 名后显式声明列别名；"
                    "也可改用非递归日期/数字序列。"
                )

        if _raw_fact_scaffold_joins(statement):
            raise SqlStructureValidationError(
                "时间骨架不得直接按范围 JOIN 物理事实表；请先在事实 CTE 中使用明确日期范围过滤，"
                "按目标时间粒度聚合后，再将聚合结果 LEFT JOIN 到日期/小时/周骨架。"
            )

        correlated_columns = _join_correlated_subquery_columns(statement)
        if correlated_columns:
            names = "、".join(sorted(correlated_columns))
            raise SqlStructureValidationError(
                f"MySQL/AnalyticDB 的 JOIN 条件不能使用引用外层列的关联子查询（{names}）；"
                "请先把子查询按连接粒度聚合为 CTE 或派生表，再使用显式 JOIN 连接。"
            )

        for date_expression in statement.find_all((exp.DateAdd, exp.DateSub)):
            unit = str(getattr(date_expression.args.get("unit"), "this", "") or "").upper()
            interval_value = date_expression.args.get("expression")
            while isinstance(interval_value, exp.Paren):
                interval_value = interval_value.this
            if unit == "WEEK" and not isinstance(interval_value, exp.Literal):
                raise SqlStructureValidationError(
                    "AnalyticDB 不支持 INTERVAL <列或表达式> WEEK；"
                    "请改用已验证的动态 DAY 间隔，例如 INTERVAL (week_offset * 7) DAY，"
                    "或使用固定周边界。"
                )

        if any(
            literal.is_string
            and re.search(r"%(?:v|x)", str(literal.this), re.IGNORECASE)
            for literal in statement.find_all(exp.Literal)
        ):
            raise SqlStructureValidationError(
                "MySQL/AnalyticDB 兼容数据源不能假定支持 %v 或 %x 周格式；"
                "请使用已验证的周起止日期表达式，不要把 YEARWEEK 再按该格式反解析。"
            )

        ambiguous_columns = _ambiguous_unqualified_columns(statement)
        if ambiguous_columns:
            names = "、".join(sorted(ambiguous_columns))
            raise SqlStructureValidationError(
                f"JOIN 来源存在同名输出列（{names}），最终 SELECT、GROUP BY、ORDER BY "
                "和连接条件必须使用来源别名限定字段。"
            )


def validate_sql_for_datasource(sql: str, datasource_type: Any) -> None:
    """对生成、模板渲染和最终执行 SQL 使用同一套数据源方言校验。"""
    if str(datasource_type or "").strip().lower() not in {"mysql", "doris", "starrocks"}:
        return
    validate_mysql_compatible_sql(sql)
    validate_mysql_date_format_grouping(sql)


def validate_sql_for_generation(sql: str, datasource_type: Any) -> None:
    """校验 AI 生成 SQL 的方言约束；生成阶段统一避免兼容引擎不支持的 UNSIGNED。"""
    validate_sql_for_datasource(sql, datasource_type)
    if str(datasource_type or "").strip().lower() not in {"mysql", "mariadb", "analyticdb", "doris", "starrocks"}:
        return
    tokens = sqlglot.Tokenizer(dialect="mysql").tokenize(str(sql or ""))
    for index, token in enumerate(tokens):
        if token.text.lower() == "unsigned" and index > 0 and tokens[index - 1].text.lower() == "as":
            raise SqlStructureValidationError(
                "生成 SQL 禁止使用 CAST(... AS UNSIGNED)；请统一改用 CAST(... AS SIGNED)。"
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
    if any(isinstance(item, SqlStructureValidationError) for item in _walk_error_chain(error)):
        return SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
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
                "具备时间字段的图表（包括 metric）必须返回完整 date_filter，SQL 日期边界必须使用与 "
                "date_parameter_type 匹配的看板日期 token；yyyymmdd_number 使用 "
                "{{dashboard_start_yyyymmdd}} 和 {{dashboard_end_yyyymmdd}}。"
            ),
            (
                "同一次响应必须返回 time_scope（explicit/unspecified）和具体 time_range.start_date/end_date；"
                "日期格式必须为 YYYY-MM-DD。相对时间也必须直接换算为具体日期，不得只返回 unit/offset。"
            ),
            (
                "time_range 必须与 date_filter.date_expression 的静态 range 完全一致；结束日期不得晚于提示词中的系统业务日期。"
            ),
            (
                "用户完全未指定时间时，time_scope 必须为 unspecified，并返回系统业务日期之前最近 "
                "7 个完整自然日（不含系统业务日期）的具体日期；date_expression 必须使用与 time_range "
                "一致的静态 range，不得返回动态 preset、不得省略日期过滤或查询全历史。"
            ),
            (
                "近/最近/过去 N 天均截止系统业务日期前一天；本周、本月只能截止系统业务日期，"
                "不得补到未来周日或未来月末；上周、上月使用完整自然周或自然月。"
            ),
            (
                "非汇总实时问题的未指定日期范围必须使用系统业务日当天的具体日期，不能套用默认七天；"
                "实时汇总 metric 涉及日期语义，仍必须返回 date_filter 并使用 dashboard token。"
            ),
            (
                "SQL 不得保留 date_filter 边界的具体日期字面量，必须使用成对 dashboard token；"
                "单日范围也使用起止 token，并在返回前核对 SQL、time_range、date_expression 三者一致。"
            ),
            (
                "metric 只要涉及日期字段或日期条件，就必须使用日期 token 和完整 date_filter；只有完全无日期语义的全量累计指标才省略 date_filter。"
            ),
            (
                "date_filter 存在时不得使用 CURDATE、CURRENT_DATE、NOW、CURRENT_TIMESTAMP、"
                "LOCALTIME、LOCALTIMESTAMP、GETDATE 或 GETUTCDATE。"
            ),
            (
                "date_expression 必须严格使用 version=1、mode=range，start/end 均使用 "
                "mode=static 和 YYYY-MM-DD 日期；不得返回 preset 或动态 offset。"
            ),
        ]
        if "realtime_requires_hourly_time_series" in context.error_message:
            payload["repair_requirements"].append(
                "用户明确要求按小时或时间趋势但上一版返回了 metric；必须返回按 event_realtime.time "
                "分组的非 metric 小时序列，并提供完整 date_filter。"
            )
    if context.reason is SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT:
        dialect_text = f"{context.dialect} {context.error_message}".lower()
        payload["repair_requirements"] = [
            "当前 SQL 必须在目标数据源方言下可解析并执行；只返回修复后的完整 SQL JSON。",
            "MySQL/AnalyticDB 兼容数据源默认禁止 WITH RECURSIVE；日期序列优先使用目标方言支持的非递归序列。只有能力元数据明确声明且已有执行样例验证支持递归时才可例外使用，并在自引用 CTE 名后写完整列清单 cte(col1, ...)。",
            "AnalyticDB 不支持 INTERVAL <列或表达式> WEEK；改用固定周边界或 INTERVAL (week_offset * 7) DAY。",
            "时间骨架不得直接按范围 JOIN 物理事实表；先按明确日期范围过滤事实表并按目标粒度聚合，再 LEFT JOIN 时间骨架。",
            "JOIN 后的同名字段在 SELECT、GROUP BY、ORDER BY、HAVING 和连接条件中必须限定来源别名。",
            "周格式不要依赖 %v 或 %x；使用已验证的周起止日期表达式。",
        ]
        if any(name in dialect_text for name in ("mysql", "mariadb", "doris", "starrocks", "analyticdb")):
            payload["repair_requirements"].insert(
                1,
                "生成 SQL 时统一使用 CAST(... AS SIGNED)；禁止生成 CAST(... AS UNSIGNED) 或 AS UNSIGNED。",
            )
        if "correlated subquery" in dialect_text or "关联子查询" in dialect_text:
            payload["repair_requirements"].extend([
                "目标数据源不支持上一版 JOIN 条件中的关联子查询；禁止在 JOIN ON 中使用引用外层列的 EXISTS、IN 或标量子查询。",
                "先把子查询按连接键和目标粒度聚合为 CTE 或派生表，再使用显式 JOIN；连接前后都要保持原有主体、日期和分组粒度。",
            ])
        if "unsigned" in str(context.error_message or "").lower():
            payload["repair_requirements"].insert(
                1,
                "目标数据库已在执行错误中拒绝当前 UNSIGNED 用法；请根据错误信息改用该引擎支持的 SIGNED、DECIMAL 或无需转换的表达式。",
            )
        if "当前 schema 中不存在" in dialect_text or "无法解析的字段" in dialect_text:
            payload["repair_requirements"].extend([
                "上一版 SQL 引用了当前 Schema 中不存在或无法解析的表/字段；必须根据当前 Schema 和 Data Skill 重新生成完整 SQL。",
                "只能使用当前 Schema 明确提供的表和字段；不得把无效字段静默替换为第一个字段、无关字段或仅名称相似的字段。",
            ])
        recursive_alias_error = (
            "missing column aliases in recursive with query" in dialect_text
            or "missing column alias in recursive with query" in dialect_text
            or ("recursive with query" in dialect_text and "alias" in dialect_text)
            or "日期时间骨架默认禁止 with recursive" in dialect_text
        )
        if recursive_alias_error:
            payload["repair_requirements"].extend([
                "目标数据源已经明确拒绝上一版递归 CTE；本次修复禁止使用 WITH RECURSIVE、递归自引用 CTE 或仅补充 CTE 列别名后重试。",
                "日期、小时或周序列必须改用非递归数字序列、日期维表或当前数据源已验证的其他时间骨架；保留完整起止边界和补零结构。",
            ])
        elif "recursive" in dialect_text or "date_series" in dialect_text:
            payload["repair_requirements"].append(
                "完整日期补零必须保留日期骨架，并对日期与维度做 CROSS JOIN，再 LEFT JOIN 聚合结果并 COALESCE 数值；"
                "不得把日期 CTE 当作物理表。"
            )
    if (
        context.reason is SqlRepairReason.DATA_SKILL_VALIDATION
        and any(term in context.error_message for term in ("连续日期", "补齐", "日期序列", "补零"))
    ):
        payload["repair_requirements"] = [
            "必须先生成覆盖完整起止边界的日期序列；有维度时先构造日期与维度的 CROSS JOIN 骨架。",
            "事实聚合结果使用 LEFT JOIN 回填到骨架，并对数值指标使用 COALESCE(..., 0)，不能只返回事实表中有数据的日期。",
            "优先使用非递归日期序列；只有自引用 CTE 才使用 WITH RECURSIVE，并为该 CTE 写完整列清单，普通 CTE 保持普通别名即可。",
            "事实表必须先在自己的 CTE 中按日期范围过滤并按目标粒度聚合，不得直接按范围 JOIN 日期/小时/周骨架。",
        ]
    if (
        context.reason is SqlRepairReason.DATA_SKILL_VALIDATION
        and any(term in context.error_message for term in ("历史按小时", "完整 24 小时"))
    ):
        payload["repair_requirements"] = [
            "历史完整日按小时查询必须生成固定 00:00 到 23:00 的 24 小时骨架，不得使用事实 MAX(time) 截断小时范围。",
            "事实表必须先按看板日期、事件、产品和权限范围过滤并按小时聚合，再 LEFT JOIN 小时骨架。",
            "所有缺失小时使用 COALESCE(..., 0) 补零；即使历史日完全没有事实，也必须保留 24 个小时。",
        ]
    elif (
        context.reason is SqlRepairReason.DATA_SKILL_VALIDATION
        and any(term in context.error_message for term in ("实时", "小时"))
    ):
        payload["repair_requirements"] = [
            "仅当天实时小时趋势允许取事实 MAX(time)；必须使用与指标聚合相同的日期、事件、产品和权限过滤，禁止全表取最大时间。",
            "小时序列必须从 00:00 开始；有其他分组维度时先构造小时序列 CROSS JOIN 维度集合，再 LEFT JOIN 小时聚合结果。",
            "小时序列和小时聚合必须使用相同日期范围，数值指标使用 COALESCE(..., 0)，不得使用 NOW、CURRENT_DATE 或固定 00-23 全日序列替代事实最大时间。",
        ]
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "上一版 SQL 未通过校验或执行，请根据下方修复上下文重写完整 SQL JSON。\n"
        "只修复上下文指出的问题，继续遵守当前数据源、权限和 Data Skills 约束，"
        "不得编造表、字段或业务口径。\n"
        "请仅返回完整 SQL JSON，不要返回解释、Markdown 或局部 SQL。\n"
        f"```json\n{serialized}\n```"
    )
