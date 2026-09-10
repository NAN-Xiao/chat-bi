"""Structural checks for generated dashboard SQL, without executing business queries."""
from __future__ import annotations

from collections.abc import Iterable

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


def _outputs(scope: Scope, seen: frozenset = frozenset()) -> dict[str, exp.Expression] | None:
    if id(scope) in seen:
        return None
    seen = seen | {id(scope)}
    query = scope.expression
    if scope.union_scopes:
        outputs = _outputs(scope.union_scopes[0], seen)
        if outputs is not None and scope.outer_columns:
            return dict(zip(scope.outer_columns, outputs.values()))
        return outputs
    projections = []
    for item in query.selects:
        if not item.is_star:
            projections.append(item)
            continue
        star = item.this if isinstance(item, exp.Column) else item
        if any(star.args.values()):
            return None
        qualifier = item.table if isinstance(item, exp.Column) else ""
        sources = {name: source for name, (_, source) in scope.selected_sources.items()
                   if not qualifier or name == qualifier}
        if not sources:
            return None
        for name, source in sources.items():
            columns = _outputs(source, seen) if isinstance(source, Scope) else None
            if columns is None:
                return None  # Physical SELECT * requires schema information we do not have here.
            projections.extend(exp.column(column, table=name) for column in columns)
    if scope.outer_columns:
        return dict(zip(scope.outer_columns, projections))
    if len({item.alias_or_name for item in projections}) != len(projections):
        return None
    return {item.alias_or_name: item for item in projections}


def _source(scope: Scope, column: exp.Column):
    sources = {name: source for name, (_, source) in scope.selected_sources.items()}
    if column.table:
        return sources.get(column.table)
    candidates = [source for source in sources.values()
                  if not isinstance(source, Scope) or _outputs(source) is None
                  or column.name in _outputs(source)]
    return candidates[0] if len(candidates) == 1 else None


def _column_names(node: exp.Expression) -> set[str]:
    return {column.name for column in node.find_all(exp.Column)}


def _select_expression_columns(expression: exp.Expression | None) -> list[exp.Column]:
    """Collect columns from one expression without entering nested SELECTs."""
    if expression is None:
        return []
    columns: list[exp.Column] = []

    def visit(node: exp.Expression) -> None:
        if isinstance(node, exp.Select):
            return
        if isinstance(node, exp.Column):
            columns.append(node)
            return
        for child in node.iter_expressions():
            visit(child)

    visit(expression)
    return columns


def _normalized_alias(value: object) -> str:
    return str(value or "").strip().strip('"`[]').lower()


def same_select_alias_reference_issues(
        statements: Iterable[exp.Expression],
        *,
        sql_dialect: str | None = None,
) -> list[str]:
    """Find query-block alias references before the alias is in scope.

    This validator is shared by SQL generation and execution.  WHERE and JOIN
    ON cannot see aliases introduced by their SELECT list.  MySQL-compatible
    engines may allow ordinary or aggregate aliases in HAVING, but a window
    alias is evaluated too late and must be rejected there as well.
    """
    issues: list[str] = []
    dialect = str(sql_dialect or "mysql").strip().lower()
    having_aliases_allowed = dialect in {
        "mysql",
        "mariadb",
        "doris",
        "starrocks",
        "analyticdb",
    }
    for statement in statements:
        for select in statement.find_all(exp.Select):
            aliases: dict[str, exp.Expression] = {}
            for projection in select.expressions:
                if not isinstance(projection, exp.Alias):
                    continue
                alias_name = _normalized_alias(projection.alias)
                expression = projection.args.get("this")
                if not alias_name or expression is None:
                    continue
                # A pass-through alias does not create a new name that can
                # shadow its source column in this query block.
                if (
                    isinstance(expression, exp.Column)
                    and _normalized_alias(expression.name) == alias_name
                ):
                    continue
                aliases[alias_name] = expression
            if not aliases:
                continue

            for projection in select.expressions:
                if not isinstance(projection, exp.Alias):
                    continue
                projection_alias = _normalized_alias(projection.alias)
                for column in _select_expression_columns(projection.args.get("this")):
                    column_name = _normalized_alias(column.name)
                    if (
                        column.table
                        or column_name not in aliases
                        or column_name == projection_alias
                    ):
                        continue
                    issues.append(
                        f"查询块输出列 {projection_alias} 引用了同层刚定义的别名 {column_name}；"
                        "请先在子查询或 CTE 中生成该字段，再由外层查询引用。"
                    )

            clauses: list[tuple[str, exp.Expression | None, bool]] = []
            where = select.args.get("where")
            clauses.append(("WHERE", where.this if where is not None else None, True))
            having = select.args.get("having")
            clauses.append((
                "HAVING",
                having.this if having is not None else None,
                not having_aliases_allowed,
            ))
            for join in select.args.get("joins") or []:
                clauses.append(("JOIN ON", join.args.get("on"), True))

            for clause_name, clause_expression, all_aliases_invalid in clauses:
                if clause_expression is None:
                    continue
                for column in _select_expression_columns(clause_expression):
                    column_name = _normalized_alias(column.name)
                    alias_expression = aliases.get(column_name)
                    if column.table or alias_expression is None:
                        continue
                    is_window_alias = any(
                        isinstance(node, exp.Window)
                        for node in alias_expression.walk()
                    )
                    if not all_aliases_invalid and not is_window_alias:
                        continue
                    issues.append(
                        f"查询块 {clause_name} 引用了同层刚定义的别名 {column_name}；"
                        "请先在子查询或 CTE 中生成该字段，再由外层查询引用。"
                    )
    return list(dict.fromkeys(issues))


def _seconds(value: exp.Expression | None, unit: exp.Expression | None) -> float | None:
    factors = {"SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400}
    if not isinstance(value, exp.Literal) or unit is None:
        return None
    try:
        return float(value.this) * factors[str(unit.name).upper()]
    except (ValueError, KeyError):
        return None


def _duration_bound(term: exp.Expression, seconds: int) -> bool:
    if not isinstance(term, (exp.GTE, exp.LTE)):
        return False
    lower, upper = (term.this, term.expression) if isinstance(term, exp.LTE) else (term.expression, term.this)
    if isinstance(upper, exp.Column) and upper.name == "touch_time":
        if isinstance(lower, exp.Sub) and isinstance(lower.expression, exp.Interval):
            return (isinstance(lower.this, exp.Column) and lower.this.name == "target_time"
                    and _seconds(lower.expression.this, lower.expression.args.get("unit")) == seconds)
        if isinstance(lower, (exp.DateSub, exp.TimestampSub)):
            return (isinstance(lower.this, exp.Column) and lower.this.name == "target_time"
                    and _seconds(lower.expression, lower.args.get("unit")) == seconds)
    if isinstance(lower, exp.TimestampDiff):
        # sqlglot normalizes TIMESTAMPDIFF(unit, start, end) to this=end, expression=start.
        return (isinstance(lower.this, exp.Column) and lower.this.name == "target_time"
                and isinstance(lower.expression, exp.Column) and lower.expression.name == "touch_time"
                and str(lower.args.get("unit")).upper() == "SECOND"
                and _seconds(upper, exp.Var(this="SECOND")) == seconds)
    return False


def derived_column_issues(statement: exp.Expression) -> list[str]:
    """Only reject provably missing derived columns; physical schema is checked elsewhere."""
    issues: list[str] = []
    scopes = list(traverse_scope(statement))
    owners = {id(scope.expression): scope for scope in scopes}
    for scope in scopes:
        sources = {name: source for name, (_, source) in scope.selected_sources.items()}
        for column in scope.columns:
            if column.is_star:
                continue
            nested = owners.get(id(column.find_ancestor(exp.Select)))
            if nested is not None and nested is not scope and _source(nested, column) is not None:
                continue  # An unqualified scalar-subquery column can still resolve locally.
            source = _source(scope, column)
            if isinstance(source, Scope):
                outputs = _outputs(source)
                if outputs is not None and column.name not in outputs:
                    issues.append(f"SQL 字段 {column.sql()} 未由其来源 CTE 或子查询输出，请在正确的明细层保留该字段。")
            elif not column.table and sources and all(
                isinstance(item, Scope) and _outputs(item) is not None
                and column.name not in _outputs(item) for item in sources.values()
            ):
                # ORDER BY / GROUP BY can legally reference this SELECT's output aliases.
                aliases = {item.alias for item in scope.expression.selects if item.alias}
                if column.name not in aliases and not scope.is_correlated_subquery:
                    issues.append(f"SQL 字段 {column.name} 未由当前查询的任何 CTE 或子查询输出。")
    return list(dict.fromkeys(issues))


def encoded_date_issues(statement: exp.Expression, field: dict, parameter_type: str) -> list[str]:
    if parameter_type not in {"yyyymmdd_number", "yyyymmdd_text"}:
        return []
    field_name = str(field.get("field") or field.get("name") or "").split(".")[-1].lower()
    table_name = str(field.get("table") or "").lower()
    if not field_name:
        return []

    def contains_key(node: exp.Expression, scope: Scope, seen: frozenset = frozenset()) -> bool:
        # Parsing the encoded value terminates its numeric-date lineage.
        if isinstance(node, (exp.StrToDate, exp.TsOrDsToDate)):
            return False
        if isinstance(node, exp.Cast) and node.to.is_type(exp.DataType.Type.DATE, exp.DataType.Type.TIMESTAMP, exp.DataType.Type.DATETIME):
            return False
        if isinstance(node, exp.Column):
            source = _source(scope, node)
            if isinstance(source, Scope):
                marker = (id(source), node.name)
                if marker in seen:
                    return False
                projection = (_outputs(source) or {}).get(node.name)
                return projection is not None and contains_key(projection, source, seen | {marker})
            return node.name.lower() == field_name and (
                not table_name or source is None
                or isinstance(source, exp.Table) and source.name.lower() == table_name
            )
        return any(contains_key(child, scope, seen) for child in node.iter_expressions()
                   if not isinstance(child, exp.Query))

    issues: list[str] = []
    arithmetic = (exp.Add, exp.Sub, exp.DateAdd, exp.DateSub, exp.DateDiff,
                  exp.TimestampAdd, exp.TimestampSub, exp.TimestampDiff)
    for scope in traverse_scope(statement):
        for node in scope.expression.walk(prune=lambda child: child is not scope.expression and isinstance(child, exp.Query)):
            if isinstance(node, arithmetic) and contains_key(node, scope):
                issues.append(
                    f"SQL 日期运算 {node.sql()} 使用了未经解析的 YYYYMMDD 编码键；"
                    "必须先按数据源方言解析为 DATE，不能进行整数减法或直接加减 INTERVAL。"
                )
    return list(dict.fromkeys(issues))


def _conjuncts(node: exp.Expression | None) -> list[exp.Expression]:
    if isinstance(node, exp.Paren):
        return _conjuncts(node.this)
    if isinstance(node, exp.And):
        return _conjuncts(node.this) + _conjuncts(node.expression)
    return [node] if node is not None else []


def _resolve_projection(node: exp.Expression, scope: Scope):
    """Follow pass-through columns, retaining joins traversed to reach an expression."""
    path: list[tuple[Scope, Scope]] = []
    seen: set[tuple[int, str]] = set()
    while True:
        if isinstance(node, (exp.Alias, exp.Paren)):
            node = node.this
            continue
        if not isinstance(node, exp.Column):
            break
        source = _source(scope, node)
        if not isinstance(source, Scope):
            break
        if source.union_scopes:
            break  # UNION values have one lineage per branch, not the first branch's scope.
        marker = (id(source), node.name)
        projection = (_outputs(source) or {}).get(node.name)
        if marker in seen or projection is None:
            break
        seen.add(marker)
        path.append((scope, source))
        node, scope = projection, source
    return node, scope, path


def _matching_scopes(scopes: list[Scope]) -> list[Scope]:
    matches = []
    for scope in scopes:
        if not isinstance(scope.expression, exp.Select) or not scope.expression.args.get("joins"):
            continue
        outputs = _outputs(scope) or {}
        sources = []
        for name in ("target_time", "touch_time"):
            value = outputs.get(name)
            if isinstance(value, exp.Alias):
                value = value.this
            sources.append(_source(scope, value) if isinstance(value, exp.Column) else None)
        # A later join to a count CTE carries both times from the same matched source.
        if all(source is not None for source in sources) and sources[0] is not sources[1]:
            matches.append(scope)
    return matches


def _same_value(left: exp.Expression, left_scope: Scope, right: exp.Expression, right_scope: Scope) -> bool:
    """Compare expressions through projections, without relying on intermediate aliases."""
    left, left_scope, _ = _resolve_projection(left, left_scope)
    right, right_scope, _ = _resolve_projection(right, right_scope)
    if left_scope is right_scope and left == right:
        return True
    if isinstance(left, exp.Column) or isinstance(right, exp.Column):
        return (isinstance(left, exp.Column) and isinstance(right, exp.Column)
                and left.name == right.name and _source(left_scope, left) is _source(right_scope, right)
                and _source(left_scope, left) is not None)
    if type(left) is not type(right):
        return False
    # Preserve operators, literals, units and argument positions while resolving children.
    for key in left.arg_types:
        a, b = left.args.get(key), right.args.get(key)
        if isinstance(a, exp.Expression) and isinstance(b, exp.Expression):
            if not _same_value(a, left_scope, b, right_scope):
                return False
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return False
            for x, y in zip(a, b):
                if isinstance(x, exp.Expression) and isinstance(y, exp.Expression):
                    if not _same_value(x, left_scope, y, right_scope):
                        return False
                elif x != y:
                    return False
        elif a != b:
            return False
    # Query-local identities must not compare equal across separate event scans.
    return left_scope is right_scope if isinstance(left, exp.Window) else True


def _natural_day_of(value: exp.Expression, scope: Scope, timestamp: exp.Expression) -> bool:
    value, owner, _ = _resolve_projection(value, scope)
    if isinstance(value, (exp.Date, exp.TsOrDsToDate)) or (
        isinstance(value, exp.Cast) and value.to.is_type(exp.DataType.Type.DATE)
    ):
        return _same_value(value.this, owner, timestamp, scope)
    return False


def _same_day_match(term: exp.Expression, scope: Scope) -> bool:
    if not isinstance(term, exp.EQ):
        return False
    outputs = _outputs(scope) or {}
    for target, touch in ((term.this, term.expression), (term.expression, term.this)):
        def is_day(value, side):
            date = outputs.get(f"{side}_date")
            time = outputs.get(f"{side}_time")
            return (date is not None and _same_value(value, scope, date, scope)) or (
                time is not None and _natural_day_of(value, scope, time))
        if is_day(target, "target") and is_day(touch, "touch"):
            return True
    return False


def _target_count_join(parent: Scope, source: Scope) -> bool:
    aliases = {name for name, (_, selected) in parent.selected_sources.items() if selected is source}
    for join in parent.expression.args.get("joins") or []:
        for term in _conjuncts(join.args.get("on")):
            if not isinstance(term, exp.EQ) or not all(isinstance(side, exp.Column) for side in (term.this, term.expression)):
                continue
            left, right = term.this, term.expression
            if left.name == right.name == "target_id" and (left.table in aliases) != (right.table in aliases):
                left_value, left_scope, _ = _resolve_projection(left, parent)
                right_value, right_scope, _ = _resolve_projection(right, parent)
                if left_scope is right_scope and left_value == right_value:
                    return True
        using = join.args.get("using") or []
        if join.this.alias_or_name in aliases and any(item.name == "target_id" for item in using):
            counted, counted_scope, _ = _resolve_projection(exp.column("target_id", table=join.this.alias_or_name), parent)
            for name in parent.selected_sources:
                if name not in aliases:
                    target, target_scope, _ = _resolve_projection(exp.column("target_id", table=name), parent)
                    if target_scope is counted_scope and target == counted:
                        return True
    return False


def _null_without_touch(value: exp.Expression, scope: Scope, matches: list[Scope]) -> bool:
    for match in matches:
        for key in ("touch_id", "touch_time"):
            touch = (_outputs(match) or {}).get(key)
            if touch is not None and _same_value(value, scope, touch, match):
                return True
    value, owner, _ = _resolve_projection(value, scope)
    if not isinstance(value, exp.Case) or value.this is not None:
        return False
    arms = value.args.get("ifs") or []
    if len(arms) != 1:
        return False
    predicate = arms[0].this
    negated = isinstance(predicate, exp.Not)
    if negated:
        predicate = predicate.this
    if not isinstance(predicate, exp.Is) or not isinstance(predicate.expression, exp.Null):
        return False
    null_branch = value.args.get("default") if negated else arms[0].args.get("true")
    return (isinstance(null_branch, exp.Null)
            and _null_without_touch(predicate.this, owner, matches))


def _touches_can_be_null(scope: Scope, matches: list[Scope], seen: frozenset[int] = frozenset()) -> bool:
    if id(scope) in seen:
        return True
    where = scope.expression.args.get("where")
    for term in _conjuncts(where.this if where else None):
        if (isinstance(term, exp.Not) and isinstance(term.this, exp.Is)
                and isinstance(term.this.this, exp.Column)
                and isinstance(term.this.expression, exp.Null)):
            if _null_without_touch(term.this.this, scope, matches):
                return False
        if isinstance(term, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)) and any(
            _null_without_touch(side, scope, matches) for side in (term.this, term.expression)
        ):
            return False
    if any(scope is match for match in matches):
        output = (_outputs(scope) or {}).get("touch_time")
        if isinstance(output, exp.Alias):
            output = output.this
        if not isinstance(output, exp.Column):
            return True
        nullable = any(
            join.side == "FULL" or join.side == "LEFT" and join.this.alias_or_name == output.table
            or join.side == "RIGHT" and join.this.alias_or_name != output.table
            for join in scope.expression.args.get("joins") or []
        )
        return nullable
    sources = [source for _, source in scope.selected_sources.values()
               if isinstance(source, Scope) and _depends_on_match(source, matches)]
    return not sources or any(_touches_can_be_null(source, matches, seen | {id(scope)}) for source in sources)


def _linear_weight_issues(scopes: list[Scope], matches: list[Scope]) -> list[str]:
    issues: list[str] = []
    fractions = [(node, scope) for scope in scopes for item in scope.expression.selects
                 if item.alias == "linear_weight" for node in item.find_all(exp.Div)]
    if not fractions:
        return ["归因 linear_weight 缺少每个目标独立计算的触点分配比例。"]
    for fraction, scope in fractions:
        denominator = fraction.expression
        if (not isinstance(fraction.this, exp.Literal) or not fraction.this.is_number or float(fraction.this.this) != 1
                or not isinstance(denominator, exp.Nullif) or not isinstance(denominator.expression, exp.Literal)
                or not denominator.expression.is_number or float(denominator.expression.this) != 0):
            issues.append("归因 linear_weight 必须为 1.0 / NULLIF(目标触点数, 0)，目标值只能在汇总时乘一次。")
            continue
        value, count_scope, path = _resolve_projection(denominator.this, scope)
        if isinstance(value, exp.Window) and isinstance(value.this, exp.Count):
            count = value.this
            keys = value.args.get("partition_by") or []
        elif isinstance(value, exp.Count):
            count = value
            keys = (count_scope.expression.args.get("group") or exp.Group()).expressions
            # A grouped count must be joined back on its complete unique target key.
            joined = False
            for parent, source in reversed(path):
                if _target_count_join(parent, source):
                    joined = True
                    break
                if parent.expression.args.get("joins") or len(parent.selected_sources) != 1:
                    break
            if not joined:
                issues.append("归因分组触点数必须按 target_id 关联回匹配明细，不能交叉关联或按其他字段关联。")
        else:
            issues.append("归因 linear_weight 的分母必须来自当前目标的触点 COUNT，不能仅凭列名判定。")
            continue
        if len(keys) != 1 or not isinstance(keys[0], exp.Column) or keys[0].name != "target_id":
            issues.append("归因触点计数必须仅按 target_id 分区或分组，每个目标单独分配贡献。")
        if isinstance(count.this, exp.Star):
            if _touches_can_be_null(count_scope, matches):
                issues.append("归因 COUNT(*) 可能将 LEFT JOIN 空行算作触点；请统计非空触点时间。")
        elif not isinstance(count.this, exp.Column) or count.this.name not in {"touch_time", "touch_id"}:
            issues.append("归因触点数必须统计非空 touch_time，不能对其他字段或 DISTINCT 触点去重。")
    return list(dict.fromkeys(issues))


def _metric_nodes(node: exp.Expression, scope: Scope, kind: type, seen: frozenset = frozenset()):
    """Follow only the requested result's lineage, including UNION output positions."""
    marker = (id(scope), id(node))
    if marker in seen:
        return
    seen = seen | {marker}
    if isinstance(node, kind):
        yield node, scope
        return
    if isinstance(node, exp.Column):
        source = _source(scope, node)
        if isinstance(source, Scope):
            outputs = _outputs(source) or {}
            if source.union_scopes and node.name in outputs:
                index = list(outputs).index(node.name)
                for branch in source.union_scopes:
                    projections = list((_outputs(branch) or {}).values())
                    if index < len(projections):
                        yield from _metric_nodes(projections[index], branch, kind, seen)
            elif node.name in outputs:
                yield from _metric_nodes(outputs[node.name], source, kind, seen)
        return
    for child in node.iter_expressions():
        yield from _metric_nodes(child, scope, kind, seen)


def _depends_on_match(scope: Scope, matches: list[Scope], seen: frozenset = frozenset()) -> bool:
    if any(scope is match for match in matches):
        return True
    if id(scope) in seen:
        return False
    sources = [source for _, source in scope.selected_sources.values() if isinstance(source, Scope)]
    return any(_depends_on_match(source, matches, seen | {id(scope)})
               for source in [*sources, *scope.union_scopes])


def _entity_count_uses_touch(count: exp.Count, owner: Scope, matches: list[Scope]) -> bool:
    distinct = count.this
    if not isinstance(distinct, exp.Distinct) or len(distinct.expressions) != 1:
        return False
    value, scope = distinct.expressions[0], owner
    seen = set()
    while True:
        if isinstance(value, (exp.Alias, exp.Paren)):
            value = value.this
            continue
        if not isinstance(value, exp.Column) or (id(scope), value.name, value.table) in seen:
            return False
        seen.add((id(scope), value.name, value.table))
        source = _source(scope, value)
        if any(scope is match for match in matches):
            touch = (_outputs(scope) or {}).get("touch_id")
            if isinstance(touch, exp.Alias):
                touch = touch.this
            if isinstance(touch, exp.Column) and source is _source(scope, touch):
                return True
            # A target-side UID is equivalent only after the equality join has matched.
            target = (_outputs(scope) or {}).get("target_id")
            if isinstance(target, exp.Alias):
                target = target.this
            return (isinstance(target, exp.Column) and source is _source(scope, target)
                    and not _touches_can_be_null(owner, matches))
        projection = (_outputs(source) or {}).get(value.name) if isinstance(source, Scope) else None
        if projection is None:
            return False
        value, scope = projection, source


def _scalar_aggregate(scope: Scope) -> bool:
    query = scope.expression
    return (isinstance(query, exp.Select) and not any(query.args.get(key) for key in ("group", "having", "limit", "offset"))
            and any(aggregate.find_ancestor(exp.Select) is query and aggregate.find_ancestor(exp.Window) is None
                    for item in query.selects for aggregate in item.find_all(exp.AggFunc)))


def _preserves_rows(scope: Scope, origin: Scope, seen: frozenset = frozenset()) -> bool:
    """Prove a result path retains the touch-statistics rows, respecting join direction."""
    if scope is origin:
        return True
    if id(scope) in seen:
        return False
    seen = seen | {id(scope)}
    query = scope.expression
    if any(query.args.get(key) for key in ("where", "having", "qualify", "limit", "offset")):
        return False
    if scope.union_scopes:
        return isinstance(query, exp.Union) and any(_preserves_rows(branch, origin, seen) for branch in scope.union_scopes)
    sources = {alias: source for alias, (_, source) in scope.selected_sources.items()}
    for alias, source in sources.items():
        if not isinstance(source, Scope) or not _preserves_rows(source, origin, seen):
            continue
        preserved = True
        for join in query.args.get("joins") or []:
            joined_alias = join.this.alias_or_name
            if joined_alias == alias:
                preserved = join.side in {"RIGHT", "FULL"}
            elif preserved:
                other = sources.get(joined_alias)
                scalar = (isinstance(other, Scope) and _scalar_aggregate(other)
                          and not join.args.get("on") and not join.args.get("using"))
                preserved = join.side in {"LEFT", "FULL"} or scalar
        if preserved:
            return True
    return False


def _number(value: exp.Expression | None, number: float) -> bool:
    return isinstance(value, exp.Literal) and value.is_number and float(value.this) == number


def _without_zero_coalesce(value: exp.Expression) -> exp.Expression:
    while isinstance(value, (exp.Alias, exp.Paren)):
        value = value.this
    if isinstance(value, exp.Coalesce) and len(value.expressions) == 1 and _number(value.expressions[0], 0):
        return _without_zero_coalesce(value.this)
    return value


def _rate_value_matches(value: exp.Expression, scope: Scope, metric: exp.Expression, root: Scope) -> bool:
    def branches(node, owner, seen=frozenset()):
        node, owner, _ = _resolve_projection(node, owner)
        unwrapped = _without_zero_coalesce(node)
        if unwrapped is not node:
            yield from branches(unwrapped, owner, seen)
            return
        marker = (id(owner), id(node))
        if marker in seen:
            return
        source = _source(owner, node) if isinstance(node, exp.Column) else None
        if isinstance(source, Scope) and source.union_scopes:
            names = list(_outputs(source) or {})
            if node.name in names:
                index = names.index(node.name)
                for branch in source.union_scopes:
                    outputs = list((_outputs(branch) or {}).values())
                    if index < len(outputs):
                        yield from branches(outputs[index], branch, seen | {marker})
        else:
            yield node, owner
    return any(_same_value(a, a_scope, b, b_scope)
               for a, a_scope in branches(value, scope) for b, b_scope in branches(metric, root))


def _safe_rate_division(fraction: exp.Div, scope: Scope) -> bool:
    denominator = fraction.expression
    if isinstance(denominator, exp.Nullif) and _number(denominator.expression, 0):
        return True
    # CASE is safe only when this division's own denominator is guarded and zero yields NULL.
    branch = fraction.parent
    while branch is not None and not isinstance(branch, (exp.Select, exp.Case)):
        branch = branch.parent
    if not isinstance(branch, exp.Case) or branch.this is not None:
        return False
    arms = branch.args.get("ifs") or []
    if len(arms) != 1:
        return False
    arm = arms[0]
    predicate = arm.this
    if not isinstance(predicate, (exp.EQ, exp.NEQ, exp.GT, exp.LT)):
        return False
    left, right = predicate.this, predicate.expression
    if _number(left, 0):
        left, right = right, left
        operator = {exp.GT: exp.LT, exp.LT: exp.GT}.get(type(predicate), type(predicate))
    else:
        operator = type(predicate)
    if not _number(right, 0) or not _same_value(left, scope, denominator, scope):
        return False
    positive = arm.args.get("true")
    negative = branch.args.get("default")
    if operator is exp.EQ:
        positive, negative = negative, positive
    elif operator not in {exp.GT, exp.NEQ}:
        return False
    return (isinstance(negative, exp.Null) and positive is not None
            and any(node is fraction for node in positive.walk()))


def _effective_rate_valid(output: exp.Expression | None, root: Scope, outputs: dict) -> bool:
    if output is None:
        return False
    fractions = list(_metric_nodes(output, root, exp.Div))
    if not fractions:
        return False
    for fraction, scope in fractions:
        numerator, denominator = fraction.this, fraction.expression
        if isinstance(denominator, exp.Nullif):
            denominator = denominator.this
        if not isinstance(numerator, exp.Mul) or not _safe_rate_division(fraction, scope):
            return False
        a, b = numerator.this, numerator.expression
        if _number(a, 100):
            a, b = b, a
        if (not _number(b, 100)
                or not _rate_value_matches(a, scope, outputs["effective_touch_count"], root)
                or not _rate_value_matches(denominator, scope, outputs["total_touch_count"], root)):
            return False
    return True


def _touch_metric_issues(scopes: list[Scope], matches: list[Scope], groups: list[dict]) -> list[str]:
    issues = []
    root = scopes[-1]
    outputs = _outputs(root) or {}
    for metric, key in (("total_touch_count", "touch_id"), ("effective_touch_count", "touch_id"),
                        ("effective_entity_count", "entity_id")):
        output = outputs.get(metric)
        counts = list(_metric_nodes(output, root, exp.Count)) if output is not None else []
        if not counts:
            issues.append(f"归因 {metric} 必须从真实触点明细计算，不能用常量或目标次数替代。")
        for count, owner in counts:
            distinct = count.this
            if (not isinstance(distinct, exp.Distinct) or len(distinct.expressions) != 1
                    or _column_names(distinct) != {key}):
                issues.append(f"归因 {metric} 必须 COUNT(DISTINCT {key})，同一触点多次归因仍只计一次。")
            if metric == "effective_entity_count" and not _entity_count_uses_touch(count, owner, matches):
                issues.append("归因有效用户必须来自触点侧；使用目标侧主体时，必须在计数前排除未匹配触点的记录。")
            matched = _depends_on_match(owner, matches)
            if metric == "total_touch_count" and matched:
                issues.append("归因总触发数必须从关联目标前的触点全集统计，不能只统计匹配成功或获选触点。")
            elif metric != "total_touch_count" and not matched:
                issues.append(f"归因 {metric} 必须来自实际获选触点，不能直接使用触点全集。")
            if metric == "total_touch_count" and not _preserves_rows(root, owner):
                issues.append("归因结果必须保留触点全集的零贡献行：以触点统计 LEFT JOIN 贡献统计，再 UNION ALL 直接转化；不能以贡献统计为主表。")
    effective_rate = outputs.get("effective_touch_rate")
    if not {"effective_touch_count", "total_touch_count"}.issubset(outputs) or not _effective_rate_valid(effective_rate, root, outputs):
        issues.append("归因有效触发率必须为 effective_touch_count * 100.0 / total_touch_count，分母为零时用 NULLIF 或等价 CASE 返回 NULL。")
    contribution = outputs.get("contribution_rate")
    expected = {f"group_{index + 1}" for index, group in enumerate(groups) if group.get("attributionSide") != "touch"}
    if contribution is not None:
        fractions = list(_metric_nodes(contribution, root, exp.Div))
        if not fractions or any(not _safe_rate_division(fraction, owner) for fraction, owner in fractions):
            issues.append("归因贡献度必须在分母为零时用 NULLIF 或等价 CASE 返回 NULL。")
        for window, _ in _metric_nodes(contribution, root, exp.Window):
            if isinstance(window.this, exp.Sum):
                keys = set().union(*(_column_names(key) for key in window.args.get("partition_by") or []))
                if keys != expected:
                    issues.append("归因贡献度的分母只能按目标事件侧分组，必须跨全部归因事件及触点侧分组计算。")
    return issues


def attribution_structure_issues(statement: exp.Expression, config: dict, groups: list[dict] | None = None) -> list[str]:
    """Validate the explicit target/touch result contract used by generation and repair."""
    issues: list[str] = []
    method = str(config.get("method") or "linear")
    window = config.get("window") or {}
    selects = list(statement.find_all(exp.Select))
    scopes = list(traverse_scope(statement))
    matching_scopes = _matching_scopes(scopes)
    issues.extend(_touch_metric_issues(scopes, matching_scopes, groups or []))
    target_origins = [item for select in selects for item in select.selects if item.alias == "target_id"]
    if not target_origins:
        issues.append("归因 SQL 必须为每条目标事件保留 target_id；不得按用户与日期合并目标事件。")
    for item in target_origins:
        owner = item.find_ancestor(exp.Select)
        if owner is not None and (owner.args.get("distinct") or owner.args.get("group")):
            issues.append("归因目标明细不能在分配 target_id 时去重或聚合，必须保留每次目标事件。")
        value = item.this
        if isinstance(value, exp.Column):
            continue
        if not (isinstance(value, exp.Window) and isinstance(value.this, exp.RowNumber)
                and not value.args.get("partition_by") and value.args.get("order")):
            issues.append("归因 target_id 必须来自事件唯一键或关联前全局 ROW_NUMBER()，不能拼接用户日期或使用分区内序号。")
    target_counts = [item for select in selects for item in select.selects if item.alias == "target_count"]
    if not any(
        isinstance(count.this, exp.Distinct)
        and len(count.this.expressions) == 1
        and isinstance(count.this.expressions[0], exp.Column)
        and count.this.expressions[0].name == "target_id"
        for item in target_counts for count in item.find_all(exp.Count)
    ):
        issues.append("归因 target_count 必须 COUNT(DISTINCT target_id)，不能统计用户日数。")

    weight_windows = [node for select in selects for item in select.selects for node in item.find_all(exp.Window)
                      if isinstance(node.this, (exp.Count, exp.RowNumber, exp.Rank))
                      and item.alias not in {"target_id", "touch_id"}]
    if method == "linear":
        issues.extend(_linear_weight_issues(scopes, matching_scopes))
    else:
        relevant = weight_windows
        if not relevant or any(
            len(node.args.get("partition_by") or []) != 1
            or not isinstance(node.args["partition_by"][0], exp.Column)
            or node.args["partition_by"][0].name != "target_id" for node in relevant
        ):
            issues.append("归因首次/末次排序必须仅按 target_id 分区，每个目标单独分配贡献。")
        ranks = [node for node in relevant if isinstance(node.this, exp.RowNumber)]
        if not ranks:
            issues.append("首次/末次归因必须按 target_id 使用 ROW_NUMBER()，并在外层仅保留第一条触点。")
        for node in ranks:
            orders = (node.args.get("order") or exp.Order()).expressions
            if not orders or _column_names(orders[0]) != {"touch_time"} or bool(orders[0].args.get("desc")) != (method == "last"):
                issues.append("首次归因必须按 touch_time 升序，末次归因必须降序；相同时间使用已配置稳定字段打破并列。")
        rank_aliases = {item.alias for select in selects for item in select.selects
                        if any(node is rank for node in item.walk() for rank in ranks)}
        if not any(
            isinstance(term, exp.EQ) and isinstance(term.this, exp.Column) and term.this.name in rank_aliases
            and isinstance(term.expression, exp.Literal) and term.expression.this == "1"
            for select in selects for predicate in [select.args.get("where"), select.args.get("qualify")]
            if predicate for term in predicate.find_all(exp.EQ)
        ):
            issues.append("首次/末次归因必须在排序后筛选触点序号 = 1，不能将全部触点计入贡献。")

    matches = [scope.expression for scope in matching_scopes]
    if not matches:
        issues.append("归因匹配层必须同时输出 target_id、target_time、touch_time 和 target_value。")
        return issues
    for select in matches:
        scope = next(scope for scope in matching_scopes if scope.expression is select)
        outputs = _outputs(scope) or {}
        output_names = {item.alias_or_name for item in select.selects}
        if not {"target_id", "touch_id", "target_time", "touch_time", "target_value"}.issubset(output_names):
            issues.append("归因匹配层必须保留目标值、目标/触点标识和事件时间，供后续权重计算使用。")
        predicates = [join.args.get("on") for join in select.args.get("joins") or []]
        if select.args.get("where"):
            predicates.append(select.args["where"].this)
        predicates = [item for item in predicates if item is not None]
        # Disjunctions cannot establish a mandatory window boundary.
        terms = [term for predicate in predicates for term in _conjuncts(predicate)]
        for index, group in enumerate(groups or []):
            projected = outputs.get(f"group_{index + 1}")
            time = outputs.get("touch_time" if group.get("attributionSide") == "touch" else "target_time")
            if isinstance(projected, exp.Alias):
                projected = projected.this
            if isinstance(time, exp.Alias):
                time = time.this
            if (isinstance(projected, exp.Column) and isinstance(time, exp.Column)
                    and _source(scope, projected) is not _source(scope, time)):
                issues.append(f"归因 group_{index + 1} 的字段来源必须与配置的 attributionSide 一致。")
        metric = config.get("targetMetric") or {}
        target_value = outputs.get("target_value")
        if target_value is not None and metric:
            value, value_scope, _ = _resolve_projection(target_value, scope)
            if metric.get("aggregation") == "count" and not (
                isinstance(value, exp.Literal) and value.is_number and float(value.this) == 1
            ):
                issues.append("归因总次数的每次目标 target_value 必须为 1。")
            elif metric.get("aggregation") == "sum":
                field = metric.get("metricField") or metric.get("metric_field") or {}
                if isinstance(field, dict):
                    field_name = str(field.get("sourceField") or field.get("field") or "").split(".")[-1]
                    physical = {column.name for column, _ in _metric_nodes(value, value_scope, exp.Column)}
                    if field_name and field_name not in physical:
                        issues.append("归因求和的 target_value 必须读取配置的目标数值属性，不能替换成次数或其他字段。")
        if not any(isinstance(term, exp.EQ) and isinstance(term.this, exp.Column)
                   and isinstance(term.expression, exp.Column) and term.this.name == term.expression.name == "entity_id"
                   and _source(scope, term.this) is not _source(scope, term.expression) for term in terms):
            issues.append("归因匹配必须按目标和触点的 entity_id 相等关联，不能跨主体分配贡献。")
        ordered = any(
            isinstance(term, (exp.LTE, exp.LT)) and isinstance(term.this, exp.Column) and term.this.name == "touch_time"
            and isinstance(term.expression, exp.Column) and term.expression.name == "target_time"
            or isinstance(term, (exp.GTE, exp.GT)) and isinstance(term.this, exp.Column) and term.this.name == "target_time"
            and isinstance(term.expression, exp.Column) and term.expression.name == "touch_time"
            for term in terms
        )
        if not ordered:
            issues.append("归因匹配必须强制 touch_time <= target_time，不能使用日期字段替代事件先后顺序。")
        if window.get("mode") == "same_day":
            same_day = any(_same_day_match(term, scope) for term in terms)
            if not same_day:
                issues.append("归因当天窗口必须强制 target_date = touch_date；当天不是过去 24 小时。")
        else:
            seconds = int(window.get("value") or 1) * {"day": 86400, "hour": 3600, "minute": 60}.get(window.get("unit", "day"), 0)
            bounded = any(_duration_bound(term, seconds) for term in terms)
            if not bounded:
                issues.append("归因自定义窗口必须对 touch_time 和 target_time 设置精确回溯时长边界。")
    touch_origins = [item for select in selects for item in select.selects if item.alias == "touch_id"]
    if not touch_origins:
        issues.append("归因 SQL 必须在关联前为每条触点保留 touch_id，供有效触发去重使用。")
    for item in touch_origins:
        owner = next((scope for scope in scopes if scope.expression is item.find_ancestor(exp.Select)), None)
        value = item.this
        if owner is not None and (owner.expression.args.get("distinct") or owner.expression.args.get("group")):
            issues.append("归因触点明细不能在分配 touch_id 时去重或聚合，必须保留每次触发。")
        if isinstance(value, exp.Column):
            continue
        if (owner is None or _depends_on_match(owner, matching_scopes)
                or not isinstance(value, exp.Window) or not isinstance(value.this, exp.RowNumber)
                or value.args.get("partition_by") or not value.args.get("order")):
            issues.append("归因 touch_id 必须来自事件唯一键或关联前的全局 ROW_NUMBER()，不能按用户时间去重或在匹配后编号。")
    return list(dict.fromkeys(issues))
