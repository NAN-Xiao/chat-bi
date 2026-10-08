from copy import deepcopy
import pytest
from event_sql_fixture import build, config, FIELDS

@pytest.mark.parametrize("grain", ["day","week","month"])
def test_date_buckets_preserve_configured_grain(grain):
    c=config();c["time"]["grain"]=grain;p=build(c)
    assert p.time.grain==grain and p.time.scaffold_ctes

@pytest.mark.parametrize("kind,param", [("integer","yyyymmdd_number"),("text","yyyymmdd_text"),("date","date"),("timestamp","timestamp")])
def test_declared_date_type_selects_correct_boundaries(kind,param):
    c=config();c["time"]["dateParameterType"]=param
    f=deepcopy(FIELDS);f["events"]["day_key"]={"type":kind,"extra_properties":{"timezone":"Asia/Shanghai"}}
    p=build(c,fields=f)
    assert (" < " in p.time.predicate)==(param=="timestamp")

@pytest.mark.parametrize("encoding", ["epoch_seconds","epoch_milliseconds"])
def test_epoch_encoding_is_explicit(encoding):
    c=config();c["time"]["dateParameterType"]="timestamp"
    f=deepcopy(FIELDS);f["events"]["day_key"]={"type":"bigint","extra_properties":{"encoding":encoding}}
    assert "TO_TIMESTAMP" in build(c,fields=f).time.bucket

def test_numeric_timestamp_without_encoding_fails():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    c=config();c["time"]["dateParameterType"]="timestamp"
    with pytest.raises(EventConfigurationError):build(c)

def test_metric_card_keeps_time_filter_without_date_group():
    p=build(config(card=True));assert p.time.predicate!="TRUE" and not p.time.bucket
    assert p.required_columns==("次数",)

def test_unsupported_dialect_never_substitutes_another():
    from apps.dashboard.crud.event_sql_plan import EventConfigurationError
    with pytest.raises(EventConfigurationError):build(dialect="sqlite")
