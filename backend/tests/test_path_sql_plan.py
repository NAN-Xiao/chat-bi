import copy
import pytest
from path_compiler_fixture import config, plan, field, event, FIELDS, TRACKING
from apps.dashboard.crud.path_sql_plan import validate_path_input


def test_path_payload_without_entity_field_uses_authorized_default_subject():
    assert plan().entity_expression == '"subject"'
    t = copy.deepcopy(TRACKING); t.pop("default_subject_field")
    with pytest.raises(ValueError, match="主体"): plan(tracking=t)
    with pytest.raises(ValueError): plan(allowed=set(FIELDS) - {"subject"})
    t = copy.deepcopy(TRACKING); t["default_subject_field"] = "category"
    with pytest.raises(ValueError, match="主体"): plan(tracking=t)


@pytest.mark.parametrize("v", [0, 86401, 1.5, True, None, "30"])
def test_invalid_gap_not_coerced(v):
    c = config(); c["path"]["sessionGapSeconds"] = v
    assert validate_path_input(c)


@pytest.mark.parametrize("v", [1, 86400])
def test_gap_boundaries(v):
    c = config(); c["path"]["sessionGapSeconds"] = v
    assert plan(c).session_gap_seconds == v


@pytest.mark.parametrize("change", [
    lambda c: c["path"].update(events=[]),
    lambda c: c["path"]["events"].append(c["path"]["events"][0]),
    lambda c: c["path"].update(initialEvent=event("missing")),
    lambda c: c.update(groups=[field("category")]),
    lambda c: c["path"]["events"][0].update(splitProperties=[field("category"), field("subject")]),
    lambda c: c["path"]["events"][0].update(filters={"rules": [{"field": field("category"), "operator": "eq", "value": "x"}]}),
    lambda c: c.update(approximate=True),
])
def test_invalid_configuration(change):
    c = config(); change(c)
    with pytest.raises(ValueError): plan(c)


def test_event_mapping_permissions_and_expressions():
    c = config(); c["path"]["events"][0]["event"]["eventTable"] = "private"
    with pytest.raises(ValueError): plan(c)
    c = config(); c["path"]["events"][0]["splitProperties"] = [{**field("category"), "expression": "secret"}]
    with pytest.raises(ValueError): plan(c)
    with pytest.raises(ValueError): plan(allowed=set(FIELDS) - {"sequence"})


def test_event_parameter_is_resolved_from_server_dictionary():
    c = config(); prop = {**field("score"), "kind": "tracking-property", "eventName": "A", "propertyName": "score"}
    c["path"]["events"][0]["splitProperties"] = [prop]
    assert "payload" in plan(c).events[0].split_expression
    prop["eventName"] = "B"
    with pytest.raises(ValueError): plan(c)


def test_global_event_property_leaf_and_mandatory_filters():
    c = config(); c["filters"] = {"logic": "or", "rules": [
        {"field": {**field("score"), "kind": "tracking-property", "eventName": "A"}, "operator": "eq", "value": 0},
        {"field": field("category"), "operator": "is_null"}]}
    p = plan(c, table_filters={"events": {"rules": [{"field": field("category"), "operator": "eq", "value": "public"}]}})
    assert "'A'" in p.global_predicate and "0" in p.global_predicate
    assert "public" in p.mandatory_predicate


def test_time_only_and_ambiguous_roles():
    f = copy.deepcopy(FIELDS); f["sequence"].pop("field_role")
    assert plan(fields=f).order_expressions == ()
    t = copy.deepcopy(TRACKING); t["field_role_mappings"] = [{"table": "events", "field": "category", "role": "event_sequence"}]
    with pytest.raises(ValueError): plan(tracking=t)


@pytest.mark.parametrize("n,valid", [(1,True),(30,True),(31,False)])
def test_event_count(n, valid):
    c=config(); c["path"]["events"]=[{"event":event(str(i)),"splitProperties":[]} for i in range(n)]
    c["path"]["initialEvent"]=event("0")
    assert bool(validate_path_input(c)) != valid


@pytest.mark.parametrize("value", [True, False])
def test_json_boolean_filter_keeps_type(value):
    t=copy.deepcopy(TRACKING); t["event_name_mappings"][0]["properties"][0]["property_type"]="boolean"
    c=config(); prop={**field("score"),"kind":"tracking-property","eventName":"A"}
    c["path"]["events"][0]["splitProperties"]=[prop]
    c["filters"]={"logic":"or","rules":[{"field":prop,"operator":"eq","value":value},{"field":field("category"),"operator":"is_null"}]}
    p=plan(c,tracking=t)
    assert p.events[0].split_type=="boolean"
    assert "BOOLEAN" in p.events[0].split_expression
    assert str(value).upper() in p.global_predicate


@pytest.mark.parametrize("kind", ["array","object","unknown","",None])
def test_selected_json_property_requires_supported_declared_type(kind):
    t=copy.deepcopy(TRACKING); t["event_name_mappings"][0]["properties"][0]["property_type"]=kind
    c=config(); c["path"]["events"][0]["splitProperties"]=[{**field("score"),"kind":"tracking-property","eventName":"A"}]
    with pytest.raises(ValueError,match="类型"): plan(c,tracking=t)


def test_unverified_mysql_json_boolean_is_explicitly_rejected():
    t=copy.deepcopy(TRACKING); t["event_name_mappings"][0]["properties"][0]["property_type"]="boolean"
    c=config(); c["path"]["events"][0]["splitProperties"]=[{**field("score"),"kind":"tracking-property","eventName":"A"}]
    with pytest.raises(ValueError,match="尚未验证"): plan(c,tracking=t,dialect="mysql")


def test_workspace_json_boolean_is_typed_for_split_and_global_filter():
    f=copy.deepcopy(FIELDS);f["flag"]={"type":"boolean","semantic_type":"boolean","source_field":"payload","json_path":"$.flag"}
    c=config();c["path"]["events"][0]["splitProperties"]=[field("flag")]
    c["filters"]={"rules":[{"field":field("flag"),"operator":"eq","value":False}]}
    p=plan(c,fields=f)
    assert p.events[0].split_type=="boolean" and "FALSE" in p.global_predicate
