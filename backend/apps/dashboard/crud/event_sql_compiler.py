"""Closed event aggregate templates: filter, aggregate, align, then calculate."""
from sqlglot import exp
from apps.dashboard.crud.event_sql_plan import EventSqlPlan

def compile_event_sql(plan: EventSqlPlan) -> str:
    def q(name):return exp.to_identifier(name,quoted=True).sql(dialect=plan.dialect)
    table=exp.to_table(plan.source_table) if plan.source_table else None
    if table:
        for part in table.parts:part.set("quoted",True)
    ctes=[plan.time.scaffold_ctes] if plan.time.scaffold_ctes else []
    dimensions=(["chart_date"] if plan.time.bucket else [])+[f"chart_group_{i+1}" for i in range(len(plan.group_aliases))]
    for i,m in enumerate(plan.metrics):
        selections=[]
        if plan.time.bucket:selections.append(f"{plan.time.bucket} AS chart_date")
        selections.extend(f"{expression} AS chart_group_{j+1}" for j,expression in enumerate(m.groups))
        selections.append("1 AS metric_value" if m.aggregation=="count" else f"{m.expression} AS metric_value")
        ctes.append(f"event_input_{i} AS (\n SELECT "+", ".join(selections)+f"\n FROM {table.sql(dialect=plan.dialect)}\n WHERE {m.predicate}\n)")
        measure="COUNT(*)" if m.aggregation=="count" else ("COUNT(DISTINCT metric_value)" if m.aggregation=="count_distinct" else f"{m.aggregation.upper()}(metric_value)")
        aggregation="SELECT "+", ".join([*dimensions,f"{measure} AS metric_value"])+f" FROM event_input_{i}"
        if dimensions:aggregation+=" GROUP BY "+", ".join(dimensions)
        ctes.append(f"event_aggregate_{i} AS (\n {aggregation}\n)")
    group_keys=[f"chart_group_{i+1}" for i in range(len(plan.group_aliases))]
    if group_keys:
        ctes.append("event_group_domain AS (\n "+"\n UNION\n ".join("SELECT DISTINCT "+", ".join(group_keys)+f" FROM event_input_{i}" for i in range(len(plan.metrics)))+"\n)")
    if plan.time.bucket:
        grid="SELECT DISTINCT "+plan.time.scaffold_bucket+" AS chart_date"
        grid+=(", "+", ".join("g."+g for g in group_keys)) if group_keys else ""
        grid+=" FROM dashboard_dates"
        if group_keys:grid+=" CROSS JOIN event_group_domain AS g"
    elif group_keys:grid="SELECT "+", ".join(group_keys)+" FROM event_group_domain"
    else:grid="SELECT 1 AS event_anchor"
    ctes.append("event_keys AS (\n "+grid+"\n)")
    selected=["k."+d for d in dimensions]
    for i,m in enumerate(plan.metrics):
        value=f"a{i}.metric_value"
        if m.aggregation in {"count","count_distinct"}:value=f"COALESCE({value}, 0)"
        selected.append(f"{value} AS chart_base_{i+1}")
    if not selected:selected=["k.event_anchor"]
    joined="SELECT "+", ".join(selected)+" FROM event_keys AS k"
    for i,m in enumerate(plan.metrics):
        on=[f"k.chart_date = a{i}.chart_date"] if plan.time.bucket else []
        on.extend(f"(k.{g} = a{i}.{g} OR (k.{g} IS NULL AND a{i}.{g} IS NULL))" for g in group_keys)
        joined+=f"\n LEFT JOIN event_aggregate_{i} AS a{i} ON "+(" AND ".join(on) or "TRUE")
    ctes.append("event_values AS (\n "+joined+"\n)")
    def formula(ir):
        if ir[0]=="number":return ir[1]
        if ir[0]=="metric_ref":return f"k.chart_base_{ir[1]+1}"
        left,right=formula(ir[2]),formula(ir[3])
        if ir[1]=="/":return f"(CAST({left} AS DECIMAL(38, 10)) / NULLIF({right}, 0))"
        return f"({left} {ir[1]} {right})"
    output=[]
    if plan.time.bucket:output.append(f"{plan.time.output_expression} AS {q(plan.time.alias)}")
    output.extend(f"k.{g} AS {q(alias)}" for g,alias in zip(group_keys,plan.group_aliases))
    output.extend(f"k.chart_base_{i+1} AS {q(m.alias)}" for i,m in enumerate(plan.metrics) if m.output)
    for f in plan.formulas:
        value=formula(f.expression)
        if f.decimal_places is not None:value=f"ROUND({value}, {f.decimal_places})"
        output.append(f"{value} AS {q(f.alias)}")
    sql="WITH "+",\n".join(ctes)+"\nSELECT "+", ".join(output)+"\nFROM event_values AS k"
    if dimensions:sql+="\nORDER BY "+", ".join("k."+d for d in dimensions)
    return sql
