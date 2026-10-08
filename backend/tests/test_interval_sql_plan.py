import copy
from dataclasses import replace

import pytest

from apps.dashboard.crud.interval_sql_plan import (
    IntervalConfigurationError, IntervalTimePlan, build_interval_plan, validate_interval_input,
)


def field(name):
    return {"table": "events", "field": name}


def config():
    return {"analysis_model": "interval", "chart": {"type": "table"},
            "time": {"field": field("day"), "grain": "day", "date_parameter_type": "date"},
            "groups": [], "filters": {}, "interval": {
                "entityField": field("subject"), "limitSeconds": 90,
                "startEvent": {"kind": "tracking-event", "eventTable": "events", "eventNameField": "action", "eventName": "open"},
                "endEvent": {"kind": "tracking-event", "eventTable": "events", "eventNameField": "action", "eventName": "close"}}}


FIELDS = {"subject": {"type": "text"}, "action": {"type": "text"}, "category": {"type": "text"},
          "link": {"type": "text"}, "payload": {"type": "json"}, "sequence": {"type": "bigint", "field_role": "event_sequence"},
          "record_id": {"type": "bigint"},
          "occurred_at": {"type": "bigint", "field_role": "event_time", "extra_properties": {"encoding": "epoch_milliseconds"}},
          "day": {"type": "date", "extra_properties": {"date_semantics": "business_date", "timezone": "Asia/Shanghai"}}}
TRACKING = {"enabled": True, "default_event_table": "events", "default_event_name_field": "action",
            "default_event_time_field": "occurred_at",
            "tables": [],
            "event_name_mappings": [{"event_name": name, "event_table": "events", "event_name_field": "action"} for name in ("open", "close")]}


def plan(conf=None, *, fields=None, tracking=None, dialect="postgres", engine=None):
    from apps.dashboard.crud.interval_sql_time import build_interval_time_plan
    c = conf or config()
    meta = {"events": copy.deepcopy(fields or FIELDS)}
    t = copy.deepcopy(TRACKING if tracking is None else tracking)
    time = build_interval_time_plan(c, metadata_fields=meta, dialect=dialect, engine=engine or dialect,
                                   business_timezone="Asia/Shanghai", tracking_metadata=t)
    return build_interval_plan(c, time_plan=time, metadata_fields=meta, allowed_fields_by_table={"events": set(FIELDS)},
                              dialect=dialect, engine=engine or dialect, tracking_metadata=t, table_filters={})


@pytest.mark.parametrize("value", [True, 90.5, 59, 15552001, None, "90"])
def test_invalid_limit_is_not_coerced(value):
    c = config(); c["interval"]["limitSeconds"] = value
    assert any(i.path == "interval.limitSeconds" for i in validate_interval_input(c))


@pytest.mark.parametrize("value", [0, False])
def test_filter_zero_and_false_are_not_missing(value):
    c = config(); c["filters"] = {"rules": [{"field": field("sequence"), "operator": "eq", "value": value}]}
    assert not validate_interval_input(c)


def test_missing_filter_value_is_not_dropped():
    c = config(); c["interval"]["startEventFilters"] = {"rules": [{"field": field("category"), "operator": "eq", "value": ""}]}
    assert any("startEventFilters" in i.path for i in validate_interval_input(c))


def test_existing_order_roles_have_stable_order():
    t = copy.deepcopy(TRACKING); t["field_role_mappings"] = [{"table": "events", "field": "record_id", "role": "event_id"}]
    assert plan(tracking=t).order_fields == ('"record_id"', '"sequence"')


def test_explicit_time_only_ordering():
    fields = copy.deepcopy(FIELDS); fields["sequence"].pop("field_role")
    assert plan(fields=fields).order_fields == ()


@pytest.mark.parametrize("names", [["secret"], ["payload"], [None]])
def test_invalid_ordering_fields_fail(names):
    t = copy.deepcopy(TRACKING); t["field_role_mappings"] = [{"table": "events", "role": "event_id", "field": name} for name in names]
    with pytest.raises(ValueError): plan(tracking=t)


def test_expression_must_match_metadata_and_event_must_exist():
    c = config(); c["groups"] = [{**field("sequence"), "expression": "sequence + 1"}]
    with pytest.raises(ValueError): plan(c)
    c = config(); c["interval"]["startEvent"]["eventName"] = "unknown"
    with pytest.raises(ValueError): plan(c)


def test_cross_table_and_same_event_related_mismatch_fail():
    c = config(); c["interval"]["endEvent"]["eventTable"] = "secret"
    with pytest.raises(ValueError): plan(c)
    c = config(); c["interval"]["endEvent"]["eventName"] = "open"
    c["interval"]["relatedProperty"] = {"enabled": True, "startProperty": field("link"), "endProperty": field("category")}
    with pytest.raises(ValueError): plan(c)


def test_original_metadata_roles_work_without_new_ui_settings():
    fields = copy.deepcopy(FIELDS)
    fields["sequence"]["field_role"] = "event_sequence"
    fields["day"]["extra_properties"] = {}
    tracking = copy.deepcopy(TRACKING)
    tracking["tables"] = []
    result = plan(fields=fields, tracking=tracking)
    assert result.order_fields == ('"sequence"',)


def test_time_only_ordering_does_not_require_a_new_metadata_form():
    fields = copy.deepcopy(FIELDS)
    fields["sequence"].pop("field_role", None)
    tracking = copy.deepcopy(TRACKING)
    tracking["tables"] = []
    assert plan(fields=fields, tracking=tracking).order_fields == ()
