"""Validate configured event measures against their actual SQL output lineage."""
from __future__ import annotations

from typing import Any, Iterator
from decimal import Decimal, InvalidOperation
import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.sql_generation_validation import _outputs, _source, _select_expression_columns


def _unquoted(node: exp.Expression) -> str:
    node = node.copy()
    for column in node.find_all(exp.Column):
        column.set("table", None)
    for identifier in node.find_all(exp.Identifier):
        identifier.set("quoted", False)
    for division in node.find_all(exp.Div):
        # Dialect flags affect SQLGlot's cross-dialect rendering, not the
        # explicit NULLIF operands we compare in the configured formula.
        division.set("safe", False)
        division.set("typed", False)
    for cast in list(node.find_all(exp.Cast)):
        if isinstance(cast.this, exp.Placeholder):
            cast.replace(cast.this)
    return node.sql(normalize=True, comments=False)


def _implies(actual: exp.Expression, expected: exp.Expression) -> bool:
    """Conservative boolean implication; do not accept a filter inside only one OR arm."""
    if isinstance(actual, (exp.Paren, exp.Where)):
        return _implies(actual.this, expected)
    if isinstance(expected, exp.Paren):
        return _implies(actual, expected.this)
    if isinstance(expected, exp.Boolean) and expected.this is True:
        return True
    if _unquoted(actual) == _unquoted(expected):
        return True
    if isinstance(actual, exp.In) and not actual.args.get("query"):
        return _implies(exp.or_(*[exp.EQ(this=actual.this.copy(), expression=value.copy()) for value in actual.expressions]), expected)
    if isinstance(expected, exp.Between):
        return (_implies(actual, exp.GTE(this=expected.this.copy(), expression=expected.args["low"].copy()))
                and _implies(actual, exp.LTE(this=expected.this.copy(), expression=expected.args["high"].copy())))
    if isinstance(actual, exp.Between) and isinstance(expected, (exp.GTE, exp.LTE)):
        bound = actual.args["low" if isinstance(expected, exp.GTE) else "high"]
        return (_unquoted(actual.this) == _unquoted(expected.this)
                and _unquoted(bound) == _unquoted(expected.expression))
    if isinstance(expected, exp.And):
        return _implies(actual, expected.this) and _implies(actual, expected.expression)
    if isinstance(actual, exp.Or):
        return _implies(actual.this, expected) and _implies(actual.expression, expected)
    if isinstance(actual, exp.And):
        return _implies(actual.this, expected) or _implies(actual.expression, expected)
    if isinstance(expected, exp.Or):
        return _implies(actual, expected.this) or _implies(actual, expected.expression)
    if isinstance(actual, exp.In) and isinstance(expected, exp.EQ):
        return (_unquoted(actual.this) == _unquoted(expected.this)
                and len(actual.expressions) == 1
                and _unquoted(actual.expressions[0]) == _unquoted(expected.expression))
    return False


def _field_expression(field: Any, dialect: str) -> exp.Expression | None:
    if not isinstance(field, dict):
        return None
    if field.get("expression"):
        return sqlglot.parse_one(field["expression"], read=dialect)
    name = field.get("field") or field.get("name")
    return exp.column(str(name), quoted=True) if name else None


def _filter_expression(filters: Any, dialect: str) -> exp.Expression | None:
    if not isinstance(filters, dict):
        return None
    children = filters.get("children") if filters.get("type") == "group" else filters.get("rules")
    if isinstance(children, list):
        parts = [_filter_expression(rule, dialect) for rule in children]
        parts = [part for part in parts if part is not None]
        if not parts:
            return None
        return (exp.or_ if filters.get("logic") == "or" else exp.and_)(*parts)
    field = _field_expression(filters.get("field"), dialect)
    if field is None:
        return None
    operator = filters.get("operator")
    value = filters.get("value")
    def literal(item):
        field_config = filters.get("field") or {}
        type_hint = str(field_config.get("type") or field_config.get("category") or "").lower()
        if isinstance(item, str) and re.search(r"\b(?:tinyint|smallint|bigint|int|integer|float|double|decimal|numeric|number)\b", type_hint):
            try:
                numeric = Decimal(item.strip())
                if not numeric.is_finite():
                    raise InvalidOperation
                return exp.Literal.number(str(numeric))
            except InvalidOperation as exc:
                raise ValueError("数值字段的筛选值必须是有效数字。") from exc
        return exp.convert(item)
    binary = {"eq": exp.EQ, "ne": exp.NEQ, "gt": exp.GT, "gte": exp.GTE, "lt": exp.LT, "lte": exp.LTE}
    if operator in binary:
        return binary[operator](this=field, expression=literal(value))
    if operator in {"in", "not_in"}:
        values = value if isinstance(value, list) else [value]
        expression = exp.In(this=field, expressions=[literal(item) for item in values])
        return exp.Not(this=expression) if operator == "not_in" else expression
    if operator in {"is_null", "is_not_null"}:
        expression = exp.Is(this=field, expression=exp.Null())
        return exp.Not(this=expression) if operator == "is_not_null" else expression
    if operator in {"between", "not_between"}:
        # The current editor's range input serializes two comma-separated values.
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",")]
        if not isinstance(value, list) or len(value) != 2 or any(item in (None, "") for item in value):
            raise ValueError("范围筛选需要两个以逗号分隔的边界值。")
        expression = exp.Between(this=field, low=literal(value[0]), high=literal(value[1]))
        return exp.Not(this=expression) if operator == "not_between" else expression
    if operator in {"contains", "not_contains", "starts_with", "ends_with"}:
        pattern = {"contains": f"%{value}%", "not_contains": f"%{value}%",
                   "starts_with": f"{value}%", "ends_with": f"%{value}"}[operator]
        expression = exp.Like(this=field, expression=exp.Literal.string(pattern))
        return exp.Not(this=expression) if operator == "not_contains" else expression
    raise ValueError(f"图表筛选操作符无法校验：{operator}。")


def _lineage(scope: Scope, expression: exp.Expression, seen=frozenset()) -> Iterator[tuple[Scope, exp.Expression]]:
    marker = (id(scope), expression.sql())
    if marker in seen:
        return
    if scope.union_scopes:
        names = list((_outputs(scope) or {}).keys())
        if expression.alias_or_name in names:
            index = names.index(expression.alias_or_name)
            # Set-operation columns are paired by ordinal in SQL itself. Trace
            # every branch, rather than treating the first projection as proof
            # of the entire dimension domain.
            for branch in scope.union_scopes:
                projections = list((_outputs(branch) or {}).values())
                if index < len(projections):
                    yield from _lineage(branch, projections[index], seen | {marker})
            return
    yield scope, expression
    for column in _select_expression_columns(expression):
        source = _source(scope, column)
        if isinstance(source, Scope):
            projected = (_outputs(source) or {}).get(column.name)
            if projected is not None:
                yield from _lineage(source, projected, seen | {marker})


def _row_predicates(scope: Scope, seen=frozenset()) -> Iterator[exp.Expression]:
    if id(scope) in seen:
        return
    where = scope.expression.args.get("where")
    if where is not None:
        yield _expanded(where.this, scope)
    for join in scope.expression.args.get("joins") or []:
        if not join.side and join.args.get("on") is not None:
            yield _expanded(join.args["on"], scope)
    for _, source in scope.selected_sources.values():
        if isinstance(source, Scope):
            yield from _row_predicates(source, seen | {id(scope)})


def _physical_tables(scope: Scope, seen=frozenset()) -> set[str]:
    if id(scope) in seen:
        return set()
    tables: set[str] = set()
    for _, source in scope.selected_sources.values():
        if isinstance(source, exp.Table):
            tables.add(source.name)
        elif isinstance(source, Scope):
            tables.update(_physical_tables(source, seen | {id(scope)}))
    return tables


def _expanded(expression: exp.Expression, scope: Scope, seen=frozenset()) -> exp.Expression:
    """Resolve projected columns while retaining aggregate row-scope identity."""
    if isinstance(expression, (exp.Alias, exp.Paren)):
        return _expanded(expression.this, scope, seen)
    if isinstance(expression, exp.Column):
        source = _source(scope, expression)
        marker = (id(source), expression.name)
        if isinstance(source, Scope) and marker not in seen:
            projection = (_outputs(source) or {}).get(expression.name)
            if projection is not None:
                return _expanded(projection, source, seen | {marker})
        return expression.copy()
    node = expression.copy()
    for key, value in expression.args.items():
        if isinstance(value, exp.Expression):
            node.set(key, _expanded(value, scope, seen))
        elif isinstance(value, list):
            node.set(key, [_expanded(item, scope, seen) if isinstance(item, exp.Expression) else item for item in value])
    if isinstance(node, exp.AggFunc):
        predicates = list(_row_predicates(scope))
        predicate = exp.and_(*predicates) if predicates else exp.true()
        return exp.Anonymous(this="aggregate_scope", expressions=[node, exp.Literal.string(_unquoted(predicate))])
    return node


def _branches(argument: exp.Expression) -> list[tuple[exp.Expression, exp.Expression]]:
    if isinstance(argument, exp.Paren):
        return _branches(argument.this)
    if isinstance(argument, exp.If):
        return [(argument.this, argument.args["true"]),
                (exp.Not(this=argument.this.copy()), argument.args.get("false") or exp.Null())]
    if isinstance(argument, exp.Case):
        branches = []
        previous = []
        for branch in argument.args.get("ifs") or []:
            condition = branch.this
            if argument.this is not None:
                condition = exp.EQ(this=argument.this.copy(), expression=condition.copy())
            branches.append((exp.and_(*previous, condition), branch.args["true"]))
            previous.append(exp.Not(this=condition.copy()))
        branches.append((exp.and_(*previous), argument.args.get("default") or exp.Null()))
        return branches
    return [(exp.true(), argument)]


def _literal_number(node: exp.Expression, value: int) -> bool:
    return isinstance(node, exp.Literal) and not node.is_string and float(node.this) == value


def _preserves_measure(expression: exp.Expression) -> bool:
    if isinstance(expression, (exp.Alias, exp.Paren)):
        return _preserves_measure(expression.this)
    if isinstance(expression, (exp.Column, exp.AggFunc)):
        return True
    if isinstance(expression, exp.Coalesce):
        return (len(expression.expressions) == 1 and _literal_number(expression.expressions[0], 0)
                and _preserves_measure(expression.this))
    return False


def _measure_issues(nodes, metric: dict, contract: dict, dialect: str) -> list[str]:
    name, aggregation = metric["alias"], metric["aggregation"]
    issues: list[str] = []
    functions = [(scope, function) for scope, expression in nodes for function in expression.find_all(exp.AggFunc)]
    if not functions:
        return [f"指标“{name}”缺少配置的 {aggregation} 聚合。"]
    for source, expression in nodes:
        # Follow wrappers through intermediate CTEs, but do not confuse a
        # configured input-field expression with a transformation of its result.
        if any(item.find(exp.AggFunc) for _, item in _lineage(source, expression)) and not _preserves_measure(expression):
            issues.append(f"指标“{name}”在聚合外使用了未配置的计算。")
    expected_field = _field_expression(metric.get("metric_field"), dialect)
    expected_type = {"count": exp.Count, "count_distinct": exp.Count, "sum": exp.Sum,
                     "avg": exp.Avg, "min": exp.Min, "max": exp.Max}.get(aggregation)
    for scope, function in functions:
        # A roll-up may sum counts/sums already computed in a source CTE.
        column = function.this if isinstance(function.this, exp.Column) else None
        source = _source(scope, column) if column is not None else None
        upstream = (_outputs(source) or {}).get(column.name) if isinstance(source, Scope) else None
        if upstream is not None and upstream.find(exp.AggFunc):
            if isinstance(function, exp.Sum) and aggregation in {"count", "sum"}:
                continue
            issues.append(f"指标“{name}”改变了已聚合结果的计算方式。")
            continue
        is_count_sum = aggregation == "count" and isinstance(function, exp.Sum)
        distinct = isinstance(function.this, exp.Distinct)
        if (not isinstance(function, expected_type) and not is_count_sum
                or aggregation != "count_distinct" and distinct or aggregation == "count_distinct" and not distinct):
            issues.append(f"指标“{name}”未按配置使用 {aggregation} 聚合。")
            continue
        argument = function.this
        if distinct:
            if len(argument.expressions) != 1:
                issues.append(f"指标“{name}”去重聚合字段与配置不一致。")
                continue
            argument = argument.expressions[0]
        row_predicates = list(_row_predicates(scope))
        conditions: list[exp.Expression] = []
        for condition, value in _branches(argument):
            if isinstance(value, exp.Null) or (is_count_sum or aggregation == "sum") and _literal_number(value, 0):
                continue
            if aggregation == "count":
                valid_value = (_literal_number(value, 1) if is_count_sum else
                               isinstance(value, (exp.Star, exp.Literal, exp.Boolean)))
            else:
                payload = _expanded(value, scope)
                while isinstance(payload, exp.Cast):
                    payload = payload.this
                valid_value = expected_field is not None and _unquoted(payload) == _unquoted(expected_field)
            if not valid_value:
                issues.append(f"指标“{name}”的聚合计算字段与配置不一致。")
            conditions.append(condition)
        if not conditions:
            issues.append(f"指标“{name}”没有按配置统计有效记录。")
        effective = exp.and_(*row_predicates, exp.or_(*conditions)) if conditions else exp.false()
        table = metric.get("table")
        if table and table not in _physical_tables(scope):
            issues.append(f"指标“{name}”未使用配置来源表 {table}。")
        time_config = contract.get("time") or {}
        tokens = contract.get("date_tokens") or []
        date_field = _field_expression(time_config.get("field"), dialect)
        if date_field is not None and tokens:
            start, end = [exp.Placeholder(this=token[2:-2]) for token in tokens]
            if time_config.get("date_parameter_type") == "timestamp":
                date_predicate = exp.and_(exp.GTE(this=date_field.copy(), expression=start), exp.LT(this=date_field.copy(), expression=end))
            else:
                date_predicate = exp.Between(this=date_field, low=start, high=end)
            if not _implies(effective, date_predicate):
                issues.append(f"指标“{name}”的事实来源缺少完整配置日期范围，必须直接限制原始时间字段。")
        fact_sources = [source for _, source in scope.selected_sources.values()
                        if isinstance(source, exp.Table) or isinstance(source, Scope) and _physical_tables(source)]
        if len(fact_sources) > 1:
            issues.append(f"指标“{name}”在多个事实来源连接后聚合，无法保证配置粒度；请先独立筛选聚合再连接。")
        field = metric.get("field") or {}
        event_field = field.get("eventNameField") or field.get("field")
        if metric.get("event") and event_field:
            expected = exp.EQ(this=exp.column(event_field, quoted=True), expression=exp.Literal.string(metric["event"]))
            if not _implies(effective, expected):
                issues.append(f"指标“{name}”未按配置事件 {metric['event']} 限定统计范围。")
        for label, filters in (("全局", contract.get("filters")), ("指标内", metric.get("filters"))):
            try:
                expected = _filter_expression(filters, dialect)
            except (ValueError, sqlglot.errors.SqlglotError) as exc:
                issues.append(str(exc))
                continue
            if expected is not None and not _implies(effective, expected):
                issues.append(f"指标“{name}”缺少或改变了{label}筛选：{expected.sql(dialect=dialect)}。")
        for group in contract.get("groups") or []:
            expected = _field_expression(group, dialect)
            group_by = scope.expression.args.get("group")
            actual_groups = group_by.expressions if group_by is not None else []
            if expected is not None and not any(_unquoted(_expanded(item, scope)) == _unquoted(expected) for item in actual_groups):
                issues.append(f"指标“{name}”未按配置分组字段 {expected.sql(dialect=dialect)} 聚合。")
    return issues


def _formula_expression(ir: dict, references: dict[str, exp.Expression]) -> exp.Expression:
    if ir.get("type") == "metric_ref":
        return references[ir["id"]].copy()
    if ir.get("type") == "number":
        return exp.Literal.number(ir["value"])
    if ir.get("type") != "binary":
        raise ValueError("公式结构无法识别")
    left = _formula_expression(ir["left"], references)
    right = _formula_expression(ir["right"], references)
    if ir["operator"] == "/":
        right = exp.Nullif(this=right, expression=exp.Literal.number(0))
    return {"+": exp.Add, "-": exp.Sub, "*": exp.Mul, "/": exp.Div}[ir["operator"]](this=left, expression=right)


def _group_domain_issues(scope: Scope, outputs: dict, contract: dict, dialect: str) -> list[str]:
    """The grouping domain is the union of the configured metric inputs.

    Reading all other events from the same authorized table would introduce
    unrelated all-zero groups and may truncate the useful result at preview.
    """
    metrics = list(contract.get("metrics") or [])
    metrics.extend(metric for formula in contract.get("formula_metrics") or [] for metric in formula.get("base_metrics") or [])
    issues = []
    checked = set()
    for group in contract.get("groups") or []:
        name = group.get("alias") or group.get("field")
        if name not in outputs:
            continue
        for source_scope, expression in _lineage(scope, outputs[name]):
            for column in _select_expression_columns(expression):
                source = _source(source_scope, column)
                if not isinstance(source, exp.Table) or (id(source_scope), source.name) in checked:
                    continue
                checked.add((id(source_scope), source.name))
                candidates = [metric for metric in metrics if metric.get("table") == source.name]
                alternatives = []
                try:
                    for metric in candidates:
                        parts = []
                        event_field = (metric.get("field") or {}).get("eventNameField") or (metric.get("field") or {}).get("field")
                        if metric.get("event") and event_field:
                            parts.append(exp.EQ(this=exp.column(event_field, quoted=True), expression=exp.Literal.string(metric["event"])))
                        for filters in (contract.get("filters"), metric.get("filters")):
                            condition = _filter_expression(filters, dialect)
                            if condition is not None:
                                parts.append(condition)
                        tokens = contract.get("date_tokens") or []
                        time = contract.get("time") or {}
                        field = _field_expression(time.get("field"), dialect)
                        if field is not None and tokens:
                            start, end = [exp.Placeholder(this=token[2:-2]) for token in tokens]
                            parts.append(exp.and_(exp.GTE(this=field.copy(), expression=start),
                                (exp.LT if time.get("date_parameter_type") == "timestamp" else exp.LTE)(this=field.copy(), expression=end)))
                        alternatives.append(exp.and_(*parts) if parts else exp.true())
                except (ValueError, sqlglot.errors.SqlglotError) as exc:
                    issues.append(str(exc))
                    continue
                predicates = list(_row_predicates(source_scope))
                actual = exp.and_(*predicates) if predicates else exp.true()
                fact_sources = [item for _, item in source_scope.selected_sources.values()
                                if isinstance(item, exp.Table) or isinstance(item, Scope) and _physical_tables(item)]
                if not alternatives or len(fact_sources) > 1 or not _implies(actual, exp.or_(*alternatives)):
                    issues.append(f"分组维度 {name} 的来源范围超出配置指标；维度集合必须来自已应用事件、日期、全局及指标筛选的指标事实，多指标取这些范围的并集，不能扫描同表其他事件的维度。")
    return issues


def event_result_contract_issues(statement: exp.Expression, contract: dict, dialect: str) -> list[str]:
    if contract.get("type") != "event_table":
        return []
    scope = build_scope(statement)
    if scope is None:
        return ["事件分析 SQL 无法确定结果列。"]
    outputs = _outputs(scope) or {}
    issues = [f"事件分析 SQL 缺少配置结果列：{name}。实际输出列为 {list(outputs)!r}，必须逐字保留配置名称及其空格。"
              for name in contract["required_columns"] if name not in outputs]
    references = {}
    for metric in contract["metrics"]:
        name = metric["alias"]
        if name not in outputs:
            continue
        nodes = list(_lineage(scope, outputs[name]))
        issues.extend(_measure_issues(nodes, metric, contract, dialect))
        references[metric["id"]] = _expanded(outputs[name], scope)
    for group in contract.get("groups") or []:
        name = group.get("alias") or group.get("field")
        expected = _field_expression(group, dialect)
        if name in outputs and expected is not None and _unquoted(_expanded(outputs[name], scope)) != _unquoted(expected):
            issues.append(f"结果分组列 {name} 未使用配置字段或表达式。")
    for formula in contract.get("formula_metrics") or []:
        if formula["alias"] not in outputs:
            continue
        expression = outputs[formula["alias"]]
        nodes = list(_lineage(scope, expression))
        for metric in formula.get("base_metrics") or []:
            if metric["id"] in references:
                continue
            candidates = [(source, item) for source, item in nodes if item.alias_or_name == metric["alias"]]
            if len(candidates) != 1:
                issues.append(f"公式“{formula['alias']}”缺少可验证的内部指标 {metric['alias']}。")
                continue
            source, item = candidates[0]
            issues.extend(_measure_issues(list(_lineage(source, item)), metric, contract, dialect))
            references[metric["id"]] = _expanded(item, source)
        try:
            expected = _formula_expression(formula["expression"], references)
            if formula.get("decimal_places") is not None:
                expected = exp.Round(this=expected, decimals=exp.Literal.number(formula["decimal_places"]))
            if _unquoted(_expanded(expression, scope)) != _unquoted(expected):
                issues.append(f"公式“{formula['alias']}”未按配置的运算、指标引用、分母保护或小数位计算。")
        except (KeyError, TypeError, ValueError):
            issues.append(f"公式“{formula['alias']}”存在无法解析的指标引用。")
    issues.extend(_group_domain_issues(scope, outputs, contract, dialect))
    return list(dict.fromkeys(issues))
