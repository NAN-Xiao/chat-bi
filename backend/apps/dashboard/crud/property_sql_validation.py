"""Validate the closed compiler grammar, not arbitrary model-written SQL."""
import re

import sqlglot

from apps.dashboard.crud.property_sql_compiler import compile_property_sql
from apps.dashboard.crud.property_sql_plan import PropertyIssue, PropertySqlPlan


def property_result_contract_issues(sql: str, plan: PropertySqlPlan) -> list[PropertyIssue]:
    # Use stable typed sentinels for parsing controlled runtime placeholders.
    # Both ASTs are compared in full: fields, predicates, branches, dates,
    # aggregation grain, output order and row-preserving joins must agree.
    def parse(text):
        text = re.sub(r"\{\{dashboard_(?:start|end)(?:_exclusive)?_([a-z]+)\}\}",
                      lambda m: "20260901" if m[1] == "yyyymmdd" else "'2026-09-01'", text)
        statements = sqlglot.parse(text, read=plan.dialect)
        if len(statements) != 1 or statements[0] is None:
            raise ValueError("必须为单条查询")
        return statements[0]

    try:
        actual = parse(sql)
        expected = parse(compile_property_sql(plan))
        # Tokens themselves are part of the contract, not merely their sentinel.
        tokens = lambda text: re.findall(r"\{\{dashboard_[a-z_]+\}\}", text)
        if actual == expected and tokens(sql) == tokens(compile_property_sql(plan)):
            return []
    except (ValueError, sqlglot.errors.SqlglotError):
        pass
    return [PropertyIssue("PROPERTY_SQL_CONTRACT_FAILED", "sql",
                          "SQL 与属性配置的字段、条件、聚合粒度或结果列不一致，请检查编译配置。")]
