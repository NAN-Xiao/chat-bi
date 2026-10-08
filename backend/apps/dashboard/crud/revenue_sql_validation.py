"""Verify the entire compiler grammar, including predicates and mature result cells."""
import re

import sqlglot

from apps.dashboard.crud.revenue_sql_compiler import compile_revenue_sql


def revenue_result_contract_issues(sql, plan):
    if plan is None:
        return ["收入查询计划缺失，无法校验 SQL。"]

    def tokens(text):
        return re.findall(r"\{\{dashboard_[a-z0-9_]+\}\}", text)

    def parse(text):
        text = re.sub(r"\{\{dashboard_[a-z0-9_]+\}\}",
                      lambda m: "20260901" if "yyyymmdd" in m[0] else "'2026-09-01'", text)
        statements = sqlglot.parse(text, read=plan.dialect)
        if len(statements) != 1 or statements[0] is None:
            raise ValueError("必须为单条 SQL")
        return statements[0]

    try:
        expected = compile_revenue_sql(plan)
        if tokens(sql) == tokens(expected) and parse(sql) == parse(expected):
            return []
    except (ValueError, sqlglot.errors.SqlglotError):
        pass
    return ["收入 SQL 与配置的事件、字段、筛选、Cohort 粒度、口径、成本、成熟窗口或最终输出列不一致。"]
