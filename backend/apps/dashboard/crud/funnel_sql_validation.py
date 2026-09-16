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
    "漏斗时间协议：使用 step_1 至 step_N CTE，每步输出 entity_id、first_step_time、step_time。"
    "step_1 的 first_step_time 和 step_time 都是实际事件时间的 MIN；后续步骤从 step_N-1 关联，"
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
            if not isinstance(step_value, exp.Min) or owner is not scope or kind is None:
                issues.append(f"漏斗 {name}.step_time 必须是当前步骤实际事件时间的 MIN，保留完整时间精度和声明的 epoch 单位。")
                previous = scope
                continue
            current = step_value.this
            if _time_kind(current, scope, fields, allow_aggregate=False) is None:
                issues.append(f"漏斗 {name} 必须从本步事件明细获取事件时间，不能复用前一步的聚合时间。")
            if index == 1:
                entity = outputs.get("entity_id")
                current_aliases = _input_aliases(current, scope)
                if (entity is None or not _configured_entity(entity, scope, entity_field, dialect)
                        or current_aliases is None or _input_aliases(entity, scope) != current_aliases):
                    issues.append("漏斗 step_1.entity_id 必须来自当前配置的主体字段，不能使用常量或其他字段代替。")
                if not _same(first, scope, step):
                    issues.append("漏斗 step_1.first_step_time 必须与 step_time 来自同一首次有效事件时间。")
                previous = scope
                continue
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
