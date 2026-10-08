import copy

import pytest

from apps.dashboard.crud.property_sql_plan import (
    PropertyConfigurationError, build_property_plan, property_metadata_fields,
    validate_property_input,
)


def field(name, **extra):
    return {"table": "records", "field": name, **extra}


FIELDS = {"records": {"subject": {"type": "varchar"}, "day": {"type": "integer"},
                       "region": {"type": "varchar"}, "amount": {"type": "numeric"},
                       "payload": {"type": "json"}}}
ALLOWED = {"records": set(FIELDS["records"])}


def config():
    return {"analysis_model": "property", "chart": {"type": "table"},
            "metrics": [{"field": field("subject"), "metricField": field("subject"),
                         "aggregation": "count_distinct", "alias": "用户数"}],
            "groups": [], "filters": {}, "property": {"groupMode": "property"},
            "time": {"field": field("day"), "grain": "day", "date_parameter_type": "yyyymmdd_number"}}


def plan(configuration=None, metadata=None, dialect="postgres", allowed=None):
    return build_property_plan(configuration or config(), metadata_fields=metadata or FIELDS,
                               allowed_fields_by_table=ALLOWED if allowed is None else allowed,
                               dialect=dialect, engine=dialect)


@pytest.mark.parametrize("key,value,path", [
    ("property", {"groupMode": "oops"}, "property.groupMode"),
    ("filters", {"logic": "xor", "rules": []}, "filters.logic"),
    ("time", {"grain": "year"}, "time.grain"),
    ("filters", {"logic": "and", "rules": [{"type": "group", "logic": "and", "children": []}]}, "filters.rules[0]"),
])
def test_invalid_values_survive_normalization(key, value, path):
    conf = config()
    conf[key] = value
    assert any(issue.path == path for issue in validate_property_input(conf))


def test_plan_does_not_mutate_input_and_keeps_result_order():
    conf = config()
    original = copy.deepcopy(conf)
    result = plan(conf)
    assert conf == original
    assert result.required_columns == ("property_date", "property_metric_1")


@pytest.mark.parametrize("change", [
    {"expression": "(SELECT password FROM secrets)"},
    {"table": "other"}, {"field": "missing"}, {"kind": "tracking-event"},
])
def test_reject_untrusted_or_unavailable_field(change):
    conf = config()
    conf["metrics"][0]["field"].update(change)
    conf["metrics"][0]["metricField"].update(change)
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


def test_metric_field_conflict_and_text_sum_rejected():
    conf = config()
    conf["metrics"][0]["metricField"] = field("amount")
    with pytest.raises(PropertyConfigurationError):
        plan(conf)
    conf = config()
    conf["metrics"][0]["aggregation"] = "sum"
    conf["metrics"][0]["field"]["type"] = "numeric"  # client cannot override trusted type
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


def test_formula_and_cross_table_group_are_rejected():
    conf = config()
    conf["formula_metrics"] = [{"formula": "m1+1"}]
    with pytest.raises(PropertyConfigurationError):
        plan(conf)
    conf = config()
    conf["groups"] = [field("region", table="other")]
    metadata = {**FIELDS, "other": {"region": {"type": "varchar"}}}
    with pytest.raises(PropertyConfigurationError):
        plan(conf, metadata, allowed={**ALLOWED, "other": {"region"}})


def test_metadata_uses_schema_types_and_authorized_json_host():
    schema = "# Table: public.records\n[\n(subject:varchar),\n(payload:jsonb),\n(amount:numeric(20,2))\n]"
    tracking = {"fields": [{"table_name": "records", "field_name": "payload.score",
                             "source_field": "payload", "json_path": "$.score", "semantic_type": "number"}]}
    result = property_metadata_fields(schema, tracking)
    assert result["public.records"]["amount"]["type"].startswith("numeric")
    assert result["public.records"]["payload.score"]["source_field"] == "payload"
    conf = config()
    conf["time"] = {"grain": "none"}
    conf["metrics"] = [{"field": field("payload.score"), "aggregation": "sum"}]
    with pytest.raises(PropertyConfigurationError):
        build_property_plan(conf, metadata_fields=property_metadata_fields(schema, tracking),
                            allowed_fields_by_table={"public.records": {"subject"}},
                            dialect="postgres", engine="postgres")


@pytest.mark.parametrize("operator,value", [("eq", None), ("between", "1,2,3"), ("eq", "NaN"), ("in", [])])
def test_invalid_filter_values_rejected(operator, value):
    conf = config()
    conf["filters"] = {"logic": "and", "rules": [{"field": field("amount"), "operator": operator, "value": value}]}
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
@pytest.mark.parametrize("encoding,factor", [("epoch_seconds", "1"), ("epoch_milliseconds", "1000")])
def test_epoch_time_uses_declared_encoding_and_half_open_bounds(dialect, encoding, factor):
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["day"]["extra_properties"] = {"encoding": encoding}
    conf = config()
    conf["time"]["date_parameter_type"] = "timestamp"
    result = plan(conf, metadata, dialect=dialect)
    assert "{{dashboard_end_exclusive_timestamp}}" in result.time_predicate
    assert ' < ' in result.time_predicate and ' <= ' not in result.time_predicate
    assert factor in result.time_predicate
    assert not result.scaffold_ctes
    assert result.suggestions


def test_static_table_without_time_and_json_mapping():
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["payload.score"] = {"type": "number", "semantic_type": "number", "source_field": "payload", "json_path": "$.score"}
    conf = config()
    conf["time"] = {"grain": "none"}
    conf["metrics"] = [{"field": field("payload.score"), "aggregation": "sum"}]
    result = plan(conf, metadata)
    assert result.required_columns == ("property_metric_1",)
    assert 'score' in result.metrics[0].expression
    assert result.source_columns == ("payload",)


@pytest.mark.parametrize("raw", [None, [], "bad", 1])
def test_invalid_shapes_are_configuration_errors(raw):
    conf = config()
    conf["property"] = raw
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


@pytest.mark.parametrize("key,value", [
    ("property", {"groupMode": []}), ("time", {"grain": {}}),
    ("groups", ["region"]), ("filters", {"logic": {}, "rules": []}),
    ("approximate", True),
])
def test_invalid_nested_shapes_do_not_crash_or_disappear(key, value):
    conf = config()
    conf[key] = value
    assert validate_property_input(conf)


def test_group_settings_cannot_target_a_missing_group():
    conf = config()
    conf["property"]["groupSettings"] = {"missing": {"summarize": True, "timeGrain": "month"}}
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


@pytest.mark.parametrize("prop", [{"group_mode": "invalid"}, {"group_settings": {}},
                                  {"groupSettings": {"g": {"time_grain": "bad"}}}])
def test_unsupported_aliases_are_not_silently_normalized(prop):
    conf = config()
    conf["property"] = prop
    assert validate_property_input(conf)


@pytest.mark.parametrize("value,expected", [(True, "TRUE"), (False, "FALSE"), ("true", "TRUE"), ("false", "FALSE")])
def test_boolean_filter_accepts_only_explicit_typed_values(value, expected):
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["region"]["type"] = "boolean"
    conf = config()
    conf["filters"] = {"rules": [{"field": field("region"), "operator": "eq", "value": value}]}
    assert plan(conf, metadata).global_filter.endswith(expected + ')')


def test_nontext_contains_and_noncomparable_min_are_rejected():
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["region"]["type"] = "date"
    conf = config()
    conf["filters"] = {"rules": [{"field": field("region"), "operator": "contains", "value": "2026"}]}
    with pytest.raises(PropertyConfigurationError):
        plan(conf, metadata)
    metadata["records"]["region"]["type"] = "boolean"
    conf = config()
    conf["metrics"] = [{"field": field("region"), "aggregation": "min"}]
    with pytest.raises(PropertyConfigurationError):
        plan(conf, metadata)


def test_event_schema_sections_do_not_replace_public_attributes_or_become_physical_fields():
    from apps.system.crud.tracking_event_schema import EventSchemaField, EventSchemaProjection, format_event_schema_projection
    from apps.dashboard.crud.property_sql_compiler import compile_property_sql

    base = "# Table: records\n[\n(subject:varchar),\n(day:integer),\n(region:varchar),\n(payload:json)\n]\n"
    projection = format_event_schema_projection(EventSchemaProjection(datasource_type="mysql", fields=[
        EventSchemaField("records", "one", "action", "payload.score", "number", "payload", "$.score", "JSON_EXTRACT(payload, '$.score')"),
        EventSchemaField("records", "two", "action", "subject", "number", "payload", "$.subject", "JSON_EXTRACT(payload, '$.subject')"),
    ]))
    for schema in (base + projection, projection + '\n' + base):
        metadata = property_metadata_fields(schema, {})
        assert metadata["records"]["subject"]["type"] == "varchar"
        assert set(metadata["records"]) == {"subject", "day", "region", "payload"}
        compiled = compile_property_sql(plan(metadata=metadata, dialect="mysql"))
        assert 'COUNT(DISTINCT `subject`)' in compiled
        assert 'JSON_EXTRACT' not in compiled
    assert property_metadata_fields(projection, {}) == {}


def test_repeated_base_table_sections_merge_without_losing_public_fields():
    schema = "# Table: records\n(subject:varchar)\n# Table: other\n(id:integer)\n# Table: records\n(day:integer)\n"
    metadata = property_metadata_fields(schema, {})
    assert set(metadata["records"]) == {"subject", "day"}
    assert set(metadata["other"]) == {"id"}


def test_physical_field_explicit_self_source_matches_current_metadata_api():
    conf = config()
    physical = field("subject", sourceField="subject", jsonPath="", expression='"records"."subject"')
    conf["metrics"][0]["field"] = physical
    conf["metrics"][0]["metricField"] = physical
    conf["time"]["field"] = field("day", sourceField="day", jsonPath="")
    result = plan(conf)
    assert result.metrics[0].expression == '"subject"'
    conf["metrics"][0]["field"] = {**physical, "sourceField": "region"}
    with pytest.raises(PropertyConfigurationError):
        plan(conf)


@pytest.mark.parametrize("semantic", ["country_code", "customer_segment", "identifier"])
def test_json_semantic_label_does_not_override_expression_result_type(semantic):
    from apps.dashboard.crud.property_sql_compiler import compile_property_sql
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["payload.category"] = {"type": semantic, "semantic_type": semantic,
        "source_field": "payload", "json_path": "$.category"}
    conf = config()
    conf["filters"] = {"rules": [{"field": field("payload.category"), "operator": "contains", "value": "X"}]}
    result = plan(conf, metadata)
    assert "LIKE '%X%'" in result.global_filter
    assert 'category' in compile_property_sql(result)


@pytest.mark.parametrize("grain", ["day", "week", "month"])
def test_encoded_date_group_uses_declared_metadata_encoding(grain):
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["day"]["extra_properties"] = {"encoding": "yyyyMMdd"}
    conf = config()
    conf["groups"] = [field("day", value="records.day")]
    conf["property"]["groupSettings"] = {"records.day": {"summarize": True, "timeGrain": grain}}
    assert "TO_DATE" in plan(conf, metadata).groups[0]
    assert "STR_TO_DATE" in plan(conf, metadata, dialect="mysql").groups[0]
    with pytest.raises(PropertyConfigurationError):
        plan(conf)  # Numeric fields without declared encoding cannot be guessed.
