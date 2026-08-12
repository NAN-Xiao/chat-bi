from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, traverse_scope

from apps.analysis_assistant.service.analysis_time_policy import AnalysisTimePolicy


class AnalysisTimeSqlError(ValueError):
    def __init__(self) -> None:
        super().__init__("时间边界校验未通过，当前分析角度未执行。")


@dataclass(frozen=True, eq=False)
class TimeFieldBinding:
    """工作空间已验证的时间字段及其物理编码。"""

    field: str
    data_type: str = "date"
    encoding: Literal[
        "native_date",
        "native_timestamp",
        "iso_date",
        "yyyymmdd_text",
        "yyyymmdd_integer",
        "epoch_seconds",
        "epoch_milliseconds",
    ] = "native_date"
    quoted: bool = False

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.field == other
        if not isinstance(other, TimeFieldBinding):
            return NotImplemented
        return (
            self.field,
            self.data_type,
            self.encoding,
            self.quoted,
        ) == (
            other.field,
            other.data_type,
            other.encoding,
            other.quoted,
        )

    def __hash__(self) -> int:
        return hash((self.field, self.data_type, self.encoding, self.quoted))


@dataclass(frozen=True)
class _SchemaEntry:
    key: tuple[str, ...]
    fields: tuple[TimeFieldBinding, ...]


@dataclass(frozen=True)
class _Scan:
    table_key: tuple[str, ...]
    schema_entry: _SchemaEntry
    alias: str
    qualifier: exp.Identifier
    select: exp.Select


@dataclass(frozen=True)
class _Binding:
    table_key: tuple[str, ...]
    time_field: TimeFieldBinding
    alias: str
    qualifier: exp.Identifier
    select: exp.Select
    start_offset_days: int = 0
    end_offset_days: int = 0

    @property
    def field(self) -> str:
        return self.time_field.field


@dataclass(frozen=True)
class _Coverage:
    has_lower: bool = False
    has_upper: bool = False
    invalid: bool = False


@dataclass(frozen=True)
class _DeclaredField:
    table_key: tuple[str, ...]
    field: str
    alias: str | None = None
    start_offset_days: int = 0
    end_offset_days: int = 0


_ORDERED_COMPARISONS = (exp.GT, exp.GTE, exp.LT, exp.LTE)
_TIME_COMPARISONS = (*_ORDERED_COMPARISONS, exp.EQ, exp.NEQ)
MAX_ANALYSIS_SCAN_WINDOW_OFFSET_DAYS = 3660


def _table_key(table: exp.Table) -> tuple[str, ...]:
    return tuple(
        part.lower()
        for part in (table.catalog, table.db, table.name)
        if part
    )


def _table_qualifier(table: exp.Table) -> exp.Identifier:
    alias = table.args.get("alias")
    if isinstance(alias, exp.TableAlias) and isinstance(alias.this, exp.Identifier):
        return alias.this.copy()
    if isinstance(table.this, exp.Identifier):
        return table.this.copy()
    raise AnalysisTimeSqlError()


def _parse_table_key(value: object, dialect: str | None) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        raise AnalysisTimeSqlError()
    try:
        table = parse_one(text, read=dialect or None, into=exp.Table)
    except (ParseError, TypeError, ValueError) as exc:
        raise AnalysisTimeSqlError() from exc
    if not isinstance(table, exp.Table):
        raise AnalysisTimeSqlError()
    return _table_key(table)


def _normalized_time_field(value: object) -> TimeFieldBinding | None:
    if isinstance(value, TimeFieldBinding):
        field = value.field.strip()
        if not field:
            return None
        return TimeFieldBinding(
            field=field,
            data_type=value.data_type.strip().lower(),
            encoding=value.encoding,
            quoted=value.quoted,
        )
    field = str(value or "").strip()
    if not field:
        return None
    quoted = len(field) >= 2 and field[0] == field[-1] and field[0] in {'"', '`'}
    if quoted:
        field = field[1:-1]
    return TimeFieldBinding(field=field.lower(), quoted=quoted)


def _normalize_fields(fields: tuple[object, ...]) -> tuple[TimeFieldBinding, ...]:
    normalized: list[TimeFieldBinding] = []
    for field in fields:
        value = _normalized_time_field(field)
        if value is not None and value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _schema_entries(
    schema_time_fields: dict[str, tuple[TimeFieldBinding | str, ...]],
    dialect: str | None,
) -> dict[tuple[str, ...], _SchemaEntry]:
    entries: dict[tuple[str, ...], _SchemaEntry] = {}
    for table, raw_fields in schema_time_fields.items():
        key = _parse_table_key(table, dialect)
        fields = _normalize_fields(raw_fields)
        existing = entries.get(key)
        if not fields or (existing is not None and existing.fields != fields):
            raise AnalysisTimeSqlError()
        entries[key] = _SchemaEntry(key=key, fields=fields)
    return entries


def _matching_schema_entry(
    table_key: tuple[str, ...], entries: dict[tuple[str, ...], _SchemaEntry]
) -> _SchemaEntry | None:
    exact = entries.get(table_key)
    if exact is not None:
        return exact
    if len(table_key) > 1:
        if any(key[-1] == table_key[-1] for key in entries):
            raise AnalysisTimeSqlError()
        return None
    basename_matches = [
        entry for key, entry in entries.items() if key[-1] == table_key[-1]
    ]
    if not basename_matches:
        return None
    if len(basename_matches) != 1:
        raise AnalysisTimeSqlError()
    return basename_matches[0]


def _declared_fields(
    declared_time_fields: object, dialect: str | None
) -> list[_DeclaredField]:
    if not isinstance(declared_time_fields, list):
        raise AnalysisTimeSqlError()
    declared: list[_DeclaredField] = []
    for item in declared_time_fields:
        if not isinstance(item, dict):
            raise AnalysisTimeSqlError()
        raw_table = item.get("table")
        raw_field = item.get("field")
        if not isinstance(raw_table, str) or not isinstance(raw_field, str):
            raise AnalysisTimeSqlError()
        key = _parse_table_key(raw_table, dialect)
        field = raw_field.strip()
        if not field:
            raise AnalysisTimeSqlError()
        raw_alias = item.get("alias")
        if raw_alias is not None and (
            not isinstance(raw_alias, str) or not raw_alias.strip()
        ):
            raise AnalysisTimeSqlError()
        alias = raw_alias.strip().casefold() if isinstance(raw_alias, str) else None
        has_start_offset = "start_offset_days" in item
        has_end_offset = "end_offset_days" in item
        if has_start_offset != has_end_offset:
            raise AnalysisTimeSqlError()
        start_offset = item.get("start_offset_days", 0)
        end_offset = item.get("end_offset_days", 0)
        if (
            isinstance(start_offset, bool)
            or isinstance(end_offset, bool)
            or not isinstance(start_offset, int)
            or not isinstance(end_offset, int)
            or abs(start_offset) > MAX_ANALYSIS_SCAN_WINDOW_OFFSET_DAYS
            or abs(end_offset) > MAX_ANALYSIS_SCAN_WINDOW_OFFSET_DAYS
            or (start_offset != 0 or end_offset != 0) and alias is None
        ):
            raise AnalysisTimeSqlError()
        value = _DeclaredField(
            table_key=key,
            field=field,
            alias=alias,
            start_offset_days=start_offset,
            end_offset_days=end_offset,
        )
        if value not in declared:
            declared.append(value)
    return declared


def _declared_key_matches_scan(
    declared_key: tuple[str, ...], scan: _Scan
) -> bool:
    return declared_key == scan.table_key or (
        len(scan.table_key) == 1
        and (
            declared_key == scan.schema_entry.key
            or declared_key == (scan.table_key[-1],)
        )
    )


def _select_scan_declaration(
    scan: _Scan,
    declared: list[_DeclaredField],
) -> tuple[TimeFieldBinding, _DeclaredField]:
    table_declarations = [
        item
        for item in declared
        if (
            _declared_key_matches_scan(item.table_key, scan)
            and (item.alias is None or item.alias == scan.alias)
        )
    ]
    alias_declarations = [item for item in table_declarations if item.alias is not None]
    matching_declared = alias_declarations or [
        item for item in table_declarations if item.alias is None
    ]
    exact = [
        field
        for field in scan.schema_entry.fields
        if (
            any(field.field == item.field for item in matching_declared)
            if field.quoted
            else any(
                field.field.casefold() == item.field.casefold()
                for item in matching_declared
            )
        )
    ]
    windows = {
        (item.start_offset_days, item.end_offset_days)
        for item in matching_declared
    }
    if len(exact) != 1 or len(windows) != 1:
        raise AnalysisTimeSqlError()
    declaration = matching_declared[0]
    if any(
        item.field.casefold() != declaration.field.casefold()
        for item in matching_declared
    ):
        raise AnalysisTimeSqlError()
    return exact[0], declaration


def _time_bearing_scans(
    tree: exp.Expression,
    schema_time_fields: dict[str, tuple[TimeFieldBinding | str, ...]],
    dialect: str | None,
) -> list[_Scan]:
    entries = _schema_entries(schema_time_fields, dialect)
    scans: list[_Scan] = []
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        scope_scans: list[_Scan] = []
        for table in scope.tables:
            qualifier = _table_qualifier(table)
            alias = qualifier.name
            if isinstance(scope.sources.get(alias), Scope):
                continue
            key = _table_key(table)
            schema_entry = _matching_schema_entry(key, entries)
            if schema_entry is None:
                continue
            scope_scans.append(
                _Scan(
                    table_key=key,
                    schema_entry=schema_entry,
                    alias=alias.lower(),
                    qualifier=qualifier,
                    select=scope.expression,
                )
            )
        aliases = [scan.alias for scan in scope_scans]
        if len(aliases) != len(set(aliases)):
            raise AnalysisTimeSqlError()
        scans.extend(scope_scans)
    return scans


def _physical_table_keys(tree: exp.Expression) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    for scope in traverse_scope(tree):
        for table in scope.tables:
            alias = _table_qualifier(table).name
            if isinstance(scope.sources.get(alias), Scope):
                continue
            keys.append(_table_key(table))
    return keys


def _matching_query_keys(
    declared_key: tuple[str, ...],
    query_keys: list[tuple[str, ...]],
) -> list[tuple[str, ...]]:
    if len(declared_key) > 1:
        exact = [key for key in query_keys if key == declared_key]
        if exact:
            return exact
        unqualified = [
            key
            for key in query_keys
            if len(key) == 1 and key[-1] == declared_key[-1]
        ]
        return unqualified if len(set(unqualified)) == 1 else []

    basename_matches = [
        key for key in query_keys if key[-1] == declared_key[-1]
    ]
    if len(set(basename_matches)) > 1:
        raise AnalysisTimeSqlError()
    return basename_matches


def _relevant_declared_fields_without_time_scans(
    declared_time_fields: object,
    query_keys: list[tuple[str, ...]],
    dialect: str | None,
) -> list[_DeclaredField]:
    if not isinstance(declared_time_fields, list):
        return []
    declared: list[_DeclaredField] = []
    for item in declared_time_fields:
        if not isinstance(item, dict):
            continue
        raw_table = item.get("table")
        raw_field = item.get("field")
        if not isinstance(raw_table, str):
            continue
        try:
            key = _parse_table_key(raw_table, dialect)
        except AnalysisTimeSqlError:
            continue
        if not _matching_query_keys(key, query_keys):
            continue
        if not isinstance(raw_field, str) or not raw_field.strip():
            raise AnalysisTimeSqlError()
        field = raw_field.strip()
        value = _DeclaredField(table_key=key, field=field)
        if value not in declared:
            declared.append(value)
    return declared


def _declared_field_matches_binding(field: str, binding: _Binding) -> bool:
    if binding.time_field.quoted:
        return field == binding.field
    return field.casefold() == binding.field.casefold()


def _validate_declared_scan_bindings(
    declared: list[_DeclaredField],
    query_keys: list[tuple[str, ...]],
    bindings: list[_Binding],
) -> None:
    for item in declared:
        matching_keys = _matching_query_keys(item.table_key, query_keys)
        if not matching_keys:
            if item.alias is not None:
                raise AnalysisTimeSqlError()
            continue
        matching_bindings = [
            binding
            for binding in bindings
            if binding.table_key in set(matching_keys)
            and (item.alias is None or binding.alias == item.alias)
        ]
        if item.alias is not None and len(matching_bindings) != 1:
            raise AnalysisTimeSqlError()
        if not matching_bindings or any(
            not _declared_field_matches_binding(item.field, binding)
            for binding in matching_bindings
        ):
            raise AnalysisTimeSqlError()


def _validate_scan_window_contract(bindings: list[_Binding]) -> None:
    offset_bindings = [
        binding
        for binding in bindings
        if binding.start_offset_days != 0 or binding.end_offset_days != 0
    ]
    if not offset_bindings:
        return
    if (
        len(bindings) < 2
        or not any(binding.start_offset_days == 0 for binding in bindings)
        or not any(binding.end_offset_days == 0 for binding in bindings)
    ):
        raise AnalysisTimeSqlError()


def _resolve_bindings(
    tree: exp.Expression,
    declared_time_fields: object,
    schema_time_fields: dict[str, tuple[TimeFieldBinding | str, ...]],
    dialect: str | None,
) -> list[_Binding]:
    query_keys = _physical_table_keys(tree)
    scans = _time_bearing_scans(tree, schema_time_fields, dialect)
    declared = (
        _declared_fields(declared_time_fields, dialect)
        if scans
        else _relevant_declared_fields_without_time_scans(
            declared_time_fields,
            query_keys,
            dialect,
        )
    )
    bindings: list[_Binding] = []
    for scan in scans:
        time_field, declaration = _select_scan_declaration(scan, declared)
        bindings.append(
            _Binding(
                table_key=scan.table_key,
                time_field=time_field,
                alias=scan.alias,
                qualifier=scan.qualifier,
                select=scan.select,
                start_offset_days=declaration.start_offset_days,
                end_offset_days=declaration.end_offset_days,
            )
        )
    _validate_declared_scan_bindings(declared, query_keys, bindings)
    _validate_scan_window_contract(bindings)
    return bindings


def sql_references_time_bearing_table(
    sql: str,
    schema_time_fields: dict[str, tuple[TimeFieldBinding | str, ...]],
    dialect: str | None,
) -> bool:
    """使用与时间边界校验相同的 AST scope 规则识别物理时间表。"""
    try:
        tree = parse_one(sql, read=dialect or None)
    except (ParseError, TypeError, ValueError) as exc:
        raise AnalysisTimeSqlError() from exc
    return bool(_time_bearing_scans(tree, schema_time_fields, dialect))


def _literal_date(node: exp.Expression) -> str | None:
    if isinstance(node, exp.Literal):
        return str(node.this)
    if (
        isinstance(node, exp.Cast)
        and isinstance(node.to, exp.DataType)
    ):
        return _literal_date(node.this)
    if isinstance(node, exp.Date):
        return _literal_date(node.this)
    return None


def _scope_bindings(binding: _Binding, bindings: list[_Binding]) -> list[_Binding]:
    return [candidate for candidate in bindings if candidate.select is binding.select]


def _column_matches(
    column: exp.Column, binding: _Binding, bindings: list[_Binding]
) -> bool:
    identifier = column.this
    if not isinstance(identifier, exp.Identifier):
        return False
    if binding.time_field.quoted:
        field_matches = bool(identifier.args.get("quoted")) and column.name == binding.field
    else:
        field_matches = column.name.lower() == binding.field.lower()
    if not field_matches:
        return False
    if column.table:
        return column.table.lower() == binding.alias
    same_field = [
        candidate
        for candidate in _scope_bindings(binding, bindings)
        if candidate.field == binding.field
    ]
    return len(same_field) == 1 and same_field[0] is binding


def _contains_binding_column(
    expression: exp.Expression, binding: _Binding, bindings: list[_Binding]
) -> bool:
    if isinstance(expression, exp.Column) and _column_matches(
        expression, binding, bindings
    ):
        return True
    return any(
        _column_matches(column, binding, bindings)
        for column in expression.find_all(exp.Column)
    )


def _is_direct_binding_column(
    expression: exp.Expression, binding: _Binding, bindings: list[_Binding]
) -> bool:
    return isinstance(expression, exp.Column) and _column_matches(
        expression, binding, bindings
    )


def _belongs_to_binding_select(node: exp.Expression, binding: _Binding) -> bool:
    return node.find_ancestor(exp.Select) is binding.select


def _is_mandatory_where_predicate(node: exp.Expression, binding: _Binding) -> bool:
    ancestor = node.parent
    found_where = False
    while ancestor is not None and ancestor is not binding.select:
        if isinstance(ancestor, exp.Where):
            found_where = True
        elif isinstance(ancestor, exp.Join):
            if ancestor.args.get("on") is None:
                return False
            side = str(ancestor.args.get("side") or "").upper()
            kind = str(ancestor.args.get("kind") or "").upper()
            return side == "" and kind in {"", "INNER"}
        elif not isinstance(ancestor, (exp.And, exp.Paren)):
            return False
        ancestor = ancestor.parent
    return ancestor is binding.select and found_where


def _binding_is_nullable_outer_join_side(binding: _Binding) -> bool:
    from_expression = binding.select.args.get("from_")
    left_aliases: set[str] = set()
    if isinstance(from_expression, exp.From):
        left_aliases = {
            table.alias_or_name.lower()
            for table in from_expression.find_all(exp.Table)
        }
    for join in binding.select.args.get("joins") or []:
        side = str(join.args.get("side") or "").upper()
        joined_aliases = {
            table.alias_or_name.lower()
            for table in join.this.find_all(exp.Table)
        }
        if isinstance(join.this, exp.Table):
            joined_aliases.add(join.this.alias_or_name.lower())
        if side in {"LEFT", "FULL"} and binding.alias in joined_aliases:
            return True
        if side in {"RIGHT", "FULL"} and binding.alias in left_aliases:
            return True
        left_aliases.update(joined_aliases)
    return False


def _reverse_comparison_type(
    node: exp.Expression,
) -> type[exp.Expression] | None:
    reverse: dict[type[exp.Expression], type[exp.Expression]] = {
        exp.EQ: exp.EQ,
        exp.GT: exp.LT,
        exp.GTE: exp.LTE,
        exp.LT: exp.GT,
        exp.LTE: exp.GTE,
    }
    return reverse.get(type(node))


def _effective_bounds(
    binding: _Binding,
    policy: AnalysisTimePolicy,
) -> tuple[type[exp.Expression], date, type[exp.Expression], date]:
    try:
        logical_start = policy.start_date + timedelta(days=binding.start_offset_days)
        logical_end = policy.end_date + timedelta(days=binding.end_offset_days)
    except OverflowError as exc:
        raise AnalysisTimeSqlError() from exc
    if logical_start > logical_end:
        raise AnalysisTimeSqlError()
    if binding.time_field.encoding in {
        "native_timestamp",
        "epoch_seconds",
        "epoch_milliseconds",
    }:
        start = logical_start + timedelta(days=not policy.start_inclusive)
        return exp.GTE, start, exp.LT, logical_end + timedelta(days=1)
    lower_type = exp.GTE if policy.start_inclusive else exp.GT
    upper_type = exp.LTE if policy.end_inclusive else exp.LT
    return lower_type, logical_start, upper_type, logical_end


def _boundary_value(binding: _Binding, value: date) -> str:
    encoding = binding.time_field.encoding
    if encoding == "native_timestamp":
        return datetime.combine(value, time.min).isoformat(sep=" ")
    if encoding in {"yyyymmdd_text", "yyyymmdd_integer"}:
        return value.strftime("%Y%m%d")
    if encoding in {"epoch_seconds", "epoch_milliseconds"}:
        seconds = int(
            datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp()
        )
        return str(seconds * (1000 if encoding == "epoch_milliseconds" else 1))
    return value.isoformat()


def _static_boundary_value(
    node: exp.Expression,
    binding: _Binding,
) -> str | None:
    """把 MySQL 静态时间函数还原为当前字段编码对应的边界值。"""
    literal = _literal_date(node)
    if literal is not None:
        return literal

    encoding = binding.time_field.encoding
    expression = node
    if encoding == "epoch_milliseconds":
        if not isinstance(node, exp.Mul):
            return None
        if _literal_date(node.expression) == "1000":
            expression = node.this
        elif _literal_date(node.this) == "1000":
            expression = node.expression
        else:
            return None
    elif encoding != "epoch_seconds":
        return None

    if not (
        isinstance(expression, exp.Anonymous)
        and str(expression.this).upper() == "UNIX_TIMESTAMP"
        and len(expression.expressions) == 1
    ):
        return None
    datetime_text = _literal_date(expression.expressions[0])
    if datetime_text is None:
        return None
    try:
        boundary_datetime = datetime.fromisoformat(datetime_text)
    except ValueError:
        return None
    if boundary_datetime.time() != time.min:
        return None
    return _boundary_value(binding, boundary_datetime.date())


def _expected_comparison(
    comparison_type: type[exp.Expression],
    value: str | None,
    policy: AnalysisTimePolicy,
    binding: _Binding,
) -> tuple[bool, bool] | None:
    lower_type, lower_date, upper_type, upper_date = _effective_bounds(binding, policy)
    if (
        comparison_type is exp.EQ
        and lower_type is exp.GTE
        and upper_type is exp.LTE
        and lower_date == upper_date
        and value == _boundary_value(binding, lower_date)
    ):
        return True, True
    if comparison_type is lower_type and value == _boundary_value(binding, lower_date):
        return True, False
    if comparison_type is upper_type and value == _boundary_value(binding, upper_date):
        return False, True
    return None


def _is_inner_join_predicate(node: exp.Expression, binding: _Binding) -> bool:
    """判断谓词是否是当前扫描所在 SELECT 的强制 INNER JOIN 条件。"""
    ancestor = node.parent
    while ancestor is not None and ancestor is not binding.select:
        if isinstance(ancestor, exp.Join):
            if ancestor.args.get("on") is None:
                return False
            side = str(ancestor.args.get("side") or "").upper()
            kind = str(ancestor.args.get("kind") or "").upper()
            return side == "" and kind in {"", "INNER"}
        ancestor = ancestor.parent
    return False


def _is_lifecycle_inner_join_predicate(
    node: exp.Expression,
    binding: _Binding,
    bindings: list[_Binding],
) -> bool:
    if not _is_inner_join_predicate(node, binding):
        return False
    return any(
        candidate is not binding
        and candidate.select is binding.select
        and _contains_binding_column(node, candidate, bindings)
        for candidate in bindings
    )


def _is_select_projection_calculation(
    node: exp.Expression, binding: _Binding
) -> bool:
    """判断派生时间比较是否只用于当前 SELECT 的结果计算。"""
    projection = node
    while projection.parent is not None and projection.parent is not binding.select:
        projection = projection.parent
    return (
        projection.parent is binding.select
        and projection in binding.select.expressions
    )


def _comparison_coverage(
    node: exp.Expression,
    binding: _Binding,
    bindings: list[_Binding],
    policy: AnalysisTimePolicy,
) -> _Coverage | None:
    left_contains = _contains_binding_column(node.this, binding, bindings)
    right_contains = _contains_binding_column(node.expression, binding, bindings)
    if not left_contains and not right_contains:
        return None

    left_direct = _is_direct_binding_column(node.this, binding, bindings)
    right_direct = _is_direct_binding_column(node.expression, binding, bindings)
    if not left_direct and not right_direct:
        # 留存等指标会在 SELECT/CASE 中比较 DATEDIFF、DATE_ADD 等派生时间值。
        # 只有结果计算或 INNER JOIN 生命周期关联不决定物理扫描范围；
        # WHERE/HAVING 等过滤语境中的派生时间条件仍必须失败关闭。
        if _is_select_projection_calculation(
            node, binding
        ) or _is_lifecycle_inner_join_predicate(node, binding, bindings):
            return None
        return _Coverage(invalid=True)
    if (
        left_direct == right_direct
        or not _is_mandatory_where_predicate(node, binding)
    ):
        return _Coverage(invalid=True)

    if left_direct:
        comparison_type = type(node)
        boundary = node.expression
    else:
        comparison_type = _reverse_comparison_type(node)
        boundary = node.this
    if comparison_type is None:
        return _Coverage(invalid=True)
    boundary_value = _static_boundary_value(boundary, binding)
    if boundary_value is None and _is_lifecycle_inner_join_predicate(
        node, binding, bindings
    ):
        # 表间生命周期关联（例如 active.dt = cohort.dt + N）不是范围条件。
        # 当前扫描仍会在后续 coverage 检查中要求独立的固定上下界。
        return None
    expected = _expected_comparison(
        comparison_type, boundary_value, policy, binding
    )
    if expected is None:
        return _Coverage(invalid=True)
    return _Coverage(
        has_lower=expected[0],
        has_upper=expected[1],
    )


def _between_coverage(
    node: exp.Between,
    binding: _Binding,
    bindings: list[_Binding],
    policy: AnalysisTimePolicy,
) -> _Coverage | None:
    contains = _contains_binding_column(node.this, binding, bindings)
    if not contains:
        return None
    direct_and_mandatory = (
        _is_direct_binding_column(node.this, binding, bindings)
        and _is_mandatory_where_predicate(node, binding)
        and not node.args.get("symmetric")
    )
    low = _static_boundary_value(node.args["low"], binding)
    high = _static_boundary_value(node.args["high"], binding)
    lower_type, lower_date, upper_type, upper_date = _effective_bounds(binding, policy)
    exact_lower = (
        direct_and_mandatory
        and lower_type is exp.GTE
        and low == _boundary_value(binding, lower_date)
    )
    exact_upper = (
        direct_and_mandatory
        and upper_type is exp.LTE
        and high == _boundary_value(binding, upper_date)
    )
    return _Coverage(
        has_lower=exact_lower,
        has_upper=exact_upper,
        invalid=not (exact_lower and exact_upper),
    )


def _binding_coverage(
    binding: _Binding,
    bindings: list[_Binding],
    policy: AnalysisTimePolicy,
) -> _Coverage:
    has_lower = False
    has_upper = False
    invalid = False
    for node in binding.select.walk():
        if node is not binding.select and not _belongs_to_binding_select(node, binding):
            continue
        coverage: _Coverage | None = None
        if isinstance(node, _TIME_COMPARISONS):
            coverage = _comparison_coverage(node, binding, bindings, policy)
        elif isinstance(node, exp.Between):
            coverage = _between_coverage(node, binding, bindings, policy)
        if coverage is not None:
            has_lower = has_lower or coverage.has_lower
            has_upper = has_upper or coverage.has_upper
            invalid = invalid or coverage.invalid
    return _Coverage(
        has_lower=has_lower,
        has_upper=has_upper,
        invalid=invalid,
    )


def _boundary_literal(
    binding: _Binding,
    value: date,
    dialect: str | None,
) -> exp.Expression:
    encoded = _boundary_value(binding, value)
    encoding = binding.time_field.encoding
    if encoding in {"yyyymmdd_integer", "epoch_seconds", "epoch_milliseconds"}:
        return exp.Literal.number(encoded)
    if encoding in {"iso_date", "yyyymmdd_text"} or dialect == "sqlite":
        return exp.Literal.string(encoded)
    target_type = "timestamp" if encoding == "native_timestamp" else "date"
    return exp.Cast(
        this=exp.Literal.string(encoded),
        to=exp.DataType.build(target_type),
    )


def _append_bounds(
    binding: _Binding,
    policy: AnalysisTimePolicy,
    *,
    add_lower: bool,
    add_upper: bool,
    dialect: str | None,
) -> None:
    predicates: list[exp.Expression] = []
    column = exp.Column(
        this=exp.Identifier(
            this=binding.field,
            quoted=binding.time_field.quoted,
        ),
        table=binding.qualifier.copy(),
    )
    lower_type, lower_date, upper_type, upper_date = _effective_bounds(binding, policy)
    if add_lower:
        predicates.append(
            lower_type(
                this=column.copy(),
                expression=_boundary_literal(binding, lower_date, dialect),
            )
        )
    if add_upper:
        predicates.append(
            upper_type(
                this=column.copy(),
                expression=_boundary_literal(binding, upper_date, dialect),
            )
        )
    if not predicates:
        return
    predicate = predicates[0]
    for extra in predicates[1:]:
        predicate = exp.and_(predicate, extra)
    binding.select.where(predicate, append=True, copy=False)


def enforce_analysis_time_sql(
    sql: str,
    *,
    policy: AnalysisTimePolicy,
    declared_time_fields: list[dict[str, Any]],
    schema_time_fields: dict[str, tuple[TimeFieldBinding | str, ...]],
    dialect: str | None,
    allow_rewrite: bool,
) -> str:
    try:
        tree = parse_one(sql, read=dialect or None)
    except (ParseError, TypeError, ValueError) as exc:
        raise AnalysisTimeSqlError() from exc

    bindings = _resolve_bindings(
        tree,
        declared_time_fields,
        schema_time_fields,
        dialect,
    )
    if not bindings:
        return tree.sql(dialect=dialect or None)

    missing: list[tuple[_Binding, _Coverage]] = []
    for binding in bindings:
        coverage = _binding_coverage(binding, bindings, policy)
        if coverage.invalid:
            raise AnalysisTimeSqlError()
        if not (coverage.has_lower and coverage.has_upper):
            missing.append((binding, coverage))

    if not missing:
        return tree.sql(dialect=dialect or None)
    if not allow_rewrite or len(missing) != 1:
        raise AnalysisTimeSqlError()
    binding, coverage = missing[0]
    if _binding_is_nullable_outer_join_side(binding):
        raise AnalysisTimeSqlError()
    _append_bounds(
        binding,
        policy,
        add_lower=not coverage.has_lower,
        add_upper=not coverage.has_upper,
        dialect=dialect,
    )
    return tree.sql(dialect=dialect or None)
