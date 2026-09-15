from __future__ import annotations

import re
from datetime import datetime

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from common.error import SingleMessageError


class SqlDateConversionError(SingleMessageError):
    pass


_MYSQL_TYPES = {'mysql', 'mariadb', 'analyticdb', 'doris', 'starrocks'}
_DATE_FORMATS = {'%Y%m%d', '%Y-%m-%d'}


def _literal_format(value: str) -> str | None:
    for pattern, date_format in ((r'\d{8}', '%Y%m%d'), (r'\d{4}-\d{2}-\d{2}', '%Y-%m-%d')):
        if re.fullmatch(pattern, value):
            try:
                datetime.strptime(value, date_format)
            except ValueError:
                return None
            return date_format
    return None


def _date_outputs(sql: str, field_encodings: dict[tuple[str, str], str]):
    normalized = re.sub(r'\{\{[^{}]+\}\}', 'NULL', sql)
    for statement in sqlglot.parse(normalized, read='mysql'):
        outputs: dict[int, dict[str, str | None]] = {}
        for scope in traverse_scope(statement):
            def resolve(expression: exp.Expression | None) -> str | None:
                if isinstance(expression, (exp.Alias, exp.Paren)):
                    return resolve(expression.this)
                if isinstance(expression, exp.Cast):
                    target = expression.args.get('to')
                    if not isinstance(target, exp.DataType) or target.expressions:
                        return None
                    target_type = str(target.this.value).upper()
                    if target_type in {'CHAR', 'VARCHAR', 'TEXT'}:
                        value_format = resolve(expression.this)
                        return '%Y-%m-%d' if value_format == 'native_date' else value_format
                    if target_type in {'INT', 'BIGINT', 'SMALLINT', 'UBIGINT', 'UINT'}:
                        value_format = resolve(expression.this)
                        return value_format if value_format == '%Y%m%d' else None
                    if target_type == 'DATE':
                        return 'native_date'
                    if target_type in {'DATETIME', 'TIMESTAMP', 'TIMESTAMPTZ'}:
                        return 'native_timestamp'
                    return None
                if isinstance(expression, exp.TimeToStr):
                    format_node = expression.args.get('format')
                    return format_node.this if isinstance(format_node, exp.Literal) else None
                if isinstance(expression, (exp.Date, exp.TsOrDsToDate)):
                    return 'native_date'
                if isinstance(expression, (exp.StrToDate, exp.StrToTime)):
                    format_node = expression.args.get('format')
                    if not isinstance(format_node, exp.Literal):
                        return None
                    if not any(token in format_node.this for token in ('%Y', '%y', '%m', '%d', '%j')):
                        return None
                    return 'native_date' if isinstance(expression, exp.StrToDate) else 'native_timestamp'
                if isinstance(expression, exp.Literal):
                    return _literal_format(expression.this)
                if isinstance(expression, exp.Column):
                    sources = scope.selected_sources
                    if expression.table:
                        source_entry = sources.get(expression.table)
                    elif len(sources) == 1:
                        source_entry = next(iter(sources.values()))
                    else:
                        return None
                    if not source_entry:
                        return None
                    source = source_entry[1]
                    if isinstance(source, Scope):
                        return outputs.get(id(source), {}).get(expression.name)
                    if isinstance(source, exp.Table):
                        return field_encodings.get((source.name.lower(), expression.name.lower()))
                return None

            for node in scope.walk():
                if not isinstance(node, (exp.StrToDate, exp.StrToTime)):
                    continue
                actual_format = resolve(node.this)
                format_node = node.args.get('format')
                expected_format = format_node.this if isinstance(format_node, exp.Literal) else None
                if actual_format in _DATE_FORMATS and expected_format in _DATE_FORMATS and actual_format != expected_format:
                    raise SqlDateConversionError(
                        f"日期转换格式冲突：{node.this.sql(dialect='mysql')} 的输入格式为 {actual_format}，"
                        f"但 {node.sql(dialect='mysql')} 使用 {expected_format} 解析，会产生无效日期。"
                        "请区分输入解析格式与输出展示格式，修正转换表达式；保持数据源、权限、日期范围、分组粒度和指标口径。"
                    )
            if isinstance(scope.expression, exp.Select):
                projections = []
                for projection in scope.expression.expressions:
                    if projection.is_star:
                        merged_columns = any(
                            join.args.get('using') or join.method == 'NATURAL'
                            for join in scope.expression.args.get('joins') or []
                        )
                        if isinstance(projection, exp.Star) and merged_columns:
                            projections = []
                            break
                        sources = scope.selected_sources
                        selected = [sources.get(projection.table)] if isinstance(projection, exp.Column) else list(sources.values())
                        if not selected or any(not source or not isinstance(source[1], Scope) or not outputs.get(id(source[1])) for source in selected):
                            projections = []
                            break
                        for source in selected:
                            projections.extend(outputs[id(source[1])].items())
                    else:
                        projections.append((projection.alias_or_name, resolve(projection)))
                if scope.outer_columns:
                    projections = (
                        list(zip(scope.outer_columns, [value_format for _, value_format in projections]))
                        if len(scope.outer_columns) == len(projections) else []
                    )
                scope_outputs = {}
                for name, value_format in projections:
                    scope_outputs[name] = None if name in scope_outputs else value_format
                outputs[id(scope)] = scope_outputs
            elif isinstance(scope.expression, exp.SetOperation):
                branches = [outputs.get(id(branch), {}) for branch in scope.union_scopes]
                merged = {}
                if len(branches) == 2 and len(branches[0]) == len(branches[1]):
                    for (name, left_format), right_format in zip(branches[0].items(), branches[1].values()):
                        merged[name] = left_format if left_format == right_format else None
                outputs[id(scope)] = merged
        yield outputs.get(id(scope), {}) if outputs else {}


def validate_sql_date_conversions(sql: str, datasource_type: str | None, field_encodings=None) -> None:
    if str(datasource_type or '').lower() not in _MYSQL_TYPES:
        return
    list(_date_outputs(sql, field_encodings or {}))


def mysql_temporal_result_fields(sql: str, datasource_type: str | None) -> set[str]:
    if str(datasource_type or '').lower() not in _MYSQL_TYPES:
        return set()
    fields = set()
    for outputs in _date_outputs(sql, {}):
        fields.update(name for name, value_format in outputs.items() if value_format in _DATE_FORMATS | {'native_date', 'native_timestamp'})
    return fields
