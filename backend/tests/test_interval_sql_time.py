import copy

import pytest

from test_interval_sql_plan import config, plan, FIELDS


def test_timestamp_boundaries_use_business_timezone():
    c = config(); c["time"].update(field={"table": "events", "field": "occurred_at"}, date_parameter_type="timestamp")
    p = plan(c)
    assert "Asia/Shanghai" in p.time.predicate
    assert "EXTRACT(EPOCH" in p.time.predicate
    assert '"occurred_at" <' in p.time.predicate
    assert "AT TIME ZONE" in p.time.date
    assert "dashboard_end_exclusive_timestamp" in p.time.bounds


@pytest.mark.parametrize("kind", ["date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"])
def test_all_date_parameters_get_daily_scaffold(kind):
    c = config(); c["time"]["date_parameter_type"] = kind
    f = copy.deepcopy(FIELDS)
    if kind == "timestamp":
        c["time"]["field"]["field"] = "occurred_at"
    elif kind.startswith("yyyymmdd"):
        f["day"]["type"] = "bigint" if kind.endswith("number") else "text"
        f["day"]["extra_properties"]["encoding"] = "yyyymmdd"
    assert "dashboard_dates AS" in plan(c, fields=f).time.scaffold


def test_datetime_requires_timezone_and_aware_preserves_instant():
    f = copy.deepcopy(FIELDS); f["occurred_at"] = {"type": "timestamp", "field_role": "event_time"}
    with pytest.raises(ValueError, match="时区"): plan(fields=f)
    f["occurred_at"]["type"] = "timestamptz"
    assert "EXTRACT(EPOCH" in plan(fields=f).time.instant


def test_explicit_date_parameter_does_not_require_new_business_date_metadata():
    f = copy.deepcopy(FIELDS); f["day"]["extra_properties"] = {}
    assert plan(fields=f).time.date == '"day"'
    f["day"]["extra_properties"] = {"timezone": "UTC"}
    with pytest.raises(ValueError, match="时区冲突"): plan(fields=f)


@pytest.mark.parametrize("kind", ["timestamp", "timestamp(6)"])
def test_mysql_timestamp_precision_does_not_change_absolute_clock(kind):
    f = copy.deepcopy(FIELDS); f["occurred_at"] = {"type": kind, "field_role": "event_time", "extra_properties": {"encoding": "datetime"}}
    p = plan(fields=f, dialect="mysql", engine="mysql")
    assert p.time.mysql_utc is True
    assert "CONVERT_TZ" not in p.time.instant
    assert p.time.naive_timezones == ()


def test_epoch_with_business_date_does_not_require_unused_mysql_timezone_functions():
    p = plan(dialect="mysql", engine="analyticdb mysql")
    assert p.time.mysql_timezones == ()
    assert p.time.mysql_utc is False
