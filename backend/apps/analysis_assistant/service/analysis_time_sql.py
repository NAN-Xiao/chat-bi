from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, traverse_scope

from apps.analysis_assistant.service.analysis_time_policy import AnalysisTimePolicy


class AnalysisTimeSqlError(ValueError):
    def __init__(self) -> None:
        super().__init__("时间边界校验未通过，当前分析角度未执行。")


@dataclass(frozen=True)
class _SchemaEntry:
    key: tuple[str, ...]
    fields: tuple[str, ...]


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
    field: str
    alias: str
    qualifier: exp.Identifier
    select: exp.Select


@dataclass(frozen=True)
class _Coverage:
    has_lower: bool = False
    has_upper: bool = False
    invalid: bool = False


_ORDERED_COMPARISONS = (exp.GT, exp.GTE, exp.LT, exp.LTE)
_TIME_COMPARISONS = (*_ORDERED_COMPARISONS, exp.EQ, exp.NEQ)


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


def _normalize_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for field in fields:
        value = str(field or "").strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _schema_entries(
    schema_time_fields: dict[str, tuple[str, ...]], dialect: str | None
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
    unqualified = entries.get((table_key[-1],))
    if unqualified is None:
        return None
    qualified_same_name = any(
        len(key) > 1 and key[-1] == table_key[-1] for key in entries
    )
    if len(table_key) > 1 and qualified_same_name:
        raise AnalysisTimeSqlError()
    return unqualified


def _declared_fields(
    declared_time_fields: list[dict[str, str]], dialect: str | None
) -> list[tuple[tuple[str, ...], str]]:
    declared: list[tuple[tuple[str, ...], str]] = []
    for item in declared_time_fields:
        key = _parse_table_key(item.get("table"), dialect)
        field = str(item.get("field") or "").strip().lower()
        if not field:
            raise AnalysisTimeSqlError()
        pair = (key, field)
        if pair not in declared:
            declared.append(pair)
    return declared


def _select_field(
    table_key: tuple[str, ...],
    schema_entry: _SchemaEntry,
    declared: list[tuple[tuple[str, ...], str]],
) -> str:
    matching_declared = {
        field
        for declared_key, field in declared
        if declared_key == table_key
        or (schema_entry.key == (table_key[-1],) and declared_key == schema_entry.key)
    }
    exact = [field for field in schema_entry.fields if field in matching_declared]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1 or len(schema_entry.fields) != 1:
        raise AnalysisTimeSqlError()
    return schema_entry.fields[0]


def _resolve_bindings(
    tree: exp.Expression,
    declared_time_fields: list[dict[str, str]],
    schema_time_fields: dict[str, tuple[str, ...]],
    dialect: str | None,
) -> list[_Binding]:
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
    if not scans:
        return []
    declared = _declared_fields(declared_time_fields, dialect)
    return [
        _Binding(
            table_key=scan.table_key,
            field=_select_field(scan.table_key, scan.schema_entry, declared),
            alias=scan.alias,
            qualifier=scan.qualifier,
            select=scan.select,
        )
        for scan in scans
    ]


def _literal_date(node: exp.Expression) -> str | None:
    if isinstance(node, exp.Literal) and node.is_string:
        value = str(node.this)
        return value if len(value) == 10 else None
    if (
        isinstance(node, exp.Cast)
        and isinstance(node.to, exp.DataType)
        and node.to.this == exp.DataType.Type.DATE
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
    if column.name.lower() != binding.field:
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
        if isinstance(ancestor, (exp.Or, exp.Not)):
            return False
        if isinstance(ancestor, exp.Where):
            found_where = True
        ancestor = ancestor.parent
    return ancestor is binding.select and found_where


def _reverse_comparison_type(
    node: exp.Expression,
) -> type[exp.Expression] | None:
    reverse: dict[type[exp.Expression], type[exp.Expression]] = {
        exp.GT: exp.LT,
        exp.GTE: exp.LTE,
        exp.LT: exp.GT,
        exp.LTE: exp.GTE,
    }
    return reverse.get(type(node))


def _expected_comparison(
    comparison_type: type[exp.Expression],
    value: str | None,
    policy: AnalysisTimePolicy,
) -> tuple[bool, bool] | None:
    lower_type = exp.GTE if policy.start_inclusive else exp.GT
    upper_type = exp.LTE if policy.end_inclusive else exp.LT
    if comparison_type is lower_type and value == policy.start_date.isoformat():
        return True, False
    if comparison_type is upper_type and value == policy.end_date.isoformat():
        return False, True
    return None


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
    if (
        left_contains == right_contains
        or not _is_mandatory_where_predicate(node, binding)
    ):
        return _Coverage(invalid=True)

    if left_contains:
        if not _is_direct_binding_column(node.this, binding, bindings):
            return _Coverage(invalid=True)
        comparison_type = type(node)
        boundary = node.expression
    else:
        if not _is_direct_binding_column(node.expression, binding, bindings):
            return _Coverage(invalid=True)
        comparison_type = _reverse_comparison_type(node)
        boundary = node.this
    if comparison_type is None:
        return _Coverage(invalid=True)
    expected = _expected_comparison(
        comparison_type, _literal_date(boundary), policy
    )
    if expected is None:
        return _Coverage(invalid=True)
    return _Coverage(has_lower=expected[0], has_upper=expected[1])


def _between_coverage(
    node: exp.Between,
    binding: _Binding,
    bindings: list[_Binding],
    policy: AnalysisTimePolicy,
) -> _Coverage | None:
    contains = _contains_binding_column(node.this, binding, bindings)
    if not contains:
        return None
    valid = (
        _is_direct_binding_column(node.this, binding, bindings)
        and _is_mandatory_where_predicate(node, binding)
        and not node.args.get("symmetric")
        and policy.start_inclusive
        and policy.end_inclusive
        and _literal_date(node.args["low"]) == policy.start_date.isoformat()
        and _literal_date(node.args["high"]) == policy.end_date.isoformat()
    )
    return _Coverage(has_lower=valid, has_upper=valid, invalid=not valid)


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
    return _Coverage(has_lower=has_lower, has_upper=has_upper, invalid=invalid)


def _has_dynamic_boundary(tree: exp.Expression, bindings: list[_Binding]) -> bool:
    if any(
        isinstance(node, exp.Join)
        and str(node.args.get("kind") or "").upper() == "CROSS"
        for node in tree.walk()
    ):
        return True
    bound_fields = {binding.field for binding in bindings}
    return any(
        any(column.name.lower() in bound_fields for column in maximum.find_all(exp.Column))
        for maximum in tree.find_all(exp.Max)
    )


def _date_literal(value: str) -> exp.Cast:
    return exp.Cast(
        this=exp.Literal.string(value),
        to=exp.DataType.build("date"),
    )


def _append_bounds(
    binding: _Binding,
    policy: AnalysisTimePolicy,
    *,
    add_lower: bool,
    add_upper: bool,
) -> None:
    predicates: list[exp.Expression] = []
    column = exp.Column(
        this=exp.Identifier(this=binding.field, quoted=False),
        table=binding.qualifier.copy(),
    )
    if add_lower:
        lower_type = exp.GTE if policy.start_inclusive else exp.GT
        predicates.append(
            lower_type(
                this=column.copy(),
                expression=_date_literal(policy.start_date.isoformat()),
            )
        )
    if add_upper:
        upper_type = exp.LTE if policy.end_inclusive else exp.LT
        predicates.append(
            upper_type(
                this=column.copy(),
                expression=_date_literal(policy.end_date.isoformat()),
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
    declared_time_fields: list[dict[str, str]],
    schema_time_fields: dict[str, tuple[str, ...]],
    dialect: str | None,
    allow_rewrite: bool,
) -> str:
    try:
        tree = parse_one(sql, read=dialect or None)
    except ParseError as exc:
        raise AnalysisTimeSqlError() from exc

    bindings = _resolve_bindings(
        tree,
        declared_time_fields,
        schema_time_fields,
        dialect,
    )
    if not bindings:
        return tree.sql(dialect=dialect or None)
    if _has_dynamic_boundary(tree, bindings):
        raise AnalysisTimeSqlError()

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
    _append_bounds(
        binding,
        policy,
        add_lower=not coverage.has_lower,
        add_upper=not coverage.has_upper,
    )
    return tree.sql(dialect=dialect or None)
