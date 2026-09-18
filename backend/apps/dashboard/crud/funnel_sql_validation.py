"""Verify the explicit funnel step protocol against declared event timestamps."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.dashboard_date_filter import _scan_sql_tokens, dashboard_date_parameter_tokens
from apps.dashboard.crud.sql_generation_validation import _conjuncts, _outputs, _resolve_projection, _source, _select_expression_columns
from apps.dashboard.crud.event_sql_contract import _field_expression, _unquoted


FUNNEL_TIMING_RULE = (
    "漏斗时间协议：步骤必须按配置顺序匹配，窗口相对每个候选首步计算，同一主体取可完成的最大深度。"
    "仅当数据源明确为支持 window_funnel 的 AnalyticDB for MySQL 时可使用原生函数；其他数据源使用 step_1 至 step_N CTE，"
    "每步输出 entity_id、first_step_time、step_time。step_1 必须为每次首步事件保留一行，first_step_time 和 step_time 都使用该候选首步的实际事件时间，"
    "禁止先按主体 MIN(event_time) 压缩成唯一最早首步；后续步骤从 step_N-1 关联，"
    "原样传递 first_step_time，并以 MIN(本步实际事件时间) 输出 step_time。"
    "本步明细必须满足 event_time >= 前步.step_time，且窗口始终相对前步.first_step_time。"
    "每一步的 entity_id 必须来自配置主体；后续步骤必须用本步事件主体 = 前步.entity_id 连接，不能用其他事件扫描的主体条件代替。"
    "事件时间只能来自当前表 Schema 声明 role=event_time 的字段；分区日期只用于日期范围过滤，不能代替事件时间。"
    "BIGINT 必须声明 encoding=epoch_seconds 或 epoch_milliseconds；缺失角色或编码时明确报告缺少配置，禁止猜测。"
    "duration 按实际时间戳比较：原始 epoch 使用事件时间差 <= 配置秒数乘声明单位倍率；"
    "TIMESTAMP/DATETIME 使用 event_time <= first_step_time + 精确配置时长，天固定转成 86400 秒，"
    "禁止 DATE/DATEDIFF 或截断的 TIMESTAMPDIFF 代替精确时长。"
    "same_day 使用实际时间戳转成自然日后与 first_step_time 的自然日相等，同时保留完整时间戳先后比较。"
)


def funnel_sql_compatibility_issues(sql: str, dialect="mysql") -> list[str]:
    """Reject value-window constructs that AnalyticDB MySQL cannot plan over funnel aggregates."""
    if str(dialect or "mysql").strip().lower() not in {"mysql", "analyticdb", "adb"}:
        return []
    source = re.sub(r"\{\{[^{}]+}}", "0", str(sql or ""))
    try:
        statements = sqlglot.parse(source, read="mysql")
    except sqlglot.errors.SqlglotError:
        return []
    if any(
        isinstance(window.this, (exp.Max, exp.Lag))
        for statement in statements
        for window in statement.find_all(exp.Window)
    ):
        return [
            "MySQL/AnalyticDB 漏斗禁止在 step_counts 聚合结果上使用 MAX/LAG 窗口函数；"
            "请使用 step_counts 的标量子查询或等价单行关联取得第一步和上一步人数。"
        ]
    return []


def _number(node: exp.Expression | None) -> Decimal | None:
    if isinstance(node, exp.Literal):
        try:
            return Decimal(node.this)
        except InvalidOperation:
            return None
    if isinstance(node, (exp.Paren, exp.Neg)):
        value = _number(node.this)
        return -value if value is not None and isinstance(node, exp.Neg) else value
    if isinstance(node, (exp.Mul, exp.Div, exp.Add, exp.Sub)):
        left, right = _number(node.this), _number(node.expression)
        if left is not None and right is not None:
            if isinstance(node, exp.Mul):
                return left * right
            if isinstance(node, exp.Div):
                return left / right if right else None
            return left + right if isinstance(node, exp.Add) else left - right
    return None


def _metadata(schema: str) -> dict[tuple[str, str], str]:
    """Read table-qualified roles, never infer an epoch unit from a field name."""
    fields: dict[tuple[str, str], str] = {}
    table = ""
    for line in str(schema or "").splitlines():
        header = re.match(r"\s*#\s*Table:\s*([^,\s]+)", line, re.I)
        if header:
            table = header[1].replace('`', '').replace('"', '').lower()
            continue
        field = re.match(r"\s*\(([^:]+):([^,]+),\s*(.*)\)\s*,?\s*$", line)
        if not table or not field or not re.search(r"\brole\s*=\s*event_time\b", field[3], re.I):
            continue
        declared = re.search(r"\bencoding\s*=\s*(\w+)", field[3], re.I)
        encoding = declared[1].lower() if declared else ""
        if not encoding and re.match(r"(?:timestamp|datetime)\b", field[2].strip(), re.I):
            encoding = "native_timestamp"
        if encoding in {"epoch_seconds", "epoch_milliseconds", "native_timestamp"}:
            fields[(table, field[1].strip(' `"').lower())] = encoding
    return fields


def _time_kind(node: exp.Expression, scope: Scope, fields: dict, seen=frozenset(), *, allow_aggregate=True) -> str | None:
    node, scope, _ = _resolve_projection(node, scope)
    marker = (id(scope), id(node))
    if marker in seen:
        return None
    seen = seen | {marker}
    if isinstance(node, exp.Min):
        return _time_kind(node.this, scope, fields, seen) if allow_aggregate else None
    if isinstance(node, exp.Column):
        source = _source(scope, node)
        if not isinstance(source, exp.Table):
            return None
        table = ".".join(part for part in (source.catalog, source.db, source.name) if part).lower()
        encoding = fields.get((table, node.name.lower()))
        return {"epoch_seconds": "seconds", "epoch_milliseconds": "milliseconds", "native_timestamp": "timestamp"}.get(encoding)
    if isinstance(node, exp.UnixToTime):
        value, owner, _ = _resolve_projection(node.this, scope)
        if _time_kind(value, owner, fields, seen, allow_aggregate=allow_aggregate) == "seconds":
            return "timestamp"
        if isinstance(value, exp.Div) and _number(value.expression) == 1000:
            # PostgreSQL's integer division would discard milliseconds.
            decimal_divisor = isinstance(value.expression, exp.Literal) and "." in value.expression.this
            if not value.args.get("typed") or decimal_divisor:
                if _time_kind(value.this, owner, fields, seen, allow_aggregate=allow_aggregate) == "milliseconds":
                    return "timestamp"
    return None


def _same(node: exp.Expression, scope: Scope, reference: exp.Expression) -> bool:
    return _same_timing_value(node, scope, reference, scope)


def _same_timing_value(left: exp.Expression, left_scope: Scope, right: exp.Expression, right_scope: Scope) -> bool:
    if isinstance(left, exp.Column) and isinstance(right, exp.Column) and left_scope is right_scope:
        if _source(left_scope, left) is not _source(right_scope, right):
            return False
        if left.table and right.table and left.table != right.table:
            return False  # Self-joined event CTE aliases contain different event occurrences.
    left, left_scope, _ = _resolve_projection(left, left_scope)
    right, right_scope, _ = _resolve_projection(right, right_scope)
    # MIN of the same physical timestamp in different step scopes is not the
    # same event: each scope has different event predicates and prior matches.
    if type(left) is not type(right):
        return False
    if isinstance(left, (exp.AggFunc, exp.Window)) and left_scope is not right_scope:
        return False
    if isinstance(left, exp.Column):
        return left.name == right.name and _source(left_scope, left) is _source(right_scope, right)
    for key in left.arg_types:
        a, b = left.args.get(key), right.args.get(key)
        if isinstance(a, exp.Expression) and isinstance(b, exp.Expression):
            if not _same_timing_value(a, left_scope, b, right_scope):
                return False
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b) or any(
                not _same_timing_value(x, left_scope, y, right_scope)
                if isinstance(x, exp.Expression) and isinstance(y, exp.Expression) else x != y
                for x, y in zip(a, b)
            ):
                return False
        elif a != b:
            return False
    return True


def _configured_entity(node: exp.Expression, scope: Scope, field: dict, dialect: str) -> bool:
    """Resolve the declared subject without accepting a same-named different table."""
    expected = _field_expression(field, dialect)
    if expected is None:
        return False
    node, owner, _ = _resolve_projection(node, scope)
    columns = _select_expression_columns(node)
    table = str(field.get("table") or field.get("eventTable") or "")
    if not table or not columns:
        return False
    for column in columns:
        source = _source(owner, column)
        if not isinstance(source, exp.Table):
            return False
        actual = ".".join(part for part in (source.catalog, source.db, source.name) if part)
        if (actual if "." in table else source.name) != table:
            return False
    return _unquoted(node) == _unquoted(expected)


def _input_aliases(node: exp.Expression, scope: Scope) -> set[str] | None:
    """Keep each joined occurrence distinct even when aliases reuse one CTE."""
    aliases = set()
    for column in _select_expression_columns(node):
        source = _source(scope, column)
        matches = [name for name, (_, candidate) in scope.selected_sources.items()
                   if candidate is source and (not column.table or name == column.table)]
        if len(matches) != 1:
            return None
        aliases.add(matches[0])
    return aliases or None


def _entity_chain_valid(scope: Scope, terms: list[exp.Expression], current: exp.Expression,
                        prior_entity: exp.Expression, output: exp.Expression | None,
                        field: dict, dialect: str) -> bool:
    if output is None:
        return False
    current_aliases = _input_aliases(current, scope)
    if current_aliases is None:
        return False
    for term in terms:
        if not isinstance(term, exp.EQ):
            continue
        for subject, prior in ((term.this, term.expression), (term.expression, term.this)):
            if (_same(prior, scope, prior_entity)
                    and _input_aliases(subject, scope) == current_aliases
                    and _configured_entity(subject, scope, field, dialect)
                    and (_same(output, scope, prior_entity) or _same(output, scope, subject))):
                return True
    return False


def _seconds(node: exp.Expression) -> Decimal | None:
    # Calendar DAY arithmetic can cross a DST boundary; elapsed days are
    # represented by 86400 seconds (or 24 hours) in the generation protocol.
    units = {"SECOND": 1, "MINUTE": 60, "HOUR": 3600}
    value = _number(node.this if isinstance(node, exp.Interval) else node.expression)
    unit = str(node.args.get("unit") or "").upper().rstrip("S")
    return value * units[unit] if value is not None and unit in units else None


def _duration(term: exp.Expression, scope: Scope, current: exp.Expression,
              first: exp.Expression, kind: str, seconds: int) -> bool:
    if not isinstance(term, (exp.LTE, exp.GTE)):
        return False
    value, limit = (term.this, term.expression) if isinstance(term, exp.LTE) else (term.expression, term.this)
    if kind in {"seconds", "milliseconds"}:
        maximum = seconds * (1000 if kind == "milliseconds" else 1)
        if isinstance(value, exp.Sub) and _number(limit) == maximum:
            return _same(value.this, scope, current) and _same(value.expression, scope, first)
        if _same(value, scope, current) and isinstance(limit, exp.Add):
            return _same(limit.this, scope, first) and _number(limit.expression) == maximum
    if kind == "timestamp" and _same(value, scope, current):
        if isinstance(limit, (exp.DateAdd, exp.TimestampAdd)):
            return _same(limit.this, scope, first) and _seconds(limit) == seconds
        if isinstance(limit, exp.Add) and isinstance(limit.expression, exp.Interval):
            return _same(limit.this, scope, first) and _seconds(limit.expression) == seconds
    return False


def _day_of(node: exp.Expression, scope: Scope, reference: exp.Expression, fields: dict) -> bool:
    node, owner, _ = _resolve_projection(node, scope)
    if not (isinstance(node, (exp.Date, exp.TsOrDsToDate))
            or isinstance(node, exp.Cast) and node.to.is_type(exp.DataType.Type.DATE)):
        return False
    value = node.this
    if _time_kind(value, owner, fields) != "timestamp":
        return False
    reference_kind = _time_kind(reference, scope, fields)
    if reference_kind in {"seconds", "milliseconds"} and isinstance(value, exp.UnixToTime):
        value = value.this
        if reference_kind == "milliseconds" and isinstance(value, exp.Div) and _number(value.expression) == 1000:
            value = value.this
    return _same_timing_value(value, owner, reference, scope)


def _window_funnel_calls(root: Scope) -> list[tuple[Scope, exp.Anonymous]]:
    calls: list[tuple[Scope, exp.Anonymous]] = []
    for scope in root.traverse():
        if not isinstance(scope.expression, exp.Select):
            continue
        for node in scope.expression.find_all(exp.Anonymous):
            if (
                node.name.lower() == "window_funnel"
                and node.find_ancestor(exp.Select) is scope.expression
            ):
                calls.append((scope, node))
    return calls


def _window_seconds(expression: exp.Expression | None) -> int | None:
    if isinstance(expression, exp.Cast):
        expression = expression.this
    value = _number(expression)
    if value is None or value != value.to_integral_value():
        return None
    return int(value)


def _configured_step_event_matches(
        condition: exp.Expression,
        scope: Scope,
        step: dict,
        dialect: str,
        required_source: tuple[exp.Table, tuple[tuple[int, str], ...]] | None = None,
) -> bool:
    event = step.get("event") if isinstance(step.get("event"), dict) else {}
    event_name = str(event.get("eventName") or event.get("event_name") or "").strip()
    event_field = {
        "table": event.get("eventTable") or event.get("table"),
        "field": event.get("eventNameField") or event.get("field"),
    }
    if not event_name or not event_field["table"] or not event_field["field"]:
        return False
    for term in _conjuncts(condition):
        if not isinstance(term, exp.EQ):
            continue
        for field_value, literal_value in (
            (term.this, term.expression),
            (term.expression, term.this),
        ):
            if (
                isinstance(literal_value, exp.Literal)
                and literal_value.is_string
                and str(literal_value.this) == event_name
                and _configured_entity(field_value, scope, event_field, dialect)
                and (
                    required_source is None
                    or _same_source_reference(
                        _configured_entity_source(field_value, scope, event_field, dialect),
                        required_source,
                    )
                )
            ):
                return True
    return False


def _selected_source_alias(
        scope: Scope,
        column: exp.Column,
        source: exp.Table | Scope,
) -> str | None:
    matches = [
        str(name).lower()
        for name, (_node, candidate) in scope.selected_sources.items()
        if candidate is source and (not column.table or str(name).lower() == str(column.table).lower())
    ]
    return matches[0] if len(matches) == 1 else None


def _column_source_trace(
        column: exp.Column,
        scope: Scope,
        seen: frozenset[tuple[int, str, str]] = frozenset(),
) -> tuple[exp.Table, tuple[tuple[int, str], ...]] | None:
    marker = (id(scope), str(column.table).lower(), str(column.name).lower())
    if marker in seen:
        return None
    source = _source(scope, column)
    if not isinstance(source, (exp.Table, Scope)):
        return None
    alias = _selected_source_alias(scope, column, source)
    if alias is None:
        return None
    edge = (id(scope), alias)
    if isinstance(source, exp.Table):
        return source, (edge,)
    outputs = _outputs(source) or {}
    projection = next(
        (value for name, value in outputs.items() if str(name).lower() == str(column.name).lower()),
        None,
    )
    if projection is None:
        return None
    traced = _expression_source_reference(projection, source, seen | {marker})
    if traced is None:
        return None
    table, path = traced
    return table, (edge, *path)


def _expression_source_reference(
        expression: exp.Expression,
        scope: Scope,
        seen: frozenset[tuple[int, str, str]] = frozenset(),
) -> tuple[exp.Table, tuple[tuple[int, str], ...]] | None:
    columns = _select_expression_columns(expression)
    traces = [_column_source_trace(column, scope, seen) for column in columns]
    if not traces or any(trace is None for trace in traces):
        return None
    first = traces[0]
    if first is None:
        return None
    if any(
        trace is None or trace[0] is not first[0] or trace[1] != first[1]
        for trace in traces[1:]
    ):
        return None
    return first


def _same_source_reference(
        left: tuple[exp.Table, tuple[tuple[int, str], ...]] | None,
        right: tuple[exp.Table, tuple[tuple[int, str], ...]] | None,
) -> bool:
    return (
        left is not None
        and right is not None
        and left[0] is right[0]
        and left[1] == right[1]
    )


def _configured_entity_source(
        expression: exp.Expression,
        scope: Scope,
        field: dict,
        dialect: str,
) -> tuple[exp.Table, tuple[tuple[int, str], ...]] | None:
    if not _configured_entity(expression, scope, field, dialect):
        return None
    return _expression_source_reference(expression, scope)


def _event_time_source(
        expression: exp.Expression,
        scope: Scope,
        fields: dict[tuple[str, str], str],
) -> tuple[exp.Table, tuple[tuple[int, str], ...]] | None:
    reference = _expression_source_reference(expression, scope)
    expression, owner, _ = _resolve_projection(expression, scope)
    matches: dict[int, exp.Table] = {}
    for column in _select_expression_columns(expression):
        resolved, column_owner, _ = _resolve_projection(column, owner)
        if not isinstance(resolved, exp.Column):
            continue
        source = _source(column_owner, resolved)
        if not isinstance(source, exp.Table):
            continue
        table = ".".join(part for part in (source.catalog, source.db, source.name) if part).lower()
        if (table, resolved.name.lower()) in fields:
            matches[id(source)] = source
    if len(matches) != 1 or reference is None or reference[0] is not next(iter(matches.values())):
        return None
    return reference


def _fixed_timestamp_origin(expression: exp.Expression | None) -> bool:
    while isinstance(expression, (exp.Alias, exp.Paren, exp.Cast)):
        expression = expression.this
    return isinstance(expression, exp.Literal)


def _window_timestamp_is_bigint_seconds(
        expression: exp.Expression,
        scope: Scope,
        fields: dict[tuple[str, str], str],
) -> bool:
    expression, owner, _ = _resolve_projection(expression, scope)
    if _time_kind(expression, owner, fields) == "seconds":
        return True
    if isinstance(expression, exp.Cast) and expression.to.is_type(
        exp.DataType.Type.BIGINT,
        exp.DataType.Type.INT,
    ):
        value = expression.this
        if _time_kind(value, owner, fields) == "seconds":
            return True
        if (
            isinstance(value, exp.Div)
            and _number(value.expression) == 1000
            and _time_kind(value.this, owner, fields) == "milliseconds"
        ):
            return True
    if (
        isinstance(expression, exp.TimestampDiff)
        and str(expression.args.get("unit") or "").upper() == "SECOND"
        and _fixed_timestamp_origin(expression.expression)
        and _time_kind(expression.this, owner, fields) == "timestamp"
    ):
        return True
    return False


def _reachable_input_scopes(scope: Scope) -> list[Scope]:
    reachable: list[Scope] = []
    pending = [scope]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        reachable.append(current)
        pending.extend(
            source
            for _node, source in current.selected_sources.values()
            if isinstance(source, Scope)
        )
    return reachable


def _resolves_to_dashboard_parameter(
        expression: exp.Expression | None,
        scope: Scope,
        parameter_name: str,
) -> bool:
    expression, _owner, _ = _resolve_projection(expression, scope)
    while isinstance(expression, (exp.Alias, exp.Paren, exp.Cast)):
        expression = expression.this
    return isinstance(expression, exp.Placeholder) and str(expression.this).lower() == parameter_name.lower()


def _configured_partition_range_applied(
        call_scope: Scope,
        partition_field: dict,
        dialect: str,
        start_parameter: str,
        end_parameter: str,
        event_source: tuple[exp.Table, tuple[tuple[int, str], ...]],
) -> bool:
    lower_bound = False
    upper_bound = False
    for scope in _reachable_input_scopes(call_scope):
        if not isinstance(scope.expression, exp.Select):
            continue
        predicates: list[exp.Expression] = []
        where = scope.expression.args.get("where")
        if where is not None:
            predicates.append(where.this if isinstance(where, exp.Where) else where)
        for join in scope.expression.args.get("joins") or []:
            side = str(join.args.get("side") or "").strip().upper()
            on = join.args.get("on")
            if side in {"", "INNER"} and on is not None:
                predicates.append(on)
        terms = [term for predicate in predicates for term in _conjuncts(predicate)]
        for term in terms:
            if isinstance(term, exp.Between):
                if (
                    not _configured_entity(term.this, scope, partition_field, dialect)
                    or not _source_reference_is_event_path_suffix(
                        _configured_entity_source(term.this, scope, partition_field, dialect),
                        event_source,
                    )
                ):
                    continue
                lower_bound = lower_bound or _resolves_to_dashboard_parameter(
                    term.args.get("low"), scope, start_parameter,
                )
                upper_bound = upper_bound or _resolves_to_dashboard_parameter(
                    term.args.get("high"), scope, end_parameter,
                )
                continue
            if not isinstance(term, (exp.GTE, exp.LTE)):
                continue
            left, right = term.this, term.expression
            if isinstance(term, exp.GTE):
                lower_field, lower_value = left, right
                upper_value, upper_field = left, right
            else:
                lower_value, lower_field = left, right
                upper_field, upper_value = left, right
            lower_bound = lower_bound or (
                _configured_entity(lower_field, scope, partition_field, dialect)
                and _source_reference_is_event_path_suffix(
                    _configured_entity_source(lower_field, scope, partition_field, dialect),
                    event_source,
                )
                and _resolves_to_dashboard_parameter(lower_value, scope, start_parameter)
            )
            upper_bound = upper_bound or (
                _configured_entity(upper_field, scope, partition_field, dialect)
                and _source_reference_is_event_path_suffix(
                    _configured_entity_source(upper_field, scope, partition_field, dialect),
                    event_source,
                )
                and _resolves_to_dashboard_parameter(upper_value, scope, end_parameter)
            )
    return lower_bound and upper_bound


def _source_reference_is_event_path_suffix(
        candidate: tuple[exp.Table, tuple[tuple[int, str], ...]] | None,
        event_source: tuple[exp.Table, tuple[tuple[int, str], ...]],
) -> bool:
    if candidate is None or candidate[0] is not event_source[0]:
        return False
    candidate_path = candidate[1]
    event_path = event_source[1]
    return len(candidate_path) <= len(event_path) and event_path[-len(candidate_path):] == candidate_path


def _trace_output_to_union(
        scope: Scope,
        output_name: str,
) -> tuple[Scope, str] | None:
    seen: set[tuple[int, str]] = set()
    while True:
        marker = (id(scope), output_name.lower())
        if marker in seen:
            return None
        seen.add(marker)
        projection = (_outputs(scope) or {}).get(output_name)
        while isinstance(projection, (exp.Alias, exp.Paren)):
            projection = projection.this
        if not isinstance(projection, exp.Column):
            return None
        source = _source(scope, projection)
        if not isinstance(source, Scope):
            return None
        if not _select_preserves_source_rows(scope, source):
            return None
        if source.union_scopes:
            return source, projection.name
        scope = source
        output_name = projection.name


def _select_preserves_source_rows(scope: Scope, source: Scope) -> bool:
    if not isinstance(scope.expression, exp.Select):
        return False
    selected_sources = [candidate for _node, candidate in scope.selected_sources.values()]
    if len(selected_sources) != 1 or selected_sources[0] is not source:
        return False
    return not any(
        scope.expression.args.get(name)
        for name in (
            "joins",
            "where",
            "having",
            "group",
            "qualify",
            "distinct",
            "limit",
            "offset",
        )
    )


def _union_leaf_scopes(scope: Scope) -> list[Scope]:
    if not scope.union_scopes:
        return [scope]
    leaves: list[Scope] = []
    for child in scope.union_scopes:
        leaves.extend(_union_leaf_scopes(child))
    return leaves


def _union_tree_preserves_all_rows(scope: Scope) -> bool:
    if scope.union_scopes:
        if (
            not isinstance(scope.expression, exp.Union)
            or scope.expression.args.get("distinct") is not False
            or scope.expression.args.get("limit")
            or scope.expression.args.get("offset")
        ):
            return False
        return all(_union_tree_preserves_all_rows(child) for child in scope.union_scopes)
    if not isinstance(scope.expression, exp.Select):
        return False
    return not any(
        scope.expression.args.get(name)
        for name in ("qualify", "limit", "offset")
    )


def _depth_threshold(
        condition: exp.Expression,
        scope: Scope,
        call_scope: Scope,
        depth_alias: str,
) -> int | None:
    if isinstance(condition, exp.GTE):
        depth, threshold = condition.this, condition.expression
    elif isinstance(condition, exp.LTE):
        threshold, depth = condition.this, condition.expression
    else:
        return None
    if (
        isinstance(depth, exp.Column)
        and depth.name.lower() == depth_alias.lower()
        and _source(scope, depth) is call_scope
    ):
        value = _number(threshold)
        if value is not None and value == value.to_integral_value():
            return int(value)
    return None


def _counted_depth_threshold(
        projection: exp.Expression,
        scope: Scope,
        call_scope: Scope,
        depth_alias: str,
) -> int | None:
    while isinstance(projection, (exp.Alias, exp.Paren)):
        projection = projection.this
    if not isinstance(projection, exp.Count) or projection.args.get("distinct"):
        return None
    case = projection.this
    if (
        not isinstance(case, exp.Case)
        or case.this is not None
        or len(case.args.get("ifs") or []) != 1
    ):
        return None
    default = case.args.get("default")
    if default is not None and not isinstance(default, exp.Null):
        return None
    branch = case.args["ifs"][0]
    if _number(branch.args.get("true")) != 1:
        return None
    return _depth_threshold(branch.this, scope, call_scope, depth_alias)


def _depth_counts_feed_final_output(
        root: Scope,
        call_scope: Scope,
        depth_alias: str,
        step_count: int,
) -> tuple[bool, set[int]]:
    traced = _trace_output_to_union(root, "step_count")
    order_traced = _trace_output_to_union(root, "step_order")
    if traced is None or order_traced is None:
        return False, set()
    union_scope, count_name = traced
    order_union_scope, order_name = order_traced
    if order_union_scope is not union_scope:
        return False, set()
    union_outputs = list((_outputs(union_scope) or {}).keys())
    if count_name not in union_outputs or order_name not in union_outputs:
        return False, set()
    count_index = union_outputs.index(count_name)
    order_index = union_outputs.index(order_name)
    if not _union_tree_preserves_all_rows(union_scope):
        return False, set()
    leaves = _union_leaf_scopes(union_scope)
    if len(leaves) != step_count:
        return False, set()
    thresholds: set[int] = set()
    for leaf in leaves:
        if not isinstance(leaf.expression, exp.Select):
            return False, thresholds
        selected_sources = [source for _node, source in leaf.selected_sources.values()]
        if (
            len(selected_sources) != 1
            or selected_sources[0] is not call_scope
            or leaf.expression.args.get("joins")
            or leaf.expression.args.get("where")
            or leaf.expression.args.get("having")
            or leaf.expression.args.get("group")
        ):
            return False, thresholds
        projections = leaf.expression.selects
        if max(count_index, order_index) >= len(projections):
            return False, thresholds
        order = projections[order_index]
        while isinstance(order, (exp.Alias, exp.Paren)):
            order = order.this
        threshold = _counted_depth_threshold(
            projections[count_index], leaf, call_scope, depth_alias,
        )
        if threshold is None or _number(order) != threshold:
            return False, thresholds
        thresholds.add(threshold)
    return thresholds == set(range(1, step_count + 1)), thresholds


def native_window_funnel_issues(
        sql: str,
        funnel: dict,
        time_config: dict,
        schema: str,
        dialect: str = "mysql",
) -> list[str]:
    """校验 AnalyticDB window_funnel 与当前漏斗配置、Schema 和日期边界一致。"""
    issues: list[str] = []
    fields = _metadata(schema)
    window = funnel.get("window") if isinstance(funnel.get("window"), dict) else {}
    if window.get("mode") != "duration":
        issues.append("window_funnel 仅适用于 duration 窗口；same_day 必须生成自然日约束的等价 SQL。")
    related_property = funnel.get("relatedProperty") or funnel.get("related_property")
    if (
        funnel.get("relatedPropertyEnabled") is True
        or funnel.get("related_property_enabled") is True
        or isinstance(related_property, dict) and related_property.get("enabled") is True
    ):
        issues.append("启用关联属性的漏斗不能使用原生 window_funnel 路径，必须使用逐步 CTE 保持同一属性值关联。")
    expected_seconds = int(window.get("value") or 0) * {
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }.get(str(window.get("unit") or ""), 0)
    tokens = dashboard_date_parameter_tokens(
        time_config.get("date_parameter_type") or time_config.get("dateParameterType")
    ) or []
    if tokens and any(token.lower() not in str(sql or "").lower() for token in tokens):
        issues.append("漏斗 SQL 必须成对使用当前配置的看板起止日期参数。")
    source, _ = _scan_sql_tokens(sql, {token: ":" + token[2:-2] for token in tokens})
    try:
        statements = sqlglot.parse(source, read=dialect or "mysql")
        if len(statements) != 1:
            raise ValueError("需要单个最终查询")
        root = build_scope(statements[0])
        if root is None:
            raise ValueError("需要可验证的 SELECT")
        calls = _window_funnel_calls(root)
        if len(calls) != 1:
            issues.append("漏斗 SQL 必须且只能包含一个 window_funnel 聚合。")
            return list(dict.fromkeys(issues))

        call_scope, call = calls[0]
        arguments = list(call.expressions)
        configured_steps = [step for step in funnel.get("steps") or [] if isinstance(step, dict)]
        if len(arguments) != 3 + len(configured_steps):
            issues.append("window_funnel 必须按配置步骤顺序提供完整且不重复的事件条件。")
            return list(dict.fromkeys(issues))

        if expected_seconds <= 0 or _window_seconds(arguments[0]) != expected_seconds:
            issues.append("window_funnel 的窗口秒数必须严格由 funnel.window 配置换算，不能使用示例中的固定窗口。")
        if not isinstance(arguments[1], exp.Literal) or not arguments[1].is_string or str(arguments[1].this).lower() != "default":
            issues.append("window_funnel 必须使用文档规定的 default 模式。")
        event_source = _event_time_source(arguments[2], call_scope, fields)
        if not fields or event_source is None or not _window_timestamp_is_bigint_seconds(arguments[2], call_scope, fields):
            issues.append(
                "window_funnel 的 timestamp 必须解析到 Schema 声明的 role=event_time 字段，"
                "并按 AnalyticDB 契约提供 BIGINT 秒值；毫秒时间必须除以 1000 后显式转换为整数，"
                "TIMESTAMPDIFF 必须使用所有事件共享的固定起点。"
            )

        entity_field = funnel.get("entityField") or funnel.get("entity_field") or {}
        group = call_scope.expression.args.get("group")
        if (
            not isinstance(group, exp.Group)
            or len(group.expressions) != 1
            or not _configured_entity(group.expressions[0], call_scope, entity_field, dialect)
            or event_source is None
            or not _same_source_reference(
                _configured_entity_source(group.expressions[0], call_scope, entity_field, dialect),
                event_source,
            )
        ):
            issues.append("window_funnel 必须按漏斗配置的分析主体分组计算最大完成深度。")
        if any(
            call_scope.expression.args.get(name)
            for name in ("having", "qualify", "limit", "offset")
        ):
            issues.append(
                "window_funnel 主体最大深度聚合层不能使用 HAVING、QUALIFY、LIMIT 或 OFFSET "
                "筛除已经计算的主体；业务筛选必须在事件明细进入聚合前应用。"
            )

        for index, (condition, step) in enumerate(zip(arguments[3:], configured_steps), start=1):
            if not _configured_step_event_matches(
                condition,
                call_scope,
                step,
                dialect,
                required_source=event_source,
            ):
                issues.append(f"window_funnel 第 {index} 个事件条件必须对应配置中的第 {index} 个步骤。")

        parent = call.parent
        depth_alias = parent.alias if isinstance(parent, exp.Alias) else ""
        if not depth_alias:
            issues.append("window_funnel 结果必须定义最大完成深度别名，供各步骤累计计数。")
        else:
            counts_valid, counted_thresholds = _depth_counts_feed_final_output(
                root,
                call_scope,
                depth_alias,
                len(configured_steps),
            )
            for threshold in range(1, len(configured_steps) + 1):
                if threshold not in counted_thresholds:
                    issues.append(
                        f"漏斗第 {threshold} 步人数必须按 {depth_alias} >= {threshold} 统计，不能只统计恰好停在该深度的主体。"
                    )
            if not counts_valid:
                issues.append(
                    "漏斗最终 step_count 必须来自可达的 window_funnel 最大深度结果，"
                    "并使用 COUNT(CASE WHEN max_depth >= step_order THEN 1 END) 只统计匹配主体；"
                    "最终 step_order 必须与对应计数分支保持同一血缘。"
                )

        partition_field = time_config.get("field") if isinstance(time_config.get("field"), dict) else {}
        if tokens and (
            not partition_field
            or len(tokens) != 2
            or event_source is None
            or not _configured_partition_range_applied(
                call_scope,
                partition_field,
                dialect,
                tokens[0][2:-2],
                tokens[1][2:-2],
                event_source,
            )
        ):
            issues.append("漏斗 SQL 必须使用配置的日期或分区字段应用看板起止日期范围。")
        return list(dict.fromkeys(issues))
    except (sqlglot.errors.SqlglotError, ValueError, TypeError) as exc:
        issues.append(f"window_funnel 协议无法验证：{exc}。请按平台漏斗 Data Skill 重写查询。")
        return list(dict.fromkeys(issues))


def funnel_timing_issues(sql: str, funnel: dict, time_config: dict, schema: str, dialect="mysql") -> list[str]:
    fields = _metadata(schema)
    if not fields:
        return ["漏斗缺少可用的事件时间元数据：请在当前工作空间声明 role=event_time；数值时间还必须声明 epoch_seconds/epoch_milliseconds，不能使用分区日期代替。"]
    tokens = dashboard_date_parameter_tokens(time_config.get("date_parameter_type") or time_config.get("dateParameterType")) or []
    source, _ = _scan_sql_tokens(sql, {token: ":" + token[2:-2] for token in tokens})
    try:
        statements = sqlglot.parse(source, read=dialect or "mysql")
        if len(statements) != 1:
            raise ValueError("需要单个最终查询")
        root = build_scope(statements[0])
        if root is None:
            raise ValueError("需要可验证的 SELECT")
        scopes = list(root.traverse())
        steps = {scope.expression.parent.alias_or_name: scope for scope in scopes
                 if isinstance(scope.expression.parent, exp.CTE)}
        reachable = set()

        def visit(scope):
            if id(scope) in reachable:
                return
            reachable.add(id(scope))
            for child in [*scope.union_scopes, *(item for _, item in scope.selected_sources.values() if isinstance(item, Scope))]:
                visit(child)

        visit(root)
        issues = []
        previous = None
        entity_field = funnel.get("entityField") or funnel.get("entity_field") or {}
        window = funnel.get("window") or {}
        seconds = int(window.get("value") or 1) * {"day": 86400, "hour": 3600, "minute": 60}.get(window.get("unit", "day"), 0)
        for index in range(1, len(funnel.get("steps") or []) + 1):
            name = f"step_{index}"
            scope = steps.get(name)
            if scope is None or id(scope) not in reachable:
                issues.append(f"漏斗必须通过实际参与结果计算的 {name} CTE 保留完整步骤链。")
                previous = None
                continue
            outputs = _outputs(scope) or {}
            first, step = outputs.get("first_step_time"), outputs.get("step_time")
            if first is None or step is None:
                issues.append(f"漏斗 {name} 必须输出 first_step_time 和 step_time 以校验首步窗口和精确顺序。")
                previous = scope
                continue
            step_value, owner, _ = _resolve_projection(step, scope)
            kind = _time_kind(step, scope, fields)
            if index == 1:
                current = step
                while isinstance(current, (exp.Alias, exp.Paren)):
                    current = current.this
                if (
                    kind is None
                    or isinstance(step_value, (exp.AggFunc, exp.Window))
                    or any(
                        scope.expression.args.get(clause)
                        for clause in ("group", "having", "qualify", "distinct")
                    )
                ):
                    issues.append(
                        "漏斗 step_1 必须为每个候选首步事件保留一行，并直接使用该事件的实际时间；"
                        "禁止按主体 GROUP BY 后用 MIN(event_time) 只保留最早首步。"
                    )
                entity = outputs.get("entity_id")
                current_aliases = _input_aliases(current, scope)
                if (entity is None or not _configured_entity(entity, scope, entity_field, dialect)
                        or current_aliases is None or _input_aliases(entity, scope) != current_aliases):
                    issues.append("漏斗 step_1.entity_id 必须来自当前配置的主体字段，不能使用常量或其他字段代替。")
                if not _same(first, scope, step):
                    issues.append("漏斗 step_1.first_step_time 必须与 step_time 来自同一首次有效事件时间。")
                previous = scope
                continue
            if not isinstance(step_value, exp.Min) or owner is not scope or kind is None:
                issues.append(f"漏斗 {name}.step_time 必须是当前步骤实际事件时间的 MIN，保留完整时间精度和声明的 epoch 单位。")
                previous = scope
                continue
            current = step_value.this
            if _time_kind(current, scope, fields, allow_aggregate=False) is None:
                issues.append(f"漏斗 {name} 必须从本步事件明细获取事件时间，不能复用前一步的聚合时间。")
            aliases = [alias for alias, (_, child) in scope.selected_sources.items() if child is previous]
            if previous is None or len(aliases) != 1:
                issues.append(f"漏斗 {name} 必须关联 step_{index - 1} 的已完成主体，不能独立计算。")
                previous = scope
                continue
            prior_time = exp.column("step_time", table=aliases[0])
            first_time = exp.column("first_step_time", table=aliases[0])
            if not _same(first, scope, first_time):
                issues.append(f"漏斗 {name} 必须原样保留步骤 1 的 first_step_time，不能把窗口起点重置为前一步。")
            predicates = [join.args.get("on") for join in scope.expression.args.get("joins") or [] if not join.side]
            where = scope.expression.args.get("where")
            predicates += [where.this] if where is not None else []
            terms = [term for predicate in predicates for term in _conjuncts(predicate)]
            if not _entity_chain_valid(scope, terms, current, exp.column("entity_id", table=aliases[0]),
                                       outputs.get("entity_id"), entity_field, dialect):
                issues.append(f"漏斗 {name} 必须用本步实际事件的配置主体 = 前步.entity_id 限制同一主体，并原样输出该主体；其他扫描、OR 条件或仅时间条件不能构成主体连接。")
            ordered = any(
                isinstance(term, exp.GTE) and _same(term.this, scope, current) and _same(term.expression, scope, prior_time)
                or isinstance(term, exp.LTE) and _same(term.this, scope, prior_time) and _same(term.expression, scope, current)
                for term in terms)
            if not ordered or _time_kind(prior_time, scope, fields) != kind:
                issues.append(f"漏斗 {name} 必须按完整事件时间强制本步 event_time >= 前步 step_time，不能仅比较日期。")
            if window.get("mode") == "same_day":
                bounded = any(isinstance(term, exp.EQ) and (
                    _day_of(term.this, scope, current, fields) and _day_of(term.expression, scope, first_time, fields)
                    or _day_of(term.expression, scope, current, fields) and _day_of(term.this, scope, first_time, fields)) for term in terms)
            else:
                bounded = any(_duration(term, scope, current, first_time, kind, seconds) for term in terms)
            if not bounded:
                issues.append(f"漏斗 {name} 必须按配置窗口相对步骤 1 的 first_step_time 限制整链；duration 使用精确经过时长，same_day 使用相同自然日，禁止日期差或逐步重置窗口。")
            previous = scope
        return list(dict.fromkeys(issues))
    except (sqlglot.errors.SqlglotError, ValueError, TypeError) as exc:
        return [f"漏斗时间协议无法验证：{exc}。请使用保留 first_step_time、step_time 的逐步 CTE。"]
