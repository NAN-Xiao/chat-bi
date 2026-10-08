"""Verify the closed event grammar independently of output lineage checks."""
import re
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope
from apps.dashboard.crud.event_sql_contract import _expanded, _unquoted, _row_predicates, _implies, _lineage, _measure_issues
from apps.dashboard.crud.event_sql_compiler import compile_event_sql

def event_compiled_contract_issues(sql,plan):
    if plan is None:return ["事件查询计划缺失，无法校验 SQL。"]
    pattern=r"\{\{dashboard_[a-z0-9_]+\}\}"
    def parse(text):
        text=re.sub(pattern,lambda m:"20260901" if "yyyymmdd" in m[0] else "'2026-09-01'",text)
        statements=sqlglot.parse(text,read=plan.dialect)
        if len(statements)!=1 or statements[0] is None:raise ValueError("必须为单条查询")
        return statements[0]
    try:
        expected=compile_event_sql(plan)
        if re.findall(pattern,sql)==re.findall(pattern,expected) and parse(sql)==parse(expected):
            statement=parse(sql)
            root=build_scope(statement)
            issues=[]
            for i,metric in enumerate(plan.metrics):
                scope=root.cte_sources.get(f"event_aggregate_{i}")
                if scope is None:
                    issues.append("事件基础聚合来源缺失。")
                    continue
                actual=scope.expression.args.get("group")
                dimensions=actual.expressions if actual else []
                wanted=([plan.time.bucket] if plan.time.bucket else [])+list(metric.groups)
                # Parse the trusted scalar expressions with the same controlled
                # token substitution as the query, without reusing its builder.
                scalar=lambda text:parse("SELECT "+text).expressions[0]
                if {_unquoted(_expanded(v,scope)) for v in dimensions}!={_unquoted(scalar(v)) for v in wanted}:
                    issues.append(f"指标 {metric.alias} 聚合粒度与配置不一致。")
                predicates=list(_row_predicates(scope))
                effective=exp.and_(*predicates) if predicates else exp.true()
                if not _implies(effective,scalar(metric.predicate)):
                    issues.append(f"指标 {metric.alias} 事实筛选与配置不一致。")
                output=next((v for v in scope.expression.expressions if v.alias_or_name=="metric_value"),None)
                if output is None:issues.append("事件基础度量缺失。")
                else:
                    contract={"groups":[],"time":{},"filters":{}}
                    field_expression=_expanded(scalar(metric.expression),scope) if metric.aggregation!="count" else None
                    # The shared measure checker compares the aggregate payload
                    # after stripping outer casts. Compare at that same layer;
                    # the full template separately verifies the trusted cast.
                    while isinstance(field_expression,exp.Cast):field_expression=field_expression.this
                    descriptor={"alias":metric.alias,"aggregation":metric.aggregation,
                        "table":exp.to_table(plan.source_table).name,"metric_field":{"expression":field_expression.sql(dialect=plan.dialect)} if field_expression is not None else None,
                        "field":{},"filters":{}}
                    issues.extend(_measure_issues(list(_lineage(scope,output)),descriptor,contract,plan.dialect))
            return list(dict.fromkeys(issues))
    except (ValueError,sqlglot.errors.SqlglotError):pass
    return ["事件 SQL 与配置的事件、字段、筛选、时间、聚合粒度、分组域、公式或输出列不一致。"]
