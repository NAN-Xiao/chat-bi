"""Validate the complete plan and independently prove the population grain."""
import re

import sqlglot

from apps.dashboard.crud.dashboard_date_filter import _scan_sql_tokens
from apps.dashboard.crud.distribution_population import population_issues
from apps.dashboard.crud.distribution_sql_compiler import compile_distribution_sql
from apps.dashboard.crud.distribution_sql_plan import DistributionSqlPlan


def distribution_result_contract_issues(sql: str, plan: DistributionSqlPlan | None) -> list[str]:
    if plan is None:
        return ["分布查询计划缺失，无法校验 SQL。"]

    def parse(value):
        tokens = set(re.findall(r"\{\{dashboard_[a-z_]+\}\}", value))
        prepared, _ = _scan_sql_tokens(value, {t: ":" + t[2:-2] for t in tokens})
        statements = sqlglot.parse(prepared, read=plan.dialect)
        if len(statements) != 1 or statements[0] is None:
            raise ValueError("分布编译结果必须为单条查询。")
        return statements

    try:
        actual = parse(sql)
        expected = parse(compile_distribution_sql(plan))
        if actual != expected:
            return ["分布 SQL 与配置的字段、事件、筛选、分桶、聚合或固定结果列不一致。"]
        return population_issues(actual, ["distribution_date", *plan.group_names])
    except (ValueError, sqlglot.errors.SqlglotError) as exc:
        return [f"分布 SQL 无法通过结构校验：{exc}"]
