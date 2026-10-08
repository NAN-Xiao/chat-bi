"""Compare the generated AST with the authorized closed attribution template."""
import re
import sqlglot
from apps.dashboard.crud.attribution_sql_compiler import compile_attribution_sql, GUARD_COLUMN


def attribution_result_contract_issues(sql, plan):
    if plan is None: return ["归因查询计划缺失。"]
    def parse(value):
        value = re.sub(r"\{\{dashboard_[a-z0-9_]+\}\}", "'2026-01-01'", value)
        statements = sqlglot.parse(value, read=plan.dialect)
        if len(statements) != 1 or statements[0] is None: raise ValueError("只允许一个查询。")
        return statements[0]
    try:
        tree = parse(sql)
        for node in tree.walk(): node.comments = None
        if tree.named_selects == [*plan.required_columns,GUARD_COLUMN] and tree == parse(compile_attribution_sql(plan)):
            return []
    except (ValueError, sqlglot.errors.SqlglotError):
        pass
    return ["归因 SQL 与配置的事件、字段、筛选、窗口、聚合、分组或最终输出列不一致。"]
