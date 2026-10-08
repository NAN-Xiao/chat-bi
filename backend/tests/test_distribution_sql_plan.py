import copy
from decimal import Decimal

import pytest

from distribution_sql_fixture import config, event, field, plan, module, property_config, simultaneous, FIELDS, TRACKING


@pytest.mark.parametrize("kind", ["count", "days", "hours", "property"])
def test_current_client_without_version_resolves_explicit_subject(kind):
    c = property_config(); c["distribution"]["metric"]["kind"] = kind
    p = plan(c)
    assert p.main_source.entity_expression == '"subject"'
    assert p.group_names == () and p.metric_kind == kind
    assert p.required_columns == ("distribution_date", "total_entities", "interval_order", "interval_label", "entity_count", "entity_rate")


@pytest.mark.parametrize("bounds", [[0], list(range(21)), [0, 0], [2, 1], [False, 1], [0, float("nan")],
                                    [0, float("inf")], ["0", 1], ["", 1], None, "0,1"])
def test_invalid_bounds_are_not_cleaned_or_defaulted(bounds):
    c = config(); c["distribution"]["interval"] = {"mode": "custom", "customBounds": bounds}
    assert any("customBounds" in i.path for i in module().validate_distribution_input(c))


@pytest.mark.parametrize("bounds", [[-1.5, 0, 10], list(range(20))])
def test_finite_increasing_bounds_remain_exact(bounds):
    c = config(); c["distribution"]["interval"] = {"mode": "custom", "customBounds": bounds}
    assert plan(c).custom_bounds == tuple(Decimal(str(b)) for b in bounds)


@pytest.mark.parametrize("bad", ["kind", "aggregation", "mode", "toggle", "groups", "filter", "time", "grain", "chart", "formula", "approximate"])
def test_invalid_active_configuration_fails_closed(bad):
    c = property_config(); d = c["distribution"]
    if bad == "kind": d["metric"]["kind"] = "unknown"
    if bad == "aggregation": d["metric"]["aggregation"] = "approx_percentile"
    if bad == "mode": d["interval"]["mode"] = "other"
    if bad == "toggle": d["simultaneous"]["enabled"] = "false"
    if bad == "groups": c["groups"] = [None]
    if bad == "filter": c["filters"] = {"logic": "xor", "rules": []}
    if bad == "time": c["time"]["field"] = None
    if bad == "grain": c["time"]["grain"] = "month"
    if bad == "chart": c["chart"]["type"] = "bar"
    if bad == "formula": c["calculatedMetrics"] = [{"tokens": [{"type": "number", "value": 1}]}]
    if bad == "approximate": c["approximate"] = True
    with pytest.raises(module().DistributionConfigurationError): plan(c)


@pytest.mark.parametrize("name", ["uid", "country", "account_key"])
def test_subject_name_never_creates_an_implicit_dimension(name):
    c, fields = config(), copy.deepcopy(FIELDS)
    fields[name] = fields.pop("subject"); c["distribution"]["entityField"] = field(name)
    p = plan(c, fields=fields)
    assert p.group_names == () and name not in p.required_columns
    assert p.main_source.entity_expression == f'"{name}"'


@pytest.mark.parametrize("bad", ["event", "event_source", "cross_table", "permission", "expression", "dictionary", "metric_type", "event_time", "encoding", "time_permission"])
def test_metadata_and_permissions_are_authoritative(bad):
    c, fields, tracking, allowed = property_config(), copy.deepcopy(FIELDS), copy.deepcopy(TRACKING), set(FIELDS)
    if bad == "event": c["distribution"]["event"]["eventName"] = "missing"
    if bad == "event_source": c["distribution"]["event"]["eventNameField"] = "tag"
    if bad == "cross_table": c["distribution"]["event"]["eventTable"] = "other"
    if bad == "permission": allowed.remove("subject")
    if bad == "expression": c["distribution"]["entityField"]["expression"] = "subject OR 1=1"
    if bad == "dictionary": tracking["enabled"] = False
    if bad == "metric_type": c["distribution"]["metric"]["field"] = field("tag")
    if bad in {"event_time", "encoding", "time_permission"}:
        c["distribution"]["metric"]["kind"] = "hours"
        if bad == "event_time": fields["occurred_at"].pop("field_role")
        if bad == "encoding": fields["occurred_at"]["extra_properties"] = {}
        if bad == "time_permission": allowed.remove("occurred_at")
    with pytest.raises(module().DistributionConfigurationError): plan(c, fields=fields, tracking=tracking, allowed=allowed)


def test_filters_keep_event_and_global_scopes_and_required_policy():
    c = simultaneous(config())
    c["groups"] = [field("category")]
    c["filters"] = {"logic": "or", "rules": [{"field": field("tag"), "operator": "eq", "value": v} for v in ("x", "y")]}
    c["distribution"]["eventFilters"] = {"rules": [{"field": field("amount"), "operator": "gt", "value": 3}]}
    policy = {"events": {"rules": [{"field": field("category"), "operator": "eq", "value": "allowed"}]}}
    p = plan(c, policies=policy)
    assert p.group_names == ("group_1",)
    assert '"amount" > 3' in p.main_source.predicate
    assert '"amount" > 3' not in p.simultaneous_source.predicate
    for source in (p.main_source, p.simultaneous_source):
        assert " OR " in source.predicate and "'allowed'" in source.predicate


def test_event_local_json_resolution_and_forged_path():
    c, tracking = simultaneous(property_config(), "sum", "score"), copy.deepcopy(TRACKING)
    c["distribution"]["metric"]["field"] = field("score")
    for m in tracking["event_name_mappings"]:
        m["properties"] = [{"property_name": "score", "source_field": "payload", "json_path": f"$.{m['event_name']}", "property_type": "number"}]
    p = plan(c, tracking=tracking)
    assert "'A'" in p.main_source.value_expression and "'B'" in p.simultaneous_source.value_expression
    c["distribution"]["metric"]["field"]["jsonPath"] = "$.forged"
    with pytest.raises(module().DistributionConfigurationError): plan(c, tracking=tracking)


def test_global_parameter_missing_on_second_event_is_not_dropped():
    c, tracking = simultaneous(config()), copy.deepcopy(TRACKING)
    tracking["event_name_mappings"][0]["properties"] = [{"property_name": "score", "source_field": "payload", "json_path": "$.x", "property_type": "number"}]
    c["filters"] = {"rules": [{"field": field("score"), "operator": "gt", "value": 1}]}
    with pytest.raises(module().DistributionConfigurationError): plan(c, tracking=tracking)


@pytest.mark.parametrize("target",["range","calendar"])
def test_mysql_timestamp_session_timezone_is_not_silently_assumed(target):
    from common.core.config import settings
    c, fields=config(),copy.deepcopy(FIELDS)
    fields["occurred_at"]={"type":"timestamp","field_role":"event_time","extra_properties":{"timezone":settings.DASHBOARD_BUSINESS_TIMEZONE}}
    if target=="range": c["time"].update(field=field("occurred_at"),dateParameterType="timestamp")
    else: c["distribution"]["metric"]["kind"]="hours"
    with pytest.raises(module().DistributionConfigurationError,match="TIMESTAMP"):
        plan(c,fields=fields,dialect="mysql")


def test_encoded_range_field_cannot_contradict_declared_metadata():
    fields=copy.deepcopy(FIELDS); fields["dt"]["extra_properties"]={"encoding":"epoch_seconds"}
    with pytest.raises(module().DistributionConfigurationError): plan(fields=fields)


def test_event_time_type_cannot_contradict_declared_encoding():
    from common.core.config import settings
    fields=copy.deepcopy(FIELDS)
    fields["occurred_at"]={"type":"timestamp","field_role":"event_time","extra_properties":{"timezone":settings.DASHBOARD_BUSINESS_TIMEZONE,"encoding":"epoch_seconds"}}
    c=config(); c["distribution"]["metric"]["kind"]="days"
    with pytest.raises(module().DistributionConfigurationError): plan(c,fields=fields)


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
@pytest.mark.parametrize("encoding", ["yyyyMMdd", "YYYYMMDD", "yyyymmdd"])
@pytest.mark.parametrize("parameter,data_type", [("yyyymmdd_number", "bigint"), ("yyyymmdd_text", "varchar")])
def test_calendar_encoding_format_case_does_not_reject_valid_workspace_metadata(dialect, encoding, parameter, data_type):
    fields = copy.deepcopy(FIELDS)
    fields["dt"] = {"type": data_type, "field_role": "partition_date", "extra_properties": {"encoding": encoding}}
    c = config()
    c["time"]["dateParameterType"] = parameter
    p = plan(c, fields=fields, dialect=dialect)
    assert "{{dashboard_start_yyyymmdd}}" in p.main_source.predicate
    assert "{{dashboard_end_yyyymmdd}}" in p.main_source.predicate
    assert ("TO_DATE" if dialect == "postgres" else "STR_TO_DATE") in p.main_source.date_expression
    assert fields["dt"]["extra_properties"]["encoding"] == encoding
