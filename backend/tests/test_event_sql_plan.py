from copy import deepcopy
import pytest
from event_sql_fixture import build, config, formula_config, field, FIELDS, TRACKING

def test_event_compiler_feature_exists():
    import importlib.util
    assert importlib.util.find_spec("apps.dashboard.crud.event_sql_plan") is not None, "事件计划尚未实现"

@pytest.mark.parametrize("aggregation", ["count","count_distinct","sum","avg","min","max"])
def test_authorized_metric_preserves_aggregation_and_output(aggregation):
    p=build(config(aggregation,groups=True))
    assert p.required_columns == ("day_key","category","次数")
    assert p.metrics[0].aggregation == aggregation

@pytest.mark.parametrize("mutate", [
    lambda c:c["metrics"].append("invalid"), lambda c:c["metrics"].append(deepcopy(c["metrics"][0])),
    lambda c:c.update(approximate=True), lambda c:c["filters"].update(logic="xor"),
    lambda c:c["metrics"][0].update(aggregation="median"),
    lambda c:c["metrics"][0].update(filters={"rules":[{"field":field("actor"),"operator":"eq"}]}),
    lambda c:c["metrics"][0]["field"].update(eventTable="unknown"),
    lambda c:c["metrics"][0]["field"].update(eventName="unknown"),
])
def test_invalid_raw_configuration_is_not_silently_dropped(mutate):
    from apps.dashboard.crud.event_sql_plan import validate_event_input, EventConfigurationError
    c=config(); mutate(c)
    errors=validate_event_input(c)
    if not errors:
        with pytest.raises(EventConfigurationError): build(c)
    else:
        assert all(e.path and e.message for e in errors)

def test_physical_text_cannot_become_numeric_by_client_label():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    c=config("sum"); c["metrics"][0]["metricField"]={**field("actor"),"category":"number"}
    with pytest.raises(EventConfigurationError): build(c)

def test_json_parameter_and_host_permission_are_authoritative():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    c=config("sum"); c["metrics"][0]["metricField"]={**field("value"),"kind":"tracking-property","eventName":"View","propertyName":"value"}
    assert "payload" in build(c).metrics[0].expression
    with pytest.raises(EventConfigurationError): build(c,allowed={"events":set(FIELDS["events"])-{"payload"}})
    c["metrics"][0]["metricField"]["jsonPath"]="$.stolen"
    with pytest.raises(EventConfigurationError): build(c)

def test_unselected_hidden_property_does_not_block_count():
    assert build(allowed={"events":set(FIELDS["events"])-{"payload"}}).metrics[0].aggregation=="count"

def test_duplicate_workspace_event_definition_is_rejected():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    t=deepcopy(TRACKING);t["event_name_mappings"].append(deepcopy(t["event_name_mappings"][0]))
    with pytest.raises(EventConfigurationError): build(tracking=t)

def test_event_selector_requires_a_workspace_dictionary():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    with pytest.raises(EventConfigurationError): build(tracking={})

def test_formula_only_atomic_inputs_remain_part_of_plan():
    c=formula_config(); metrics=c.pop("metrics"); c["metrics"]=[]
    tokens=c["formulaMetrics"][0]["tokens"]
    tokens[0]={"type":"atomicMetric","metric":metrics[0]};tokens[2]={"type":"atomicMetric","metric":metrics[1]}
    p=build(c); assert len(p.metrics)==2 and p.required_columns==("day_key","category","人均金额")

def test_conflicting_atomic_ids_do_not_share_results():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    c=formula_config(); metrics=c.pop("metrics");c["metrics"]=[];metrics[1]["id"]=metrics[0]["id"]
    c["formulaMetrics"][0]["tokens"][0]={"type":"atomicMetric","metric":metrics[0]}
    c["formulaMetrics"][0]["tokens"][2]={"type":"atomicMetric","metric":metrics[1]}
    with pytest.raises(EventConfigurationError): build(c)

def test_constant_only_group_has_no_authorized_domain():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    c=config(groups=True);c["metrics"]=[];c["formulaMetrics"]=[{"id":"f","alias":"常量","tokens":[{"type":"number","value":"3"}]}]
    with pytest.raises(EventConfigurationError): build(c)

@pytest.mark.parametrize("key,value",[("id",["bad"]),("alias",{"bad":1}),("aggregation",[])])
def test_malformed_metric_scalars_return_configuration_issues(key,value):
    from apps.dashboard.crud.event_sql_plan import validate_event_input
    c=config();c["metrics"][0][key]=value
    assert validate_event_input(c)

def test_atomic_aggregation_must_be_explicit():
    from apps.dashboard.crud.event_sql_plan import validate_event_input
    c=formula_config();m=c["metrics"][0].copy();m.pop("aggregation")
    c["formulaMetrics"][0]["tokens"][0]={"type":"atomicMetric","metric":{**m,"id":"atom"}}
    assert any("aggregation" in i.path for i in validate_event_input(c))
