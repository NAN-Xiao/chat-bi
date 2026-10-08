"""Resolve event measures and formula IR exclusively from authorized metadata."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from sqlglot import exp
from apps.dashboard.crud.funnel_sql_plan import _EventResolver, _filter_issues, FunnelConfigurationError
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, PropertyConfigurationError
from apps.dashboard.crud.event_sql_time import EventAggregationTimePlan, build_event_aggregation_time_plan
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type

AGGREGATIONS=frozenset({"count","count_distinct","sum","avg","min","max"})

@dataclass(frozen=True)
class EventIssue:
    code: str
    path: str
    message: str
    def __str__(self):return f"{self.path}：{self.message}"

class EventConfigurationError(ValueError):
    def __init__(self,issues):
        self.issues=tuple(issues)
        super().__init__("；".join(map(str,self.issues)))

def fail(path,message):raise EventConfigurationError([EventIssue("EVENT_INVALID_CONFIG",path,message)])

def measure_field(metric):return metric.get("metricField") or metric.get("metric_field") or metric.get("metric")
def empty_filter(value):return {} if value is None or value==[] else value

def validate_event_input(raw: dict) -> list[EventIssue]:
    issues=[]
    def add(path,message):issues.append(EventIssue("EVENT_INVALID_CONFIG",path,message))
    if not isinstance(raw,dict):return [EventIssue("EVENT_INVALID_CONFIG","context","事件配置必须为对象。")]
    ids={};aliases=set()
    def metric(value,path,atomic=False):
        if not isinstance(value,dict):add(path,"指标必须为有效对象。");return
        if atomic and not value.get("aggregation"):add(path+".aggregation","公式原子指标必须明确聚合方式。")
        if not isinstance(value.get("aggregation","count"),str) or value.get("aggregation","count") not in AGGREGATIONS:add(path+".aggregation","不支持的聚合方式。")
        if not isinstance(value.get("field"),dict):add(path+".field","请选择有效事件或字段。")
        if value.get("aggregation","count")!="count" and not isinstance(measure_field(value),dict):add(path+".metricField","请选择计算字段。")
        identifier=value.get("id")
        if identifier is not None and (not isinstance(identifier,str) or not identifier.strip()):add(path+".id","指标 ID 无效。")
        if isinstance(identifier,str) and identifier:
            if identifier in ids and (not atomic or ids[identifier]!=value):add(path+".id","指标 ID 重复或对应不同配置。")
            ids[identifier]=value
        for i in _filter_issues(empty_filter(value.get("filters")),path+".filters"):add(i.path,i.message)
        if not atomic:
            alias=value.get("alias") if "alias" in value else value.get("label")
            if alias is not None:
                if not isinstance(alias,str) or not alias.strip():add(path+".alias","输出别名无效。")
                elif alias in aliases:add(path+".alias","输出别名重复。")
                else:aliases.add(alias)
    metrics=raw.get("metrics",[])
    if not isinstance(metrics,list):add("metrics","指标必须为列表。");metrics=[]
    for i,m in enumerate(metrics):metric(m,f"metrics[{i}]")
    formula_lists=[raw[k] for k in ("formulaMetrics","formula_metrics","calculatedMetrics") if k in raw]
    if any(not isinstance(v,list) for v in formula_lists):add("formulaMetrics","公式必须为列表。")
    if len(formula_lists)>1 and any(v!=formula_lists[0] for v in formula_lists[1:]):add("formulaMetrics","同时提供的公式列表不一致。")
    formulas=formula_lists[0] if formula_lists and isinstance(formula_lists[0],list) else []
    formula_ids=set()
    for i,f in enumerate(formulas):
        path=f"formulaMetrics[{i}]"
        if not isinstance(f,dict):add(path,"公式必须为对象。");continue
        fid=f.get("id")
        if fid is not None and (not isinstance(fid,str) or not fid.strip() or fid in formula_ids or fid in ids):add(path+".id","公式 ID 无效或重复。")
        if isinstance(fid,str):formula_ids.add(fid)
        alias=f.get("alias")
        if alias is not None:
            if not isinstance(alias,str) or not alias.strip() or alias in aliases:add(path+".alias","输出别名无效或重复。")
            else:aliases.add(alias)
        places=f.get("decimalPlaces")
        if places is not None and (type(places) is not int or not 0<=places<=10):add(path+".decimalPlaces","小数位数必须为 0 到 10 的整数。")
        tokens=f.get("tokens")
        if not isinstance(tokens,list) or not tokens:add(path+".tokens","公式 token 不能为空。");continue
        for j,t in enumerate(tokens):
            tp=f"{path}.tokens[{j}]"
            if not isinstance(t,dict):add(tp,"公式 token 无效。");continue
            if t.get("type")=="atomicMetric":metric(t.get("metric"),tp+".metric",True)
            elif t.get("type")=="number":
                try:
                    if isinstance(t.get("value"),bool) or not Decimal(str(t.get("value"))).is_finite():raise InvalidOperation()
                except (InvalidOperation,ValueError):add(tp,"公式常量必须为有限数字。")
    if not metrics and not formulas:add("metrics","至少配置一个指标或公式。")
    for k in ("groups","selectedFields"):
        if k in raw and (not isinstance(raw[k],list) or any(not isinstance(v,dict) for v in raw[k])):add(k,"字段必须为有效对象列表。")
    for i in _filter_issues(empty_filter(raw.get("filters")),"filters"):add(i.path,i.message)
    if raw.get("approximate") not in (None,False):add("approximate","事件编译尚未提供近似聚合模板。")
    if "time" in raw and not isinstance(raw["time"],dict):add("time","时间配置必须为对象。")
    return issues

@dataclass(frozen=True)
class EventMetricPlan:
    id: str
    alias: str
    aggregation: str
    expression: str
    predicate: str
    groups: tuple[str,...]
    output: bool
    numeric: bool

@dataclass(frozen=True)
class EventFormulaPlan:
    alias: str
    expression: tuple
    decimal_places: int | None

@dataclass(frozen=True)
class EventSqlPlan:
    dialect: str
    source_table: str
    time: EventAggregationTimePlan
    group_aliases: tuple[str,...]
    metrics: tuple[EventMetricPlan,...]
    formulas: tuple[EventFormulaPlan,...]
    required_columns: tuple[str,...]

class EventResolver(_EventResolver):
    def field(self,value,path):
        expression,definition=super().field(value,path)
        if definition.get("json_path"):
            host=definition.get("source_field")
            kind=self.metadata[self.table].get(host,{}).get("type","").lower()
            if not kind.startswith(("json","text","varchar","char","string")):fail(path,"JSON 属性来源列类型无效。")
        return expression,definition

def build_event_plan(config: dict, formula_ir: dict, *, metadata_fields: dict,
        allowed_fields_by_table: dict, dialect: str, engine: str, tracking_metadata,
        table_filters: dict, business_timezone: str) -> EventSqlPlan:
    errors=validate_event_input(config.get("raw_context") or config)
    if errors:raise EventConfigurationError(errors)
    if formula_ir.get("issues"):fail("formulaMetrics","；".join(formula_ir["issues"]))
    if dialect not in {"postgres","mysql","starrocks","doris"}:fail("datasource",f"当前方言 {dialect} 未提供事件编译能力。")
    tracking=tracking_metadata.model_dump() if hasattr(tracking_metadata,"model_dump") else dict(tracking_metadata or {})
    def canonical(name,path):
        matches=[t for t in metadata_fields if t==name]
        if not matches:matches=[t for t in metadata_fields if t.split(".")[-1]==name]
        if len(matches)!=1:fail(path,"来源表不存在、未授权或名称存在歧义。")
        return matches[0]
    def base(m,i):return {"id":str(m.get("id") or f"m{i+1}"),"alias":m.get("alias") or m.get("label") or f"m{i+1}",
        "field":m.get("field"),"metric_field":measure_field(m),"aggregation":m.get("aggregation") or "count","filters":m.get("filters") or {}}
    items=[base(m,i) for i,m in enumerate(config.get("metrics",[]))]
    visible=len(items)
    for m in formula_ir.get("base_metrics",[]):
        if not any(v["id"]==m["id"] for v in items):items.append(m)
    groups=config.get("groups",[])
    candidates=[m.get("field") for m in items]+groups+[(config.get("time") or {}).get("field")]
    tables={canonical(v.get("eventTable") or v.get("table"),"metadata.table") for v in candidates if isinstance(v,dict)}
    if len(tables)>1:fail("metadata.table","未配置关联规则，不能跨表计算。")
    table=next(iter(tables),"")
    if not table and items:fail("metadata.table","无法确定授权来源表。")
    if groups and not items:fail("groups","仅常量公式没有可确定的分组域。")
    if table and tracking.get("enabled") and tracking.get("default_event_table") and canonical(tracking["default_event_table"],"metadata.table")!=table:
        fail("metadata.table","来源不属于当前工作空间默认事件表。")
    try:
        common=_Resolver(metadata_fields,allowed_fields_by_table,dialect)
        common.table=table
        if (config.get("time") or {}).get("field"):
            from apps.dashboard.crud.dashboard_date_filter import resolve_dashboard_date_expression
            from datetime import date
            try:
                resolve_dashboard_date_expression((config.get("time") or {}).get("date_expression") or (config.get("time") or {}).get("dateExpression"),today=date(2000,1,1))
            except (ValueError,TypeError,KeyError):fail("time.dateExpression","请选择有效的看板日期表达式。")
        time=build_event_aggregation_time_plan(config.get("time") or {},resolver=common,dialect=dialect,engine=engine,
                business_timezone=business_timezone,include_date=(config.get("chart") or {}).get("type")!="metric")
        result=[]
        for i,m in enumerate(items):
            path=f"metrics[{i}]" if i<visible else f"formulaMetrics.base_metrics[{i-visible}]"
            f=m["field"];name=f.get("eventName") or f.get("event_name") or "";key=f.get("eventNameField") or f.get("event_name_field")
            is_event=f.get("kind")=="tracking-event"
            properties={}
            if is_event:
                if not name or not key:fail(path+".field","事件来源配置不完整。")
                mappings=[v for v in tracking.get("event_name_mappings",[]) if name in _event_names(v)]
                if len(mappings)!=1:fail(path+".field","工作空间事件不存在或定义不唯一。")
                for mapping in mappings:
                    source=mapping.get("event_table") or mapping.get("table") or tracking.get("default_event_table")
                    if canonical(source,path)!=table or (mapping.get("event_name_field") or tracking.get("default_event_name_field"))!=key:
                        fail(path+".field","事件来源与工作空间字典不一致。")
                    for prop in mapping.get("properties",[]):
                        pname=prop.get("property_name") or prop.get("field_name") or prop.get("name")
                        if not pname:continue
                        if pname in properties:fail(path+".field","事件参数定义不唯一。")
                        host=prop.get("source_field");typ=_normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("type"))
                        properties[pname]={**prop,"type":typ if prop.get("json_path") else metadata_fields[table].get(host,{}).get("type",""),"semantic_type":typ}
            resolver=EventResolver(deepcopy(metadata_fields),allowed_fields_by_table,dialect,table,name,properties)
            # Resolve every selected field through the same event-local contract.
            group_expressions=tuple(resolver.field(g,f"groups[{j}]")[0] for j,g in enumerate(groups))
            if is_event:
                event_column,_=resolver.field({"table":table,"field":key},path+".eventNameField")
                event_predicate=f"{event_column} = {exp.Literal.string(name).sql(dialect=dialect)}"
            else:
                resolver.field(f,path+".field");event_predicate="TRUE"
            aggregation=m["aggregation"]
            expression="*"
            numeric=aggregation in {"count", "count_distinct"}
            if aggregation!="count":
                expression,definition=resolver.field(m.get("metric_field"),path+".metricField")
                typ=str(definition.get("type") or "").lower()
                numeric=numeric or bool(NUMERIC.match(typ))
                if aggregation in {"sum","avg"} and not NUMERIC.match(typ):fail(path+".metricField","求和和均值必须使用真实数值字段。")
                if aggregation in {"max","min"} and not (NUMERIC.match(typ) or typ.startswith(("text","char","varchar","string","date","time"))):fail(path+".metricField","该类型没有已支持的排序聚合能力。")
            predicates=[time.predicate,event_predicate,resolver.filters(empty_filter(config.get("filters")),"filters"),resolver.filters(empty_filter(m.get("filters")),path+".filters")]
            for policy_table,rules in table_filters.items():
                if canonical(policy_table,"workspace.required_filters")==table:
                    errs=_filter_issues(rules,"workspace.required_filters")
                    if errs:fail("workspace.required_filters","；".join(map(str,errs)))
                    predicates.append(resolver.filters(rules,"workspace.required_filters"))
            result.append(EventMetricPlan(m["id"],m["alias"],aggregation,expression," AND ".join(f"({v})" for v in predicates),group_expressions,i<visible,numeric))
        by_id={m.id:i for i,m in enumerate(result)}
        def frozen_ir(ir):
            kind=ir.get("type")
            if kind=="number":return ("number",str(Decimal(ir["value"])))
            if kind=="metric_ref":
                if ir["id"] not in by_id:fail("formulaMetrics","公式引用不存在。")
                if not result[by_id[ir["id"]]].numeric:
                    fail("formulaMetrics",f"公式仅支持数值聚合结果；指标“{result[by_id[ir['id']]].alias}”不是数值。")
                return ("metric_ref",by_id[ir["id"]])
            if kind=="binary" and ir.get("operator") in {"+","-","*","/"}:
                return ("binary",ir["operator"],frozen_ir(ir["left"]),frozen_ir(ir["right"]))
            fail("formulaMetrics","公式 IR 无效。")
        formulas=tuple(EventFormulaPlan(f["alias"],frozen_ir(f["expression"]),f.get("decimal_places")) for f in formula_ir.get("formulas",[]))
        aliases=tuple(str(g.get("alias") or g.get("field")) for g in groups)
        columns=(*( (time.alias,) if time.bucket else ()),*aliases,*(m.alias for m in result if m.output),*(f.alias for f in formulas))
        if len(columns)!=len(set(columns)):fail("outputs","日期、分组、指标或公式输出名重复。")
        return EventSqlPlan(dialect,table,time,aliases,tuple(result),formulas,columns)
    except (PropertyConfigurationError,FunnelConfigurationError) as exc:
        raise EventConfigurationError([EventIssue("EVENT_INVALID_CONFIG",i.path,i.message) for i in exc.issues]) from exc
