import copy

import pytest
import sqlglot

from apps.dashboard.crud.revenue_sql_plan import RevenueConfigurationError, validate_revenue_input
from apps.dashboard.crud.revenue_sql_compiler import compile_revenue_sql
from apps.dashboard.crud.revenue_sql_validation import revenue_result_contract_issues
from revenue_sql_fixture import FIELDS, config, field, plan


@pytest.mark.parametrize("days", [1, 365])
def test_window_boundaries_keep_inclusive_day_zero(days):
    p = plan(config(days=days, cost=True))
    assert p.required_columns == ("cohort_date", "cohort_size", *(f"day_{d}" for d in range(days + 1)), "cost_value")
    assert not revenue_result_contract_issues(compile_revenue_sql(p), p)


@pytest.mark.parametrize("days", [0, 366, -1, None, "2", 2.0, True])
def test_window_is_not_clamped_or_coerced(days):
    assert any(i.path == "revenue.observationDays" for i in validate_revenue_input(config(days=days)))


@pytest.mark.parametrize("value", [None, [], {"logic": "invalid", "rules": []},
                                  {"rules": [{}]}, {"rules": [{"field": field("subject"), "operator": "eq"}]}])
def test_malformed_filters_are_not_discarded(value):
    conf = config(); conf["filters"] = value
    with pytest.raises(RevenueConfigurationError): plan(conf)


@pytest.mark.parametrize("mutation", ["field", "table", "type", "other_event", "mapping", "duplicate_event"])
def test_authorized_metadata_is_the_only_field_mapping_authority(mutation):
    conf = config()
    fields = copy.deepcopy(FIELDS)
    tracking = {"enabled": True, "default_event_table": "events", "default_event_name_field": "event_name",
                "event_name_mappings": [{"event_name": "start"}, {"event_name": "purchase"}]}
    if mutation == "field": conf["revenue"]["metric"]["field"] = field("missing")
    if mutation == "table": conf["revenue"]["paymentEvent"]["eventTable"] = "private"
    if mutation == "type": fields["amount"]["type"] = "text"
    if mutation == "other_event": conf["revenue"]["metric"]["field"]["eventName"] = "start"
    if mutation == "mapping": conf["revenue"]["metric"]["field"]["expression"] = "amount + 10"
    if mutation == "duplicate_event": tracking["event_name_mappings"].append({"event_name": "purchase"})
    with pytest.raises(RevenueConfigurationError): plan(conf, fields=fields, tracking=tracking)


def test_json_numeric_parameter_uses_payment_event_dictionary():
    conf = config(cost=True)
    for role, name in (("metric", "value"), ("cost", "expense")):
        conf["revenue"][role]["field"] = {**field(name), "kind": "tracking-property", "eventName": "purchase",
                                            "sourceField": "payload", "jsonPath": "$." + name}
    tracking = {"enabled": True, "default_event_table": "events", "default_event_name_field": "event_name",
                "event_name_mappings": [{"event_name": "start"}, {"event_name": "purchase", "properties": [
                    {"property_name": name, "source_field": "payload", "json_path": "$." + name, "property_type": "double"}
                    for name in ("value", "expense")]}]}
    p = plan(conf, tracking=tracking)
    assert sqlglot.parse_one(p.metric_event.metric, read="postgres").find(sqlglot.exp.Cast).args["to"].this in {
        sqlglot.exp.DataType.Type.DECIMAL, sqlglot.exp.DataType.Type.DOUBLE}
    conf["revenue"]["metric"]["field"]["jsonPath"] = "$.tampered"
    with pytest.raises(RevenueConfigurationError): plan(conf, tracking=tracking)


def test_unselected_event_parameter_does_not_require_its_hidden_source_column():
    tracking = {"enabled": True, "default_event_table": "events", "default_event_name_field": "event_name",
                "event_name_mappings": [{"event_name": "start"}, {"event_name": "purchase", "properties": [
                    {"property_name":"hidden_value", "source_field":"payload", "json_path":"$.value", "property_type":"number"}]}]}
    fields = {k:v for k,v in FIELDS.items() if k != "payload"}
    p = plan(config("count"), fields=fields, tracking=tracking, allowed={"events":set(fields)})
    assert p.method == "count"
    conf = config(); conf["revenue"]["metric"]["field"] = {**field("hidden_value"), "kind":"tracking-property", "eventName":"purchase"}
    with pytest.raises(RevenueConfigurationError):
        plan(conf, fields=fields, tracking=tracking, allowed={"events":set(fields)})


def test_numeric_semantic_label_cannot_override_physical_text_source_type():
    tracking = {"enabled":True, "default_event_table":"events", "default_event_name_field":"event_name",
                "event_name_mappings":[{"event_name":"start"}, {"event_name":"purchase", "properties":[
                    {"property_name":"value", "source_field":"category", "property_type":"double"}]}]}
    conf = config(); conf["revenue"]["metric"]["field"] = {**field("value"), "kind":"tracking-property", "eventName":"purchase"}
    with pytest.raises(RevenueConfigurationError): plan(conf,tracking=tracking)


@pytest.mark.parametrize("kind", [None, "tracking-property"])
def test_json_numeric_host_is_rejected_for_explicit_and_virtual_parameters(kind):
    tracking = {"enabled":True, "default_event_table":"events", "default_event_name_field":"event_name",
                "event_name_mappings":[{"event_name":"start"}, {"event_name":"purchase", "properties":[
                    {"property_name":"value", "source_field":"amount", "json_path":"$.value", "property_type":"double"}]}]}
    conf = config(); conf["revenue"]["metric"]["field"] = field("value")
    if kind: conf["revenue"]["metric"]["field"]["kind"] = kind
    with pytest.raises(RevenueConfigurationError): plan(conf,tracking=tracking)


@pytest.mark.parametrize("role", ["entity", "group", "filter"])
def test_all_revenue_roles_reject_json_mapping_on_numeric_host(role):
    fields = copy.deepcopy(FIELDS)
    fields["invalid_json"] = {"type":"text", "semantic_type":"text", "source_field":"amount", "json_path":"$.key"}
    conf = config()
    selected = {**field("invalid_json"), "sourceField":"amount", "jsonPath":"$.key"}
    if role == "entity": conf["revenue"]["entityField"] = selected
    if role == "group": conf["groups"] = [selected]
    if role == "filter": conf["filters"] = {"rules":[{"field":selected,"operator":"eq","value":"value"}]}
    with pytest.raises(RevenueConfigurationError): plan(conf,fields=fields)


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "starrocks", "doris"])
def test_supported_dialects_have_parseable_closed_templates(dialect):
    conf = config(cost=True); conf["groups"] = [field("category")]
    p = plan(conf, dialect=dialect)
    sql = compile_revenue_sql(p)
    assert not revenue_result_contract_issues(sql, p)
    parsed = sqlglot.parse_one(sql.replace("{{dashboard_start_yyyymmdd}}", "20260901")
                                .replace("{{dashboard_end_yyyymmdd}}", "20260903"), read=dialect)
    assert tuple(parsed.named_selects) == p.required_columns
    assert "RECURSIVE" not in sql


@pytest.mark.parametrize("mutation", ["event", "filter", "cohort_grain", "payment_distinct", "maturity",
                                    "cost", "result", "token", "statement"])
def test_contract_rejects_semantic_sql_tampering(mutation):
    p = plan(config(cost=True)); sql = compile_revenue_sql(p)
    if mutation == "event": sql = sql.replace("'purchase'", "'different'")
    if mutation == "filter": sql = sql.replace('"subject" IS NOT NULL', "TRUE")
    if mutation == "cohort_grain": sql = sql.replace("SELECT DISTINCT cohort_date, entity_id", "SELECT cohort_date, entity_id")
    if mutation == "payment_distinct": sql = sql.replace("SUM(metric_value)", "SUM(DISTINCT metric_value)")
    if mutation == "maturity": sql = sql.replace("ELSE NULL END AS day_2", "ELSE 0 END AS day_2")
    if mutation == "cost": sql = sql.replace("SUM(cost_value)", "MAX(cost_value)")
    if mutation == "result": sql = sql.replace("AS day_2", "AS wrong")
    if mutation == "token": sql = sql.replace("{{dashboard_end_yyyymmdd}}", "20260903")
    if mutation == "statement": sql += "; SELECT 1"
    assert revenue_result_contract_issues(sql, p)


@pytest.mark.parametrize("parameter,kind", [("yyyymmdd_text", "text"), ("date", "date"), ("timestamp", "bigint"), ("timestamp", "timestamptz")])
def test_date_parameter_contract_is_preserved(parameter, kind):
    conf = config(); conf["time"]["dateParameterType"] = parameter
    fields = copy.deepcopy(FIELDS); fields["day"] = {"type": kind, "extra_properties": {"encoding": "epoch_milliseconds"}}
    p = plan(conf, fields=fields)
    assert p.end_inclusive is (parameter != "timestamp")
    assert not revenue_result_contract_issues(compile_revenue_sql(p), p)
