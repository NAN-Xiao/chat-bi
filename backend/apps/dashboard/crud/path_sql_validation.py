"""Ensure path edges reuse the session sequence that supplies their step numbers."""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.dashboard_date_filter import _scan_sql_tokens
from apps.dashboard.crud.sql_generation_validation import _conjuncts, _metric_nodes, _outputs, _resolve_projection, _same_value
from apps.dashboard.crud.funnel_sql_validation import _configured_entity, _input_aliases, _metadata, _time_kind


PATH_SEQUENCE_RULE = (
    "路径边顺序协议：session_steps 先以 Schema 中明确 role=event_time 的完整事件时间 ASC 作为首排序，生成一次会话内 ROW_NUMBER() AS step_in_session；"
    "事件时间必须保留声明的时间单位和精度，不能用日期截断、倒序、事件名称或常量生成初始序号。"
    "后续生成 path_source/path_target 的 LAG/LEAD 必须在相同主体、session_id 及配置分组分区内，"
    "只使用 ORDER BY step_in_session ASC，且偏移只能为 1。"
    "禁止在边窗口重新 ORDER BY event_time/time/日期，即使与 ROW_NUMBER 写了相同时间排序也不允许，"
    "因为相同时间的记录可能被重新排列，使边挂到错误步骤，甚至给最后节点生成出边。"
    "LEAD 的源节点 path_step 直接使用这份 step_in_session；LAG 的源节点 path_step 使用同一序号减 1。"
    "序号必须在前一查询层生成并原样传递，不得另算 ROW_NUMBER 或用时间列冒充步骤序号。"
    "真实事件时间并列且节点身份不同时，只能使用已配置的稳定事件序号/唯一键确定先后；"
    "缺少这种配置时说明顺序无法确定，不得根据事件名称猜测业务顺序。"
    "初始事件是会话边界约束：在步骤编号后筛选 step_in_session=1 且事件等于 path.initialEvent 的有效会话，"
    "再按原步骤窗口的全部主体、会话和分组键 INNER JOIN 回完整 session_steps，保留后续节点。"
    "仅在参与事件 IN 列表中包含初始事件、筛选会话中任意一次该事件或声明未被结果使用的有效会话 CTE，都不能代替此约束。"
)


def _sequence(node: exp.Expression, scope: Scope):
    value, owner, _ = _resolve_projection(node, scope)
    if isinstance(value, exp.Window) and isinstance(value.this, exp.RowNumber):
        return value, owner, 0
    if isinstance(value, exp.Sub) and isinstance(value.expression, exp.Literal) and value.expression.this == "1":
        original = _sequence(value.this, owner)
        if original is not None and original[2] == 0:
            return original[0], original[1], -1
    return None


def _same_partitions(left: exp.Window, left_scope: Scope, right: exp.Window, right_scope: Scope) -> bool:
    unmatched = list(right.args.get("partition_by") or [])
    keys = list(left.args.get("partition_by") or [])
    if not keys or len(keys) != len(unmatched):
        return False
    for key in keys:
        index = next((i for i, candidate in enumerate(unmatched)
                      if _same_value(key, left_scope, candidate, right_scope)), None)
        if index is None:
            return False
        unmatched.pop(index)
    return True


def _anchor_predicates(scope: Scope, predicates: list, sequence, initial: dict,
                       dialect: str, alias: str | None = None, *, require_keys: bool = False) -> bool:
    """Prove first-position and configured-event tests constrain one session row."""
    first_aliases, event_aliases = set(), set()
    field = {"table": initial.get("eventTable") or initial.get("table"),
             "field": initial.get("eventNameField") or initial.get("field")}
    event_name = initial.get("eventName") or initial.get("event_name")
    for term in (term for predicate in predicates for term in _conjuncts(predicate)):
        if isinstance(term, exp.In) and len(term.expressions) == 1 and not term.args.get("query"):
            term = exp.EQ(this=term.this, expression=term.expressions[0])
        if not isinstance(term, exp.EQ):
            continue
        for value, literal in ((term.this, term.expression), (term.expression, term.this)):
            value_aliases = _input_aliases(value, scope)
            if (not isinstance(literal, exp.Literal) or not value_aliases or len(value_aliases) != 1
                    or alias is not None and value_aliases != {alias}):
                continue
            if literal.this == "1":
                position = _sequence(value, scope)
                if (position is not None and position[2] == 0
                        and position[0] is sequence[0] and position[1] is sequence[1]):
                    first_aliases.update(value_aliases)
            if literal.is_string and literal.this == event_name and _configured_entity(value, scope, field, dialect):
                event_aliases.update(value_aliases)
    anchors = first_aliases & event_aliases
    if not require_keys:
        return bool(anchors)
    # A relation cannot export another self-joined row's session keys after
    # testing the first event on its sibling scan.
    outputs = list((_outputs(scope) or {}).values())
    return any(all(any(_input_aliases(output, scope) == {candidate}
                       and _same_value(output, scope, key, sequence[1]) for output in outputs)
                   for key in sequence[0].args.get("partition_by") or []) for candidate in anchors)


def _anchor_relation(scope: Scope, sequence, initial: dict, dialect: str, seen=frozenset()) -> bool:
    if id(scope) in seen or scope.union_scopes:
        return False
    where = scope.expression.args.get("where")
    if where is not None and _anchor_predicates(scope, [where.this], sequence, initial, dialect, require_keys=True):
        return True
    sources = list(scope.selected_sources.values())
    return (len(sources) == 1 and isinstance(sources[0][1], Scope)
            and _anchor_relation(sources[0][1], sequence, initial, dialect, seen | {id(scope)}))


def _complete_session_join(scope: Scope, alias: str, terms: list, sequence) -> bool:
    """An eligible session cannot authorize another subject's same-numbered session."""
    partitions = sequence[0].args.get("partition_by") or []
    if not partitions:
        return False
    for key in partitions:
        matched = False
        for term in terms:
            if not isinstance(term, (exp.EQ, exp.NullSafeEQ)):
                continue
            for anchor, rows in ((term.this, term.expression), (term.expression, term.this)):
                other = _input_aliases(rows, scope)
                if (_input_aliases(anchor, scope) == {alias} and other and alias not in other
                        and _same_value(anchor, scope, key, sequence[1])
                        and _same_value(rows, scope, key, sequence[1])):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            return False
    return True


def _session_gate(scope: Scope, sequence, initial: dict, dialect: str) -> bool:
    where = scope.expression.args.get("where")
    for join in scope.expression.args.get("joins") or []:
        if join.side or join.kind not in {"", "INNER"}:
            continue  # LEFT JOIN alone does not filter unqualified sessions.
        alias = join.this.alias_or_name
        selected = scope.selected_sources.get(alias)
        source = selected[1] if selected is not None else None
        if not isinstance(source, Scope):
            continue
        predicates = [join.args.get("on"), where.this if where is not None else None]
        if not (_anchor_relation(source, sequence, initial, dialect)
                or _anchor_predicates(scope, predicates, sequence, initial, dialect, alias)):
            continue
        terms = [term for predicate in predicates for term in _conjuncts(predicate)]
        if _complete_session_join(scope, alias, terms, sequence):
            return True
    return False


def _gated_projection(node: exp.Expression, scope: Scope, window: exp.Window,
                      sequence, initial: dict, dialect: str, seen=frozenset()) -> bool:
    marker = (id(scope), id(node))
    if marker in seen:
        return False
    value, owner, path = _resolve_projection(node, scope)
    if any(_session_gate(parent, sequence, initial, dialect) for parent, _ in path):
        return True
    if value is window:
        order = window.args.get("order")
        if order is not None and len(order.expressions) == 1:
            _, _, sequence_path = _resolve_projection(order.expressions[0].this, owner)
            return any(_session_gate(parent, sequence, initial, dialect) for parent, _ in sequence_path)
        return False
    return any(_gated_projection(child, owner, window, sequence, initial, dialect, seen | {marker})
               for child in value.iter_expressions())


def path_sequence_issues(sql: str, dialect: str = "mysql", *, schema: str = "", path_config: dict | None = None) -> list[str]:
    tokens = set(re.findall(r"\{\{dashboard_[a-z0-9_]+\}\}", sql, flags=re.I))
    source, _ = _scan_sql_tokens(sql, {token: ":" + token[2:-2] for token in tokens})
    try:
        statements = sqlglot.parse(source, read=dialect or "mysql")
        if len(statements) != 1:
            raise ValueError("需要单个最终 SELECT")
        root = build_scope(statements[0])
        if root is None:
            raise ValueError("缺少最终 SELECT")
        outputs = _outputs(root) or {}
        step = outputs.get("path_step")
        sequence = _sequence(step, root) if step is not None else None
        if sequence is None:
            return ["路径 path_step 必须来自已生成的会话内 ROW_NUMBER 序号；LEAD 使用原序号，LAG 使用该序号减 1。"]
        issues = []
        path_config = path_config or {}
        initial = path_config.get("initialEvent") or path_config.get("initial_event") or {}
        if not isinstance(initial, dict) or not (initial.get("eventName") or initial.get("event_name")):
            issues.append("路径会话缺少有效初始事件配置，不能省略会话起点筛选。")
            initial = {}
        sequence_window, sequence_scope, _ = sequence
        original_order = (sequence_window.args.get("order") or exp.Order()).expressions
        fields = _metadata(schema)
        if not fields:
            issues.append("路径初始序号缺少当前授权表的事件时间元数据：请声明 role=event_time；数值时间还必须声明 epoch_seconds/epoch_milliseconds。")
        elif (not original_order or original_order[0].args.get("desc")
              or _time_kind(original_order[0].this, sequence_scope, fields, allow_aggregate=False) is None):
            issues.append("路径初始 ROW_NUMBER 必须以配置声明的完整事件时间 ASC 作为首排序；不能按事件名称、常量、日期截断或时间倒序生成步骤。")
        windows = [(name, window, scope)
                   for name in ("path_source", "path_target") if name in outputs
                   for window, scope in _metric_nodes(outputs[name], root, exp.Window)
                   if isinstance(window.this, (exp.Lag, exp.Lead))]
        if not windows:
            return [*issues, "路径相邻边必须由实际输出 path_source/path_target 的 LAG/LEAD 生成，不能仅在无关查询中出现窗口函数。"]
        for name, window, owner in windows:
            if initial and not _gated_projection(outputs[name], root, window, sequence, initial, dialect):
                issues.append("路径实际结果缺少初始事件会话约束：必须在步骤编号后选出 step_in_session=1 且事件等于配置初始事件的有效会话，再按全部主体、会话和分组键 INNER JOIN 回完整节点，保留向后的后续边。")
            ordered = (window.args.get("order") or exp.Order()).expressions
            sequence_order = _sequence(ordered[0].this, owner) if len(ordered) == 1 and not ordered[0].args.get("desc") else None
            if (sequence_order is None or sequence_order[2] != 0 or sequence_order[1] is owner
                    or sequence_order[0] is not sequence[0] or sequence_order[1] is not sequence[1]):
                issues.append("路径边 LAG/LEAD 必须只按前层已生成且与 path_step 同源的 step_in_session ASC 排序；不能再次按时间排序或重新编号。")
                continue
            if not _same_partitions(window, owner, sequence_order[0], sequence_order[1]):
                issues.append("路径边窗口必须保留生成步骤序号时的全部主体、会话及分组分区，不能跨会话或跨主体关联。")
            offset = window.this.args.get("offset")
            if offset is not None and not (isinstance(offset, exp.Literal) and offset.this == "1"):
                issues.append("路径相邻边的 LAG/LEAD 偏移必须为 1，不能跳过中间节点。")
            lag = isinstance(window.this, exp.Lag)
            if (name != ("path_source" if lag else "path_target") or sequence[2] != (-1 if lag else 0)):
                issues.append("路径 path_step 必须表示源节点：LEAD 目标边使用当前步骤序号，LAG 来源边使用当前步骤序号减 1。")
        return list(dict.fromkeys(issues))
    except (sqlglot.errors.SqlglotError, ValueError, TypeError) as exc:
        return [f"路径边顺序无法验证：{exc}。请先生成会话步骤序号，再按同一序号生成相邻边。"]
