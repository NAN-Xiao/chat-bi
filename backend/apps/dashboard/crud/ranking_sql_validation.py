"""Compare the complete signed ranking query against its authorized plan."""
import re
import sqlglot
from apps.dashboard.crud.ranking_execution_contract import read_ranking_contract, ranking_tree
from apps.dashboard.crud.ranking_sql_compiler import compile_ranking_sql


def ranking_result_contract_issues(sql, plan):
    if plan is None:
        return ["排行榜查询计划缺失，无法校验 SQL。"]
    try:
        if read_ranking_contract(sql) is None:
            raise ValueError("执行协议缺失")
        expected = compile_ranking_sql(plan)
        tokens = lambda text: re.findall(r"\{\{dashboard_[a-z0-9_]+\}\}", text)
        if tokens(sql) == tokens(expected) and ranking_tree(sql, plan.dialect) == ranking_tree(expected, plan.dialect):
            return []
    except (ValueError, sqlglot.errors.SqlglotError):
        pass
    return ["排行榜 SQL 与配置的事件、字段、筛选、聚合、排序、并列规则或属性校验不一致。"]
