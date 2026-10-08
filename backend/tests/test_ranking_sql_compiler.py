import copy
import pytest
import sqlglot
from apps.dashboard.crud.ranking_sql_compiler import compile_ranking_sql, GUARD_COLUMN
from apps.dashboard.crud.ranking_sql_plan import RankingConfigurationError
from ranking_sql_fixture import config, plan, field, FIELDS


@pytest.mark.parametrize("tie,function", [("default","ROW_NUMBER"),("skip","RANK"),("dense","DENSE_RANK")])
@pytest.mark.parametrize("dialect", ["postgres", "mysql", "starrocks", "doris"])
def test_fixed_columns_and_tie_windows(tie,function,dialect):
    sql = compile_ranking_sql(plan(config(tie=tie),dialect=dialect))
    tree = sqlglot.parse_one(sql.replace("{{dashboard_start_yyyymmdd}}","20260901").replace("{{dashboard_end_yyyymmdd}}","20260928"),read=dialect)
    assert tree.named_selects == ["rank","ranking_entity","ranking_value","simultaneous_metric_1","simultaneous_metric_2","ranking_property_1",GUARD_COLUMN]
    window = next(tree.find_all(sqlglot.exp.Window))
    assert window.this.sql_name() == function
    assert len(window.args["order"].expressions) == (3 if tie == "default" else 2)
    assert sql == compile_ranking_sql(plan(config(tie=tie),dialect=dialect))


@pytest.mark.parametrize("scenario", ["direction","tie","aggregation","numeric","event","cross_table","groups","filters","revoked","mapping","properties_type","missing_time"])
def test_invalid_configuration_rejected(scenario):
    conf = config(); kwargs = {}
    r = conf["ranking"]
    if scenario == "direction": r["metric"]["direction"] = "sideways"
    if scenario == "tie": r["tieHandling"] = "other"
    if scenario == "aggregation": r["metric"]["aggregation"] = "guess"
    if scenario == "numeric": r["metric"].update(aggregation="sum",metricField=field("category"))
    if scenario == "event": r["metric"]["event"] = None
    if scenario == "cross_table": r["simultaneousMetrics"][0]["event"]["eventTable"] = "other"
    if scenario == "groups": conf["groups"] = [field("category")]
    if scenario == "filters": conf["filters"] = {"rules":[{"field":field("category"),"operator":"whatever","value":"x"}]}
    if scenario == "revoked": kwargs["allowed"] = {"events":{"day","event_name","subject"}}
    if scenario == "mapping": r["simultaneousProperties"][0]["sourceField"] = "payload"
    if scenario == "properties_type": r["simultaneousProperties"] = "category"
    if scenario == "missing_time": conf["time"] = None
    with pytest.raises(RankingConfigurationError): plan(conf,**kwargs)


def test_json_mapping_and_physical_types_are_server_owned():
    conf = config("sum")
    conf["ranking"]["metric"]["metricField"] = {**field("value"),"kind":"tracking-property","eventName":"visit","sourceField":"payload","jsonPath":"$.value"}
    tracking = {"enabled":True,"default_event_table":"events","default_event_name_field":"event_name",
        "event_name_mappings":[{"event_name":"visit","properties":[{"property_name":"value","source_field":"payload","json_path":"$.value","property_type":"double"}]},{"event_name":"purchase"}]}
    assert "payload" in compile_ranking_sql(plan(conf,tracking=tracking))
    with pytest.raises(RankingConfigurationError): plan(conf,tracking=tracking,allowed={"events":set(FIELDS)-{"payload"}})
    physical = copy.deepcopy(tracking); physical["event_name_mappings"][0]["properties"] = [{"property_name":"category","source_field":"category","property_type":"double"}]
    conf["ranking"]["metric"]["metricField"] = {**field("category"),"kind":"tracking-property","eventName":"visit"}
    with pytest.raises(RankingConfigurationError): plan(conf,tracking=physical)
