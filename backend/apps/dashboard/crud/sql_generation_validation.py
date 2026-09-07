"""Structural checks for generated dashboard SQL, without executing business queries."""
from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope


def _outputs(scope: Scope) -> dict[str, exp.Expression] | None:
    query = scope.expression
    if scope.outer_columns:
        return dict(zip(scope.outer_columns, query.selects))
    if any(item.is_star for item in query.selects):
        return None
    return {item.alias_or_name: item for item in query.selects}


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
    for scope in traverse_scope(statement):
        sources = {name: source for name, (_, source) in scope.selected_sources.items()}
        for column in scope.columns:
            if column.is_star:
                continue
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


def attribution_structure_issues(statement: exp.Expression, config: dict) -> list[str]:
    """Validate the explicit target/touch result contract used by generation and repair."""
    issues: list[str] = []
    method = str(config.get("method") or "linear")
    window = config.get("window") or {}
    selects = list(statement.find_all(exp.Select))
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
                      and item.alias != "target_id"]
    relevant = [node for node in weight_windows if isinstance(node.this, exp.Count)] if method == "linear" else weight_windows
    if not relevant or any(
        {col.name for part in node.args.get("partition_by") or [] for col in part.find_all(exp.Column)} != {"target_id"}
        for node in relevant
    ):
        issues.append("归因触点计数或首次/末次排序必须仅按 target_id 分区，每个目标单独分配贡献。")
    if method == "linear":
        weights = [item for select in selects for item in select.selects if item.alias == "linear_weight"]
        fractions = [node for item in weights for node in item.find_all(exp.Div)]
        if not fractions or any(
            not isinstance(node.this, exp.Literal) or str(node.this.this) not in {"1", "1.0"}
            or not isinstance(node.expression, exp.Nullif)
            or _column_names(node.expression.this) != {"touch_count"}
            for node in fractions
        ):
            issues.append("归因 linear_weight 必须为 1.0 / NULLIF(touch_count, 0)，目标值只能在汇总时乘一次。")
        if any(isinstance(node.this, exp.Count) and isinstance(node.this.this, exp.Star) for node in relevant):
            issues.append("归因 touch_count 必须统计非空触点时间，不能用 COUNT(*) 将 LEFT JOIN 空行算作触点。")
    else:
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

    matches = [select for select in selects if select.args.get("joins") and any(item.alias_or_name == "touch_time" for item in select.selects)
               and any(item.alias_or_name == "target_time" for item in select.selects)]
    if not matches:
        issues.append("归因匹配层必须同时输出 target_id、target_time、touch_time 和 target_value。")
        return issues
    for select in matches:
        output_names = {item.alias_or_name for item in select.selects}
        if not {"target_id", "target_time", "target_value", "target_date", "touch_date"}.issubset(output_names):
            issues.append("归因匹配层必须保留目标值、事件时间和自然日字段，供后续权重计算使用。")
        predicates = [join.args.get("on") for join in select.args.get("joins") or []]
        if select.args.get("where"):
            predicates.append(select.args["where"].this)
        predicates = [item for item in predicates if item is not None]
        # Disjunctions cannot establish a mandatory window boundary.
        terms: list[exp.Expression] = []
        def conjunction(node: exp.Expression) -> None:
            if isinstance(node, exp.And):
                conjunction(node.this)
                conjunction(node.expression)
            elif isinstance(node, exp.Paren):
                conjunction(node.this)
            else:
                terms.append(node)
        for predicate in predicates:
            conjunction(predicate)
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
            same_day = any(isinstance(term, exp.EQ) and (
                isinstance(term.this, exp.Column) and isinstance(term.expression, exp.Column)
                and {term.this.name, term.expression.name} == {"target_date", "touch_date"}
            ) for term in terms)
            if not same_day:
                issues.append("归因当天窗口必须强制 target_date = touch_date；当天不是过去 24 小时。")
        else:
            seconds = int(window.get("value") or 1) * {"day": 86400, "hour": 3600, "minute": 60}.get(window.get("unit", "day"), 0)
            bounded = any(_duration_bound(term, seconds) for term in terms)
            if not bounded:
                issues.append("归因自定义窗口必须对 touch_time 和 target_time 设置精确回溯时长边界。")
    return list(dict.fromkeys(issues))
