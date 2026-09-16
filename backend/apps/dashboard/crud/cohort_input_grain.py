"""Require unique cohort membership before joining observation event detail."""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.cohort_sql_validation import _expanded
from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens, _scan_sql_tokens
from apps.dashboard.crud.sql_generation_validation import _outputs, _source, _select_expression_columns
from apps.dashboard.crud.event_sql_contract import _lineage


COHORT_INPUT_RULE = (
    "Cohort 输入唯一粒度（强制）：关联回访、付费或同时展示事件之前，先按 "
    "result_contract.cohort_input.unique_columns 去重初始事件，使用 SELECT DISTINCT 或相同键的 GROUP BY。"
    "必须输出 cohort_date、entity_id 及配置分组键；不能额外携带 event_id、原始事件时间等细粒度字段参与 DISTINCT/GROUP BY，"
    "否则同主体同 Cohort 的重复初始事件仍会成倍放大后续明细。"
    "cohort_size 的 COUNT(DISTINCT entity_id) 或最终 SELECT DISTINCT 不能代替关联前的 Cohort 去重。"
    "后续支付事件仍保留每条真实明细；不得通过 SUM(DISTINCT amount)、对支付日期/主体/金额去重来掩盖重复关联。"
)


def cohort_input_contract(config: dict) -> dict:
    model = config.get("analysis_model")
    keys = ["cohort_date", "entity_id"]
    if model == "revenue":
        keys.extend(f"group_{index + 1}" for index, _ in enumerate(config.get("groups") or []))
    elif model == "retention":
        related = (config.get("retention") or {}).get("relatedProperty") or {}
        if related.get("enabled"):
            keys.append("related_property")
    return {"unique_columns": keys, "deduplicate_before_observation_join": True, "preserve_observation_detail_rows": True}


def _bare(node: exp.Expression) -> exp.Expression:
    while isinstance(node, (exp.Alias, exp.Paren)):
        node = node.this
    return node


def _conjuncts(node: exp.Expression | None):
    if isinstance(node, (exp.Where, exp.Paren)):
        yield from _conjuncts(node.this)
    elif isinstance(node, exp.And):
        yield from _conjuncts(node.this)
        yield from _conjuncts(node.expression)
    elif node is not None:
        yield node


def _scopes(root: Scope, seen=None):
    seen = set() if seen is None else seen
    if id(root) in seen:
        return
    seen.add(id(root))
    for _, source in root.selected_sources.values():
        if isinstance(source, Scope):
            yield from _scopes(source, seen)
    for branch in root.union_scopes:
        yield from _scopes(branch, seen)
    yield root


def _event_source(scope: Scope, source, event: dict, seen=frozenset()) -> bool:
    """Use explicit event predicates and source lineage, never CTE name guesses."""
    marker = (id(scope), id(source))
    if marker in seen or not event.get("eventName") or not event.get("eventNameField"):
        return False
    clauses = [scope.expression.args.get("where")]
    clauses += [join.args.get("on") for join in scope.expression.args.get("joins") or []]
    for clause in clauses:
        for predicate in _conjuncts(clause):
            if isinstance(predicate, exp.In) and not predicate.args.get("query") and len(predicate.expressions) == 1:
                predicate = exp.EQ(this=predicate.this, expression=predicate.expressions[0])
            if not isinstance(predicate, exp.EQ):
                continue
            for column, literal in ((predicate.this, predicate.expression), (predicate.expression, predicate.this)):
                if not isinstance(column, exp.Column) or not isinstance(literal, exp.Literal) or not literal.is_string:
                    continue
                if literal.this != event["eventName"] or _source(scope, column) is not source:
                    continue
                if isinstance(source, exp.Table):
                    if source.name == str(event.get("eventTable") or "").split(".")[-1] and column.name == event["eventNameField"]:
                        return True
                elif isinstance(source, Scope):
                    # A filtered wrapper may reference a projected event-key
                    # column. Resolve it to the physical field, not its alias.
                    projection = (_outputs(source) or {}).get(column.name)
                    if projection is not None:
                        resolved = _bare(projection)
                        if isinstance(resolved, exp.Column):
                            child = _source(source, resolved)
                            if isinstance(child, exp.Table) and child.name == str(event.get("eventTable") or "").split(".")[-1] and resolved.name == event["eventNameField"]:
                                return True
    if isinstance(source, Scope):
        return any(_event_source(source, child, event, seen | {marker}) for _, child in source.selected_sources.values())
    return False


def _one_row(source) -> bool:
    if not isinstance(source, Scope) or source.union_scopes:
        return False
    if not source.selected_sources:
        return True
    return (not source.expression.args.get("group")
            and any(isinstance(node, exp.AggFunc) for projection in source.expression.selects for node in projection.walk())
            and not any(isinstance(node, exp.Window) for projection in source.expression.selects for node in projection.walk()))


def _unique_membership(source, names: list[str], seen=frozenset()) -> bool:
    if not isinstance(source, Scope) or source.union_scopes or id(source) in seen:
        return False
    outputs = _outputs(source) or {}
    if any(name not in outputs for name in names):
        return False
    projections = [_bare(outputs[name]) for name in names]
    try:
        keys = {_expanded(projection, source).sql() for projection in projections}
        distinct = source.expression.args.get("distinct")
        if isinstance(distinct, exp.Distinct) and not distinct.args.get("on"):
            # Extra constants cannot split membership; extra event detail can.
            return all(isinstance(_bare(projection), exp.Literal) or _expanded(projection, source).sql() in keys for projection in outputs.values())
        group = source.expression.args.get("group")
        if group is not None:
            if any(group.args.get(key) for key in ("rollup", "cube", "grouping_sets", "all")):
                return False
            terms = []
            for node in group.expressions:
                if isinstance(node, exp.Literal) and not node.is_string and node.this.isdigit():
                    index = int(node.this) - 1
                    if not 0 <= index < len(source.expression.selects):
                        return False
                    node = source.expression.selects[index]
                elif isinstance(node, exp.Column) and not node.table and node.name in outputs:
                    node = outputs[node.name]
                terms.append(_expanded(node, source).sql())
            return set(terms) == keys
    except ValueError:
        return False
    if not all(isinstance(projection, exp.Column) for projection in projections):
        return False
    inherited = {_source(source, projection) for projection in projections}
    if len(inherited) != 1:
        return False
    child = next(iter(inherited))
    if any(candidate is not child and not _one_row(candidate) for _, candidate in source.selected_sources.values()):
        return False
    return _unique_membership(child, [projection.name for projection in projections], seen | {id(source)})


def cohort_input_grain_issues(sql: str, config: dict, dialect="mysql") -> list[str]:
    model = config.get("analysis_model")
    settings = config.get(model) or {}
    initial = settings.get("initialEvent") or settings.get("initial_event") or {}
    observation = settings.get("paymentEvent" if model == "revenue" else "returnEvent") or {}
    time = config.get("time") or {}
    tokens = dashboard_date_parameter_tokens(time.get("date_parameter_type") or time.get("dateParameterType") or "") or ()
    prepared, _ = _scan_sql_tokens(sql, {token: ":" + token[2:-2] for token in tokens})
    try:
        statement = sqlglot.parse_one(prepared, read=dialect or "mysql")
        root = build_scope(statement)
        if root is None:
            return []  # The syntax/result validators report missing SELECTs.
        keys = cohort_input_contract(config)["unique_columns"]
        preserve_details = model == "revenue" and (settings.get("metric") or {}).get("method") in {
            "count", "per_entity_count", "property_sum", "property_avg", "period_cumulative_count", "period_average_count",
        }
        matched_scopes: set[int] = set()
        issues = []
        for scope in _scopes(root):
            sources = {name: source for name, (_, source) in scope.selected_sources.items()}
            if len(sources) < 2:
                continue
            cohort_projection = (_outputs(scope) or {}).get("cohort_date")
            cohort_sources = {_source(scope, column) for column in _select_expression_columns(cohort_projection)}
            entity_projection = (_outputs(scope) or {}).get("entity_id")
            entity_sources = {_source(scope, column) for column in _select_expression_columns(entity_projection)}
            for alias, source in sources.items():
                if not _event_source(scope, source, initial):
                    continue
                if isinstance(source, Scope) and any(id(child) in matched_scopes for child in _scopes(source)):
                    continue
                outputs = _outputs(source) or {} if isinstance(source, Scope) else {}
                if not ({"cohort_date", "entity_id"} <= set(outputs) or source in cohort_sources & entity_sources):
                    continue
                others = [other for name, other in sources.items() if name != alias and _event_source(scope, other, observation)]
                if not others:
                    continue
                matched_scopes.add(id(scope))
                if not _unique_membership(source, keys):
                    issues.append(f"Cohort 输入 {alias} 无法证明关联前的唯一粒度 {' + '.join(keys)}；请先仅按这些键 SELECT DISTINCT 或 GROUP BY，再关联观察事件明细。cohort_size 的 COUNT(DISTINCT) 不能防止金额/次数被重复初始事件放大，不能对真实观察明细去重掩盖问题。")
                if preserve_details:
                    for other in others:
                        if not isinstance(other, Scope):
                            continue
                        for detail in _scopes(other):
                            if detail.expression.args.get("distinct") and any(_event_source(detail, child, observation) for _, child in detail.selected_sources.values()):
                                issues.append("Cohort 输入唯一粒度必须通过初始事件去重保证；当前收入统计需要保留每条观察事件明细，不能对支付日期、主体、金额使用 SELECT DISTINCT 代替。")
        if preserve_details:
            for name, projection in (_outputs(root) or {}).items():
                if not name.startswith("day_"):
                    continue
                if any(isinstance(node, (exp.Sum, exp.Avg)) and isinstance(node.this, exp.Distinct)
                       for _, expression in _lineage(root, projection) for node in expression.walk()):
                    issues.append("Cohort 输入唯一粒度必须通过初始事件去重保证；不能对 day_N 的真实金额或次数使用 SUM(DISTINCT)/AVG(DISTINCT)，相同金额的多条明细仍须保留。")
        return list(dict.fromkeys(issues))
    except (sqlglot.errors.SqlglotError, ValueError, TypeError) as exc:
        return [f"Cohort 输入唯一粒度无法验证：{exc}。"]
