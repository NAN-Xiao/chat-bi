"""Validate event aggregate grain and joins to the configured result grain."""
from __future__ import annotations

from typing import Any

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope


def event_grain_issues(statement: exp.Expression, contract: dict, dialect: str) -> list[str]:
    """Reject range totals repeated per date and missing/extra dimension keys.

    This is intentionally a structural contract: aggregate sources must expose
    the configured grain, and joins to the date/dimension scaffold must compare
    every grain key. Ambiguous rewrites require an explicit aggregate/ON shape.
    """
    if contract.get("type") != "event_table":
        return []
    # Both validators are pure. Lazy imports allow the result-contract entry
    # point to call this helper without creating an import cycle.
    from apps.dashboard.crud.event_sql_contract import (
        _expanded, _field_expression, _lineage, _outputs, _source, _unquoted,
    )
    from apps.dashboard.crud.sql_generation_validation import _select_expression_columns

    root = build_scope(statement)
    if root is None:
        return ["事件指标无法确定聚合粒度，请使用明确的 SELECT/GROUP BY 结构。"]
    outputs = _outputs(root) or {}
    time = contract.get("time") or {}
    time_field = _field_expression(time.get("field"), dialect)
    grain = str(time.get("grain") or "").lower()
    parameter_type = time.get("date_parameter_type") or time.get("dateParameterType")
    has_date = bool(contract.get("date_field"))
    groups = [(str(group.get("alias") or group.get("field") or ""), _field_expression(group, dialect))
              for group in contract.get("groups") or []]
    expected_keys = ({"date"} if has_date else set()) | {f"group:{name}" for name, _ in groups}
    issues: list[str] = []

    def unwrap(node: exp.Expression) -> exp.Expression:
        while isinstance(node, (exp.Alias, exp.Paren)):
            node = node.this
        return node

    def scaffold_date(node: exp.Expression, scope: Scope, seen=frozenset()) -> bool:
        node = unwrap(node)
        # Displaying/encoding a scaffold date does not change its grain.
        if isinstance(node, exp.Cast):
            return scaffold_date(node.this, scope, seen)
        if isinstance(node, exp.TsOrDsToTimestamp):
            return scaffold_date(node.this, scope, seen)
        if isinstance(node, exp.TimeToStr) and node.args.get("format").name in {"%Y%m%d", "%Y-%m-%d"}:
            return scaffold_date(node.this, scope, seen)
        if not isinstance(node, exp.Column):
            return False
        source = _source(scope, node)
        if not isinstance(source, Scope) or (id(source), node.name) in seen:
            return False
        parent = source.expression.parent
        if isinstance(parent, exp.CTE) and parent.alias_or_name == "dashboard_dates" and node.name == "calendar_date":
            return True
        projection = (_outputs(source) or {}).get(node.name)
        return projection is not None and scaffold_date(projection, source, seen | {(id(source), node.name)})

    def configured_time(node: exp.Expression) -> bool:
        node = unwrap(node)
        return time_field is not None and _unquoted(node) == _unquoted(time_field)

    def date_value(node: exp.Expression) -> bool:
        node = unwrap(node)
        if configured_time(node):
            return parameter_type in {"date", "yyyymmdd_number", "yyyymmdd_text"}
        if isinstance(node, exp.StrToDate) and parameter_type in {"yyyymmdd_number", "yyyymmdd_text"}:
            value = node.this
            if isinstance(value, exp.Cast):
                value = value.this
            return node.args.get("format").name == "%Y%m%d" and configured_time(value)
        if isinstance(node, exp.Cast) and node.to.is_type(exp.DataType.Type.DATE):
            return parameter_type in {"date", "timestamp"} and configured_time(node.this)
        if isinstance(node, exp.TsOrDsToDate):
            return parameter_type in {"date", "timestamp"} and configured_time(node.this)
        return False

    def key_kind(expression: exp.Expression, scope: Scope) -> str | None:
        if has_date and grain == "day" and scaffold_date(expression, scope):
            return "date"
        node = unwrap(_expanded(expression, scope))
        if has_date:
            if grain == "day" and date_value(node):
                return "date"
            if isinstance(node, (exp.DateTrunc, exp.TimestampTrunc)):
                unit = str(node.args.get("unit").name).lower()
                if unit == grain and (date_value(node.this) or parameter_type == "timestamp" and configured_time(node.this)):
                    return "date"
            if isinstance(node, exp.TimeToStr):
                value = node.this
                if isinstance(value, exp.TsOrDsToTimestamp):
                    value = value.this
                formats = {"day": {"%Y-%m-%d", "%Y%m%d"}, "month": {"%Y-%m", "%Y%m"}, "hour": {"%Y-%m-%d %H"}}
                if node.args.get("format").name in formats.get(grain, set()) and (
                    date_value(value) or parameter_type == "timestamp" and configured_time(value)
                ):
                    return "date"
        for name, field in groups:
            if field is not None and _unquoted(node) == _unquoted(field):
                return f"group:{name}"
        return None

    def group_expressions(scope: Scope) -> list[exp.Expression]:
        group = scope.expression.args.get("group")
        if group is None:
            return []
        result = []
        for item in group.expressions:
            if isinstance(item, exp.Literal) and not item.is_string and item.this.isdigit():
                index = int(item.this) - 1
                if 0 <= index < len(scope.expression.selects):
                    item = scope.expression.selects[index]
            elif isinstance(item, exp.Column) and not item.table:
                projected = (_outputs(scope) or {}).get(item.name)
                if isinstance(projected, exp.Alias):
                    item = projected.this
            result.append(item)
        return result

    def contains_scaffold(source: Any, seen=frozenset()) -> bool:
        if not isinstance(source, Scope) or id(source) in seen:
            return False
        parent = source.expression.parent
        if isinstance(parent, exp.CTE) and parent.alias_or_name == "dashboard_dates":
            return True
        return any(contains_scaffold(child, seen | {id(source)}) for _, child in source.selected_sources.values())

    def conjuncts(node: exp.Expression | None):
        if isinstance(node, exp.Paren):
            yield from conjuncts(node.this)
        elif isinstance(node, exp.And):
            yield from conjuncts(node.this)
            yield from conjuncts(node.expression)
        elif node is not None:
            yield node

    checked_joins: set[tuple[int, str]] = set()

    def check_join(scope: Scope, alias: str, label: str) -> None:
        marker = (id(scope), alias)
        if marker in checked_joins:
            return
        checked_joins.add(marker)
        sources = {name: source for name, (_, source) in scope.selected_sources.items()}
        # Joins wholly inside fact processing do not attach a measure to date
        # output. Their ordinary relational keys are outside this contract.
        if not any(name != alias and contains_scaffold(source) for name, source in sources.items()):
            return
        joins = [join for join in scope.expression.args.get("joins") or [] if join.this.alias_or_name == alias]
        matched = set()
        for join in joins:
            for equality in conjuncts(join.args.get("on")):
                if not isinstance(equality, exp.EQ):
                    continue
                left_columns = _select_expression_columns(equality.this)
                right_columns = _select_expression_columns(equality.expression)
                left_sources = {_source(scope, column) for column in left_columns}
                right_sources = {_source(scope, column) for column in right_columns}
                source = sources[alias]
                if not (left_sources == {source} and right_sources and source not in right_sources
                        or right_sources == {source} and left_sources and source not in left_sources):
                    continue
                left_key, right_key = key_kind(equality.this, scope), key_kind(equality.expression, scope)
                if left_key is not None and left_key == right_key:
                    matched.add(left_key)
        missing = expected_keys - matched
        if missing:
            issues.append(f"指标“{label}”连接日期/维度结果时缺少等值连接键：{', '.join(sorted(missing))}；必须按完整配置粒度连接，不能使用 ON TRUE 或只连接部分维度。")

    def nullable_dimension(expression: exp.Expression, scope: Scope, seen=frozenset()) -> bool:
        for column in _select_expression_columns(expression):
            source = _source(scope, column)
            if source is None:
                return True
            optional_sources = {
                scope.sources.get(join.this.alias_or_name)
                for join in scope.expression.args.get("joins") or []
                if join.side in {"LEFT", "FULL"}
            }
            if source in optional_sources:
                return True
            marker = (id(source), column.name)
            if isinstance(source, Scope) and marker not in seen:
                projected = (_outputs(source) or {}).get(column.name)
                if projected is None or nullable_dimension(projected, source, seen | {marker}):
                    return True
        return False

    if contract.get("date_scaffold_required"):
        date_output = outputs.get(contract.get("date_field"))
        if date_output is not None and not scaffold_date(date_output, root):
            issues.append("最终日期列必须来自保留全部日期的日期骨架，不能使用 LEFT JOIN 事实侧的可空日期列。")
        for name, _ in groups:
            if name in outputs and nullable_dimension(outputs[name], root):
                issues.append(f"最终分组列 {name} 必须来自保留完整组合的维度集合，不能使用 LEFT JOIN 事实侧的可空分组列。")

    checked_scopes: set[int] = set()
    metric_paths = [(metric, outputs.get(metric.get("alias"))) for metric in contract.get("metrics") or []]
    for formula in contract.get("formula_metrics") or []:
        if formula.get("alias") in outputs:
            metric_paths.extend((metric, outputs[formula["alias"]]) for metric in formula.get("base_metrics") or [])
    for metric, projection in metric_paths:
        if projection is None:
            continue
        label = str(metric.get("alias") or "")
        nodes = list(_lineage(root, projection))
        for scope, expression in nodes:
            aggregates = list(expression.find_all(exp.AggFunc))
            if aggregates and id(scope) not in checked_scopes:
                checked_scopes.add(id(scope))
                keys = [key_kind(item, scope) for item in group_expressions(scope)]
                group = scope.expression.args.get("group")
                extended = group is not None and any(group.args.get(key) for key in ("rollup", "cube", "grouping_sets", "all"))
                if extended or set(keys) != expected_keys or len(keys) != len(expected_keys):
                    issues.append(f"指标“{label}”的事实聚合粒度与配置不一致；必须仅按日期粒度 {grain if has_date else '(无日期)'} 和配置分组聚合，不能使用全区间总量或增加未配置维度。")
            if aggregates:
                for alias, (_, source) in scope.selected_sources.items():
                    if isinstance(source, exp.Table) and source.name == str(metric.get("table") or "").split(".")[-1]:
                        check_join(scope, alias, label)
            for column in _select_expression_columns(expression):
                source = _source(scope, column)
                if not isinstance(source, Scope):
                    continue
                for alias, (_, child) in scope.selected_sources.items():
                    if child is source:
                        check_join(scope, alias, label)
    return list(dict.fromkeys(issues))
