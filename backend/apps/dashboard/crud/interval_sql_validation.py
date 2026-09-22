"""Keep interval result dates attached to the event occurrence that starts the pair."""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.dashboard_date_filter import _scan_sql_tokens
from apps.dashboard.crud.sql_generation_validation import _outputs, _source
from apps.dashboard.crud.event_sql_contract import _implies, _physical_tables, _unquoted
from apps.dashboard.crud.interval_sql_compiler import exact_percentile_expression


INTERVAL_START_DATE_RULE = (
    "间隔日期来源协议：最终 interval_date 必须沿配对起点事件的日期来源传递，"
    "并与实际 interval_seconds 时差中的 start_time 来自同一事件行。"
    "同事件相邻自连接以 prev 为起点时必须输出 prev 的日期；LAG 起点时间必须配合同分区、同排序、同偏移的 LAG 起点日期，"
    "LEAD 终点配对则保留当前起点日期。不同事件最短配对必须保留获选起点的日期，不能使用终点日期。"
    "别名不能改变这一职责；跨自然日配对仍全部归到起点日。"
)


def _projection(scope: Scope, name: str) -> exp.Expression | None:
    outputs = _outputs(scope)
    if outputs is not None:
        return outputs.get(name)
    # A single SELECT * is an exact pass-through, even without a physical
    # schema inventory. Never choose between ambiguous star sources.
    explicit = [item for item in scope.expression.selects if not item.is_star and item.alias_or_name == name]
    if explicit:
        return explicit[0] if len(explicit) == 1 else None
    stars = [item for item in scope.expression.selects if item.is_star]
    aliases = [alias for star in stars for alias in scope.selected_sources
               if not isinstance(star, exp.Column) or not star.table or star.table == alias]
    return exp.column(name, table=aliases[0]) if len(aliases) == 1 else None


def _expanded(node: exp.Expression, scope: Scope, path=(), seen=frozenset()) -> exp.Expression:
    if isinstance(node, (exp.Alias, exp.Paren)):
        return _expanded(node.this, scope, path, seen)
    if isinstance(node, exp.Column):
        source = _source(scope, node)
        aliases = [alias for alias, (_, candidate) in scope.selected_sources.items()
                   if candidate is source and (not node.table or alias == node.table)]
        if len(aliases) != 1:
            raise ValueError(f"无法唯一确定字段 {node.sql()} 的事件来源")
        next_path = (*path, (id(scope), aliases[0]))
        if isinstance(source, Scope):
            marker = (id(source), node.name)
            projection = _projection(source, node.name)
            if marker in seen or projection is None or source.union_scopes:
                raise ValueError(f"字段 {node.sql()} 缺少唯一可追溯的配对来源")
            return _expanded(projection, source, next_path, seen | {marker})
        if not isinstance(source, exp.Table):
            raise ValueError(f"字段 {node.sql()} 不是可验证的事件字段")
        result = node.copy()
        result.meta["interval_row_origin"] = next_path
        return result
    if isinstance(node, exp.Query):
        raise ValueError("日期和时差必须在同一配对结果上计算，不能从标量子查询猜测来源")
    result = node.copy()
    for key, value in node.args.items():
        if isinstance(value, exp.Expression):
            result.set(key, _expanded(value, scope, path, seen))
        elif isinstance(value, list):
            result.set(key, [_expanded(item, scope, path, seen) if isinstance(item, exp.Expression) else item for item in value])
    return result


def _signature(node):
    if isinstance(node, exp.Column):
        return ("column", node.meta.get("interval_row_origin"), node.name)
    if isinstance(node, exp.Expression):
        return (type(node).__name__, tuple((key, _signature(value)) for key, value in sorted(node.args.items())))
    if isinstance(node, list):
        return tuple(_signature(value) for value in node)
    return node


def _origins(node: exp.Expression, selectors=()) -> set[tuple]:
    if isinstance(node, exp.Column):
        origin = node.meta.get("interval_row_origin")
        return {(origin, selectors)} if origin is not None else set()
    if isinstance(node, exp.Window):
        if not isinstance(node.this, (exp.Lag, exp.Lead)):
            raise ValueError("配对起点日期不能由另一个聚合或序号窗口代替")
        selector = node.copy()
        selector.this.set("this", exp.Null())
        if selector.this.args.get("offset") is None:
            selector.this.set("offset", exp.Literal.number(1))
        if selector.this.args.get("default") is None:
            selector.this.set("default", exp.Null())
        return _origins(node.this.this, (*selectors, _signature(selector)))
    result = set()
    for child in node.iter_expressions():
        result.update(_origins(child, selectors))
    return result


def _duration_starts(node: exp.Expression):
    if isinstance(node, (exp.TimestampDiff, exp.DateDiff)):
        yield node.expression
        return
    if isinstance(node, exp.Sub):
        try:
            if _origins(node.this) and _origins(node.expression):
                yield node.expression
                return
        except ValueError:
            pass
    for child in node.iter_expressions():
        yield from _duration_starts(child)


def _fact_date_projection(root: Scope, projection: exp.Expression) -> exp.Expression:
    date = projection.unalias().unnest()
    if not isinstance(date, exp.Column):
        return projection
    source = _source(root, date)
    if not isinstance(source, Scope) or _physical_tables(source):
        return projection
    candidates = []
    for join in root.expression.args.get("joins") or []:
        predicate = join.args.get("on")
        if join.side != "LEFT" or predicate is None:
            continue
        alias = join.this.alias_or_name
        for equality in predicate.find_all(exp.EQ):
            if not _implies(predicate, equality):
                continue
            for left, right in ((equality.this, equality.expression), (equality.expression, equality.this)):
                if left == date and isinstance(right, exp.Column) and right.table == alias:
                    candidates.append(right)
    if len(candidates) != 1:
        raise ValueError("补齐日期必须通过唯一的 LEFT JOIN 等值条件连接实际配对起点日期")
    return candidates[0]


def has_exact_interval_percentiles(sql: str, dialect: str) -> bool:
    source = re.sub(r"\{\{dashboard_[a-z0-9_]+\}\}", "0", sql, flags=re.I)
    try:
        root = build_scope(sqlglot.parse_one(source, read=dialect))
        if root is None:
            return False
        for scope in root.traverse():
            outputs = _outputs(scope) or {}
            aliases = [("0.75", "p75_interval_seconds"), ("0.50", "median_interval_seconds"), ("0.25", "p25_interval_seconds")]
            if not all(name in outputs and _unquoted(outputs[name].unalias()) == _unquoted(sqlglot.parse_one(exact_percentile_expression(quantile), read=dialect))
                       for quantile, name in aliases):
                continue
            sources = list(scope.selected_sources.values())
            if len(sources) != 1 or not isinstance(sources[0][1], Scope):
                continue
            ranking = sources[0][1]
            group = scope.expression.args.get("group")
            if group is None:
                continue
            partition = ", ".join(item.sql(dialect=dialect) for item in group.expressions)
            expected = {
                "percentile_position": f"ROW_NUMBER() OVER (PARTITION BY {partition} ORDER BY interval_seconds)",
                "percentile_count": f"COUNT(*) OVER (PARTITION BY {partition})",
            }
            if all((projection := _projection(ranking, name)) is not None
                   and _unquoted(projection.unalias()) == _unquoted(sqlglot.parse_one(expression, read=dialect))
                   for name, expression in expected.items()):
                return True
        return False
    except (sqlglot.errors.SqlglotError, ValueError, TypeError):
        return False


def interval_start_date_issues(sql: str, dialect: str = "mysql") -> list[str]:
    tokens = set(re.findall(r"\{\{dashboard_[a-z0-9_]+\}\}", sql, flags=re.I))
    source, _ = _scan_sql_tokens(sql, {token: ":" + token[2:-2] for token in tokens})
    try:
        statements = sqlglot.parse(source, read=dialect or "mysql")
        if len(statements) != 1:
            raise ValueError("需要单个最终 SELECT")
        root = build_scope(statements[0])
        if root is None or root.union_scopes:
            raise ValueError("需要明确的配对统计结果")
        outputs = _outputs(root) or {}
        if "interval_date" not in outputs:
            raise ValueError("缺少最终 interval_date")
        date_origins = _origins(_expanded(_fact_date_projection(root, outputs["interval_date"]), root))
        if len(date_origins) != 1:
            raise ValueError("interval_date 必须来自唯一的起点事件行")
        issues = []
        for name in ("max_interval_seconds", "min_interval_seconds", "avg_interval_seconds",
                     "p75_interval_seconds", "median_interval_seconds", "p25_interval_seconds"):
            if name not in outputs:
                continue  # The fixed output contract reports missing measures.
            starts = list(_duration_starts(_expanded(outputs[name], root)))
            if not starts or any(_origins(start) != date_origins for start in starts):
                issues.append(f"间隔 {name} 的时差起点与 interval_date 来源不一致或无法追溯；日期必须来自实际 start_time 的同一事件行及相同 LAG/LEAD 偏移，不能取终点日期。")
        return list(dict.fromkeys(issues))
    except (sqlglot.errors.SqlglotError, ValueError, TypeError) as exc:
        return [f"间隔起点日期无法验证：{exc}。请在配对层明确保留起点日期并原样传递到最终分组。"]
