"""Prove that unobserved cohort periods remain NULL in the final SQL output."""
from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens, _scan_sql_tokens
from apps.dashboard.crud.sql_generation_validation import _outputs, _source


COHORT_MATURITY_RULE = (
    "Cohort 成熟窗口是结果协议的一部分：每列 day_N 都必须使用最外层 CASE WHEN <实际 cohort_date + N 天> "
    "<= <解析为 DATE 的看板结束参数> THEN <按配置计算的当日指标> ELSE NULL END；"
    "timestamp 使用排他的 dashboard_end_exclusive_timestamp，条件必须改为 <。"
    "YYYYMMDD 结束参数须先使用当前方言的 STR_TO_DATE/TO_DATE 解析，不能直接进行日期比较。"
    "截止日只来自 result_contract.maturity.observation_end_token，不能使用系统当前时间、硬编码日期或行为记录最大日期。"
    "未成熟单元格保留 NULL；已成熟但无回访/计数事件的单元格保留真实 0。"
    "如果需要 COALESCE，必须放在 CASE 的已成熟 THEN 分支内；不能在 CASE 外用 COALESCE/IFNULL/COUNT 将 NULL 变成 0。"
)


def cohort_maturity_contract(time_config: dict[str, Any]) -> dict[str, Any]:
    parameter_type = str(time_config.get("date_parameter_type") or time_config.get("dateParameterType") or "")
    tokens = dashboard_date_parameter_tokens(parameter_type)
    return {
        "cohort_date_column": "cohort_date",
        "observation_end_token": tokens[1] if tokens else None,
        "date_parameter_type": parameter_type,
        "end_inclusive": parameter_type != "timestamp",
        "period_unit": "day",
        "immature_value": None,
        "observed_empty_count": 0,
        "rule": "每个 day_N 必须在 cohort_date + N 天已到达观察截止日时才计算；未成熟返回 NULL。观察截止日来自配置的看板结束参数，不能用系统时间、硬编码日期或回访记录最大日期替代。",
    }


def _expanded(node: exp.Expression, scope: Scope, seen=frozenset()) -> exp.Expression:
    if isinstance(node, (exp.Alias, exp.Paren)):
        return _expanded(node.this, scope, seen)
    if isinstance(node, exp.Column):
        source = _source(scope, node)
        marker = (id(source), node.name)
        if isinstance(source, Scope) and marker not in seen:
            projection = (_outputs(source) or {}).get(node.name)
            if projection is not None and not source.union_scopes:
                result = _expanded(projection, source, seen | {marker})
                alias = node.table or next(name for name, (_, candidate) in scope.selected_sources.items() if candidate is source)
                for column in result.find_all(exp.Column):
                    column.set("table", exp.to_identifier(f"ref_{id(scope)}_{alias}_{column.table}"))
                return result
        if source is None or isinstance(source, Scope):
            raise ValueError(f"无法唯一确定字段 {node.sql()} 的来源")
        # Preserve physical-source identity, including self-join aliases.
        result = node.copy()
        result.set("table", exp.to_identifier(f"source_{id(scope)}_{id(source)}"))
        return result
    if isinstance(node, (exp.Subquery, exp.Select, exp.Window)):
        raise ValueError("成熟窗口必须在输出行的 Cohort 粒度计算，不能跨查询或窗口猜测字段来源")
    result = node.copy()
    for key, value in node.args.items():
        if isinstance(value, exp.Expression):
            result.set(key, _expanded(value, scope, seen))
        elif isinstance(value, list):
            result.set(key, [_expanded(item, scope, seen) if isinstance(item, exp.Expression) else item for item in value])
    return result


def _integer(node: exp.Expression | None) -> int | None:
    if isinstance(node, exp.Neg):
        value = _integer(node.this)
        return -value if value is not None else None
    if isinstance(node, exp.Literal):
        try:
            return int(node.this)
        except (TypeError, ValueError):
            pass
    return None


def _unwrapped(node: exp.Expression) -> exp.Expression:
    while isinstance(node, (exp.Paren, exp.Alias)):
        node = node.this
    return node


def _end_date(node: exp.Expression, contract: dict) -> bool:
    node = _unwrapped(node)
    if isinstance(node, (exp.Min, exp.Max)):
        # Only aggregate an expression proven to be the constant configured
        # endpoint. MAX(event_date) is not the observation boundary.
        return _end_date(node.this, contract)
    parameter = str(contract["observation_end_token"])[2:-2]
    if contract["date_parameter_type"] in {"yyyymmdd_number", "yyyymmdd_text"}:
        if not isinstance(node, exp.StrToDate) or node.args.get("format") != exp.Literal.string("%Y%m%d"):
            return False
        node = node.this
        if isinstance(node, exp.Cast):
            node = node.this
    else:
        if isinstance(node, exp.Cast) and node.to.is_type(exp.DataType.Type.DATE):
            node = node.this
        elif isinstance(node, exp.Date):
            node = node.this
        elif contract["date_parameter_type"] == "timestamp":
            return False
    return isinstance(node, exp.Placeholder) and node.this == parameter


def _linear_date(node: exp.Expression, cohort: exp.Expression, contract: dict) -> tuple[int, int, int] | None:
    """Represent supported date arithmetic as cohort, cutoff and whole-day coefficients."""
    node = _unwrapped(node)
    if node == cohort:
        return (1, 0, 0)
    if _end_date(node, contract):
        return (0, 1, 0)
    if isinstance(node, exp.Cast) and node.to.is_type(exp.DataType.Type.DATE):
        return _linear_date(node.this, cohort, contract)
    value = _integer(node)
    if value is not None:
        return (0, 0, value)
    if isinstance(node, exp.Interval) and str(node.args.get("unit") or "").upper() in {"DAY", "DAYS"}:
        value = _integer(node.this)
        return (0, 0, value) if value is not None else None
    if isinstance(node, (exp.DateAdd, exp.DateSub)):
        if str(node.args.get("unit") or "DAY").upper() not in {"DAY", "DAYS"}:
            return None
        base, days = _linear_date(node.this, cohort, contract), _integer(node.expression)
        if base is not None and days is not None:
            return (base[0], base[1], base[2] + (-days if isinstance(node, exp.DateSub) else days))
    if isinstance(node, (exp.Add, exp.Sub, exp.DateDiff)):
        if isinstance(node, exp.DateDiff) and str(node.args.get("unit") or "DAY").upper() not in {"DAY", "DAYS"}:
            return None
        left, right = _linear_date(node.this, cohort, contract), _linear_date(node.expression, cohort, contract)
        if left is not None and right is not None:
            sign = 1 if isinstance(node, exp.Add) else -1
            return tuple(a + sign * b for a, b in zip(left, right))
    return None


def _immature_truth(node: exp.Expression, cohort: exp.Expression, contract: dict, day: int) -> bool | None:
    node = _unwrapped(node)
    if isinstance(node, exp.Not):
        value = _immature_truth(node.this, cohort, contract, day)
        return None if value is None else not value
    if isinstance(node, (exp.And, exp.Or)):
        values = [_immature_truth(child, cohort, contract, day) for child in (node.this, node.expression)]
        decisive = False if isinstance(node, exp.And) else True
        if decisive in values:
            return decisive
        return None if None in values else not decisive
    if not isinstance(node, (exp.LT, exp.LTE, exp.GT, exp.GTE)):
        return None
    left, right = _linear_date(node.this, cohort, contract), _linear_date(node.expression, cohort, contract)
    if left is None or right is None:
        return None
    a, b, offset = (x - y for x, y in zip(left, right))
    if (a, b) not in {(-1, 1), (1, -1)}:
        return None
    operator = type(node)
    if b == -1:
        offset = -offset
        operator = {exp.LT: exp.GT, exp.LTE: exp.GTE, exp.GT: exp.LT, exp.GTE: exp.LTE}[operator]
    # Date differences are integral. Normalize every supported comparison to
    # delta >= threshold (mature) or delta < threshold (immature).
    threshold = -offset + (1 if operator in {exp.GT, exp.LTE} else 0)
    expected = day + (0 if contract["end_inclusive"] else 1)
    if threshold != expected:
        return None
    return operator in {exp.LT, exp.LTE}


def _null_when_immature(node: exp.Expression | None, cohort: exp.Expression, contract: dict, day: int) -> bool:
    if node is None or isinstance(node, exp.Null):
        return True
    node = _unwrapped(node)
    if isinstance(node, exp.Case):
        if node.this is not None:  # Only searched CASE makes the predicate explicit.
            return False
        for branch in node.args.get("ifs") or []:
            truth = _immature_truth(branch.this, cohort, contract, day)
            if truth is not False and not _null_when_immature(branch.args.get("true"), cohort, contract, day):
                return False
            if truth is True:
                return True
        return _null_when_immature(node.args.get("default"), cohort, contract, day)
    if isinstance(node, exp.If):
        truth = _immature_truth(node.this, cohort, contract, day)
        return ((truth is False or _null_when_immature(node.args.get("true"), cohort, contract, day))
                and (truth is True or _null_when_immature(node.args.get("false"), cohort, contract, day)))
    if isinstance(node, exp.Coalesce):
        return all(_null_when_immature(child, cohort, contract, day) for child in [node.this, *node.expressions])
    if isinstance(node, (exp.Cast, exp.Round, exp.Neg, exp.Abs, exp.Nullif, exp.Sum, exp.Avg, exp.Min, exp.Max)):
        return _null_when_immature(node.this, cohort, contract, day)
    if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
        return any(_null_when_immature(child, cohort, contract, day) for child in (node.this, node.expression))
    return False


def cohort_maturity_issues(sql: str, time_config: dict, days: int, dialect: str = "mysql") -> list[str]:
    contract = cohort_maturity_contract(time_config)
    if not contract["observation_end_token"]:
        return ["Cohort 成熟窗口缺少有效日期参数类型，请明确观察截止日期配置。"]
    tokens = dashboard_date_parameter_tokens(contract["date_parameter_type"])
    source, _ = _scan_sql_tokens(sql, {token: ":" + token[2:-2] for token in tokens})
    try:
        statements = sqlglot.parse(source, read=dialect or "mysql")
        if len(statements) != 1:
            raise ValueError("需要单个最终 SELECT")
        scope = build_scope(statements[0])
        if scope is None or scope.union_scopes:
            raise ValueError("需要可确定 Cohort 输出列的最终 SELECT")
        outputs = _outputs(scope) or {}
        if "cohort_date" not in outputs:
            raise ValueError("缺少最终 cohort_date 输出列")
        cohort = _expanded(outputs["cohort_date"], scope)
        if isinstance(cohort, exp.TimeToStr) and cohort.args.get("format") == exp.Literal.string("%Y-%m-%d"):
            cohort = cohort.this
            if isinstance(cohort, exp.TsOrDsToTimestamp):
                cohort = cohort.this
        issues = []
        for day in range(days + 1):
            name = f"day_{day}"
            if name not in outputs:
                issues.append(f"Cohort 成熟窗口无法校验缺失的最终输出列 {name}。")
                continue
            value = _expanded(outputs[name], scope)
            has_guard = any(_immature_truth(node, cohort, contract, day) is not None for node in value.walk())
            if not has_guard or not _null_when_immature(value, cohort, contract, day):
                issues.append(f"Cohort {name} 缺少有效成熟窗口：必须用实际 cohort_date + {day} 天与解析为 DATE 的 {contract['observation_end_token']} 比较，未到观察日返回 NULL；禁止外层 COALESCE/IFNULL/COUNT 将未成熟值变为 0。")
        return issues
    except (sqlglot.errors.SqlglotError, ValueError, TypeError) as exc:
        return [f"Cohort 成熟窗口无法验证：{exc}。请用明确的日期来源与 CASE 输出每个 day_N。"]
