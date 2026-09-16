"""Compile declared model output identifiers into configured display aliases.

Bindings are established before generation. No position, similarity or guessed
field mapping is permitted when binding the returned SELECT.
"""
from copy import deepcopy
import re

import sqlglot
from sqlglot import exp


def generation_plan(plan: dict, dialect: str) -> dict:
    result = deepcopy(plan)
    bindings = plan.get("output_bindings") or {}
    contract = result.get("result_contract") or {}
    if contract.get("required_columns"):
        contract["quoted_output_columns"] = [exp.to_identifier(name, quoted=True).sql(dialect=dialect) for name in contract["required_columns"]]
    if not bindings:
        return result
    names = {configured: internal for internal, configured in bindings.items()}
    contract = result["result_contract"]
    for key in ("required_columns", "metric_fields", "group_fields", "final_grain"):
        contract[key] = [names.get(value, value) for value in contract.get(key, [])]
    contract["date_field"] = names.get(contract.get("date_field"), contract.get("date_field"))
    for metric in [*contract.get("metrics", []), *contract.get("formula_metrics", [])]:
        metric["alias"] = names.get(metric["alias"], metric["alias"])
    contract["quoted_output_columns"] = [exp.to_identifier(name, quoted=True).sql(dialect=dialect) for name in contract["required_columns"]]
    result["output_binding_instruction"] = (
        "模型 SQL 的最终 SELECT 只使用 output_bindings 的英文键作为输出别名；中文显示名由程序按此映射统一引用和输出。"
        "必须完整保留所有键，不输出显示名，不猜测其他字段，不增加结果列。"
    )
    return result


def bind_output_columns(sql: str, bindings: dict[str, str], dialect: str) -> tuple[str, list[str]]:
    if not bindings:
        return sql, []
    if len(set(bindings.values())) != len(bindings):
        return sql, ["图表配置存在重复的输出名称，请为指标和维度配置不同名称。"]
    tokens = set(re.findall(r"\{\{dashboard_[a-z0-9_]+\}\}", sql))
    source = sql
    for token in tokens:
        source = source.replace(token, ":" + token[2:-2])
    try:
        statements = sqlglot.parse(source, read=dialect)
    except sqlglot.errors.SqlglotError:
        return sql, []  # The syntax validator reports the precise location.
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return sql, ["请使用单个外层 SELECT 按 output_bindings 输出配置结果。"]
    query = statements[0]
    outputs = query.named_selects
    if len(outputs) != len(set(outputs)) or set(outputs) != set(bindings):
        return sql, [f"模型结果键不匹配：必须输出 {list(bindings)!r}，实际为 {outputs!r}；显示名称由程序绑定，不能自行改名。"]
    for projection in query.expressions:
        name = projection.alias_or_name
        if isinstance(projection, exp.Alias):
            projection.set("alias", exp.to_identifier(bindings[name], quoted=True))
        else:
            projection.replace(exp.alias_(projection.copy(), bindings[name], quoted=True))
    for key in ("order", "group", "having", "qualify"):
        clause = query.args.get(key)
        if clause is None:
            continue
        # Aggregate arguments and nested queries resolve source columns, not
        # this SELECT's output aliases. Never rename across those boundaries.
        for column in clause.walk(prune=lambda node: isinstance(node, (exp.AggFunc, exp.Query))):
            if not isinstance(column, exp.Column):
                continue
            if not column.table and column.name in bindings:
                column.set("this", exp.to_identifier(bindings[column.name], quoted=True))
    rendered = query.sql(dialect=dialect, pretty=True)
    for token in tokens:
        rendered = rendered.replace(":" + token[2:-2], token)
    return rendered, []
