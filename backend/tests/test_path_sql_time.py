import copy
import pytest
from path_compiler_fixture import config, plan, FIELDS


@pytest.mark.parametrize("parameter", ["date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"])
def test_date_parameters(parameter):
    c=config(); f=copy.deepcopy(FIELDS); c["time"]["dateParameterType"]=parameter
    if parameter.startswith("yyyymmdd"): f["day"]["type"]="bigint" if parameter.endswith("number") else "text"
    if parameter=="timestamp": c["time"]["field"]["field"]="occurred_at"
    p=plan(c,fields=f)
    assert "path_parameter_bounds" in p.time.bounds
    assert "dashboard_" in p.time.bounds
    if parameter=="timestamp": assert '"occurred_at" <' in p.time.predicate


def test_time_unit_precision_and_source_timezone():
    assert "* 0.001" in plan().time.instant
    f=copy.deepcopy(FIELDS); f["occurred_at"]={"type":"timestamp","field_role":"event_time"}
    with pytest.raises(ValueError,match="时区"): plan(fields=f)
    f["occurred_at"]["extra_properties"]={"timezone":"UTC"}
    assert "AT TIME ZONE 'UTC'" in plan(fields=f).time.instant
    f["occurred_at"]["type"]="timestamptz"
    assert plan(fields=f).time.naive_timezones == ()


def test_time_encoding_missing_or_conflicting():
    f=copy.deepcopy(FIELDS); f["occurred_at"]["extra_properties"]={}
    with pytest.raises(ValueError): plan(fields=f)


@pytest.mark.parametrize("kind", ["timestamp(6)", "datetime(6)"])
def test_mysql_microsecond_difference_is_decimal_before_division(kind):
    f=copy.deepcopy(FIELDS)
    f["occurred_at"]={"type":kind,"field_role":"event_time","extra_properties":{"timezone":"UTC"}}
    c=config(); c["time"].update(field={"table":"events","field":"occurred_at"},dateParameterType="timestamp")
    p=plan(c,fields=f,dialect="mysql")
    assert "CAST(TIMESTAMPDIFF(MICROSECOND" in p.time.instant
    assert "AS DECIMAL(30, 6)) / 1000000.0" in p.time.instant
    assert "AS DECIMAL(30, 6)) / 1000000.0" in p.time.predicate
    f["occurred_at"]={"type":"timestamp","field_role":"event_time","extra_properties":{"encoding":"epoch_seconds","timezone":"UTC"}}
    with pytest.raises(ValueError): plan(fields=f)
