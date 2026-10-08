import copy

import pytest

from apps.dashboard.crud.funnel_sql_plan import build_funnel_plan, validate_funnel_input, FunnelConfigurationError


def field(name, table="events"):
    return {"table": table, "field": name}


def event(name):
    return {"kind": "tracking-event", "eventTable": "events", "eventNameField": "action",
            "eventName": name, "field": "action"}


def config():
    return {"analysisModel": "funnel", "chart": {"type": "funnel"},
            "time": {"field": field("dt"), "dateParameterType": "yyyymmdd_number",
                     "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"}},
            "funnel": {"entityField": field("subject"), "relatedPropertyEnabled": False,
                       "window": {"mode": "duration", "value": 1, "unit": "day"},
                       "steps": [{"event": event(n), "alias": n, "filters": {}} for n in ("A", "B", "C")]},
            "filters": {}, "groups": []}


FIELDS = {"subject": {"type": "varchar"}, "action": {"type": "varchar"}, "dt": {"type": "integer"},
          "occurred_at": {"type": "bigint", "field_role": "event_time", "extra_properties": {"encoding": "epoch_milliseconds"}},
          "category": {"type": "varchar"}, "payload": {"type": "jsonb"}}
TRACKING = {"enabled": True, "default_event_table": "events", "default_event_name_field": "action",
            "event_name_mappings": [{"event_name": n} for n in ("A", "B", "C")]}


def plan(conf=None, *, dialect="postgres", fields=None, tracking=None, allowed=None, policies=None):
    metadata = fields if fields is not None else FIELDS
    return build_funnel_plan(conf if conf is not None else config(), metadata_fields={"events": metadata},
        allowed_fields_by_table={"events": set(metadata) if allowed is None else allowed},
        tracking_metadata=TRACKING if tracking is None else tracking, table_filters=policies or {},
        dialect=dialect, engine=dialect)


@pytest.mark.parametrize("count,valid", [(1, False), (2, True), (10, True), (11, False)])
def test_step_limits(count, valid):
    c = config(); c["funnel"]["steps"] = [copy.deepcopy(c["funnel"]["steps"][0]) for _ in range(count)]
    assert bool(validate_funnel_input(c)) is not valid


@pytest.mark.parametrize("window,valid", [({"mode": "same_day"}, True),
    ({"mode": "duration", "value": 365, "unit": "day"}, True),
    ({"mode": "duration", "value": 366, "unit": "day"}, False),
    ({"mode": "duration", "value": True, "unit": "day"}, False),
    ({"mode": "duration", "value": "1", "unit": "day"}, False),
    ({"mode": "duration", "value": 1.5, "unit": "day"}, False),
    ({"mode": "duration", "value": 1, "unit": "fortnight"}, False), (None, False), ({}, False)])
def test_window_input_is_strict(window, valid):
    c = config(); c["funnel"]["window"] = window
    assert bool(validate_funnel_input(c)) is not valid


def test_legacy_window_never_overrides_present_current_window():
    c = config(); c["funnel"].update(window=None, windowDays=7)
    assert validate_funnel_input(c)
    del c["funnel"]["window"]
    assert plan(c).window_seconds == 604800
    c["funnel"]["windowDays"] = 366
    assert validate_funnel_input(c)


@pytest.mark.parametrize("bad", ["empty_step", "toggle", "group", "formula", "approximate", "filter", "empty_group", "missing_time"])
def test_invalid_active_configuration_is_not_discarded(bad):
    c = config()
    if bad == "empty_step": c["funnel"]["steps"][1] = {}
    if bad == "toggle": c["funnel"]["relatedPropertyEnabled"] = "false"
    if bad == "group": c["groups"] = [field("category")]
    if bad == "formula": c["calculatedMetrics"] = [{"tokens": [{"type": "number", "value": 1}]}]
    if bad == "approximate": c["approximate"] = True
    if bad == "filter": c["filters"] = {"logic": "xor", "rules": []}
    if bad == "empty_group": c["filters"] = {"rules": [{"type": "group", "children": []}]}
    if bad == "missing_time": c["time"] = None
    with pytest.raises(FunnelConfigurationError): plan(c)


@pytest.mark.parametrize("bad", ["event", "event_source", "permission", "expression", "cross_table", "time_encoding", "time_role"])
def test_metadata_and_permission_errors_fail_closed(bad):
    c, fields, allowed = config(), copy.deepcopy(FIELDS), set(FIELDS)
    if bad == "event": c["funnel"]["steps"][0]["event"]["eventName"] = "unknown"
    if bad == "event_source": c["funnel"]["steps"][0]["event"]["eventNameField"] = "category"
    if bad == "permission": allowed.remove("subject")
    if bad == "expression": c["funnel"]["entityField"]["expression"] = "subject OR 1=1"
    if bad == "cross_table": c["funnel"]["steps"][1]["event"]["eventTable"] = "other"
    if bad == "time_encoding": fields["occurred_at"]["extra_properties"] = {}
    if bad == "time_role": fields["occurred_at"].pop("field_role")
    with pytest.raises(FunnelConfigurationError): plan(c, fields=fields, allowed=allowed)


def test_alias_and_required_filters_are_not_event_substitutions():
    c = config(); c["funnel"]["steps"][0]["alias"] = "Display only"
    policies = {"events": {"rules": [{"field": field("category"), "operator": "eq", "value": "allowed"}]}}
    p = plan(c, policies=policies)
    assert p.steps[0].label == "Display only"
    assert "'A'" in p.steps[0].predicate and "Display only" not in p.steps[0].predicate
    assert all("'allowed'" in step.predicate for step in p.steps)


def test_event_local_json_mapping_and_forged_path():
    c, tracking = config(), copy.deepcopy(TRACKING)
    for m in tracking["event_name_mappings"]:
        m["properties"] = [{"property_name": "score", "source_field": "payload",
                             "json_path": f"$.{m['event_name']}", "property_type": "number"}]
    for step in c["funnel"]["steps"]:
        step["filters"] = {"rules": [{"field": field("score"), "operator": "gt", "value": 1}]}
    p = plan(c, tracking=tracking)
    assert all(f"'{n}'" in step.predicate for n, step in zip(("A", "B", "C"), p.steps))
    c["funnel"]["steps"][0]["filters"]["rules"][0]["field"]["jsonPath"] = "$.secret"
    with pytest.raises(FunnelConfigurationError): plan(c, tracking=tracking)


def test_related_property_legacy_cannot_override_explicit_root():
    c = config(); c["funnel"]["relatedPropertyEnabled"] = True
    for s in c["funnel"]["steps"]: s["relatedProperty"] = field("category")
    assert all(s.related for s in plan(c).steps)
    c["funnel"]["relatedProperty"] = None
    with pytest.raises(FunnelConfigurationError): plan(c)


@pytest.mark.parametrize("mapping_key,item", [("field_role_mappings", {"table":"other_events","field":"clock","role":"event_time"}),
                                             ("fields", {"table_name":"other_events","field_name":"clock","field_role":"event_time"})])
def test_unrelated_table_time_roles_do_not_block_current_default_table(mapping_key,item):
    tracking=copy.deepcopy(TRACKING); tracking[mapping_key]=[item]
    assert len(plan(tracking=tracking).steps)==3


@pytest.mark.parametrize("collision", ["occurred_at","subject","action","dt","category"])
def test_event_parameters_cannot_shadow_physical_fields_or_policy(collision):
    tracking=copy.deepcopy(TRACKING)
    tracking["event_name_mappings"][0]["properties"]=[{"property_name":collision,"source_field":"payload",
        "json_path":"$.client_value","property_type":"number"}]
    policy={"events":{"rules":[{"field":field("category"),"operator":"eq","value":"allowed"}]}}
    p=plan(tracking=tracking,policies=policy)
    assert p.steps[0].entity=='"subject"'
    assert p.steps[0].time=='("occurred_at" / 1000.0)'
    assert "client_value" not in p.steps[0].predicate
    assert "'A'" in p.steps[0].predicate and '"category"' in p.steps[0].predicate


def test_root_json_related_property_resolves_each_event_from_verified_logical_mapping():
    c,tracking=config(),copy.deepcopy(TRACKING)
    for m in tracking["event_name_mappings"]:
        m["properties"]=[{"property_name":"key","source_field":"payload","json_path":f"$.{m['event_name']}","property_type":"text"}]
    c["funnel"].update(relatedPropertyEnabled=True,relatedProperty={**field("key"),"kind":"tracking-property",
        "eventName":"A","propertyName":"key","sourceField":"payload","jsonPath":"$.A","isJsonSubfield":True})
    p=plan(c,tracking=tracking)
    assert all(f"'{name}'" in step.related for name,step in zip(("A","B","C"),p.steps))
    c["funnel"]["relatedProperty"]["jsonPath"]="$.forged"
    with pytest.raises(FunnelConfigurationError): plan(c,tracking=tracking)


def test_explicit_json_filter_can_select_property_colliding_with_physical_column():
    c,tracking=config(),copy.deepcopy(TRACKING)
    tracking["event_name_mappings"][0]["properties"]=[{"property_name":"subject","source_field":"payload","json_path":"$.subject","property_type":"text"}]
    c["funnel"]["steps"][0]["filters"]={"rules":[{"field":{**field("subject"),"kind":"tracking-property",
        "eventName":"A","sourceField":"payload","jsonPath":"$.subject"},"operator":"eq","value":"customer"}]}
    step=plan(c,tracking=tracking).steps[0]
    assert step.entity=='"subject"' and "->> 'subject'" in step.predicate
