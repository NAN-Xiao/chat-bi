"""Validate the complete deterministic retention grammar against its resolved plan."""
import re

import sqlglot

from apps.dashboard.crud.retention_sql_compiler import compile_retention_sql


def retention_result_contract_issues(sql, plan):
    if plan is None:
        return ["留存查询计划缺失，无法校验 SQL。"]

    def parse(text):
        text = re.sub(r"\{\{dashboard_[a-z_]+\}\}",
                      lambda m: "20260901" if "yyyymmdd" in m[0] else "'2026-09-01'", text)
        statements = sqlglot.parse(text, read=plan.dialect)
        if len(statements) != 1 or statements[0] is None:
            raise ValueError("必须为单条 SQL")
        return statements[0]

    try:
        expected = compile_retention_sql(plan)
        tokens = lambda text: re.findall(r"\{\{dashboard_[a-z_]+\}\}", text)
        if tokens(sql) == tokens(expected) and parse(sql) == parse(expected):
            return []
    except (ValueError, sqlglot.errors.SqlglotError):
        pass
    return ["留存 SQL 与配置的字段、事件、筛选、聚合粒度、成熟窗口或输出列不一致。"]
