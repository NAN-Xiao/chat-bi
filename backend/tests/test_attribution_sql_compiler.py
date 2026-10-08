import pytest
import sqlglot
from attribution_compiler_fixture import config, plan, field, FIELDS, ALLOWED

def compile_sql(conf=None, **kw):
    from apps.dashboard.crud.attribution_sql_compiler import compile_attribution_sql
    return compile_attribution_sql(plan(conf, **kw))

@pytest.mark.parametrize("method", ["first", "last", "linear"])
def test_closed_template_preserves_fixed_columns(method):
    p = plan(config(method))
    sql = compile_sql(config(method))
    tree = sqlglot.parse_one(sql.replace("{{dashboard_start_date}}", "'2026-09-01'").replace("{{dashboard_end_date}}", "'2026-09-28'"), read="postgres")
    assert tree.named_selects == [*p.required_columns,'__attribution_data_error']
    assert sql == compile_sql(config(method))

@pytest.mark.parametrize("case", ["method", "window", "float_window", "direct", "event", "field", "linear_avg", "group"])
def test_bad_config_is_not_silently_substituted(case):
    from apps.dashboard.crud.attribution_sql_plan import AttributionConfigurationError
    conf = config()
    if case == "method": conf["attribution"]["method"] = "unknown"
    if case == "window": conf["attribution"]["window"] = {"mode":"duration", "value":0,"unit":"day"}
    if case == "float_window": conf["attribution"]["window"] = {"mode":"duration", "value":1.5,"unit":"day"}
    if case == "direct": conf["attribution"]["includeDirect"] = "false"
    if case == "event": conf["attribution"]["events"][0]["event"]["eventName"] = "missing"
    if case == "field": conf["attribution"]["targetMetric"]["metricField"] = field("missing")
    if case == "linear_avg": conf["attribution"]["targetMetric"]["aggregation"] = "avg"
    if case == "group": conf["groups"] = [{**field("channel"), "attributionSide":"invalid"}]
    with pytest.raises(AttributionConfigurationError): plan(conf)

def test_same_time_selection_requires_stable_metadata():
    from apps.dashboard.crud.attribution_sql_plan import AttributionConfigurationError
    fields = {k:{kk:vv for kk,vv in v.items() if kk != "field_role" or k != "id"} for k,v in FIELDS.items()}
    with pytest.raises(AttributionConfigurationError): plan(config("first"), metadata_fields={"events":fields})
    assert compile_sql(metadata_fields={"events":fields})

def test_revoked_field_and_client_expression_are_rejected():
    from apps.dashboard.crud.attribution_sql_plan import AttributionConfigurationError
    with pytest.raises(AttributionConfigurationError): plan(allowed_fields_by_table={"events":set(FIELDS)-{"amount"}})
    conf = config(); conf["attribution"]["targetMetric"]["metricField"]["expression"] = "1"
    with pytest.raises(AttributionConfigurationError): plan(conf)

def test_compiled_sql_tamper_is_rejected():
    from apps.dashboard.crud.attribution_sql_validation import attribution_result_contract_issues
    p = plan(); sql = compile_sql()
    assert attribution_result_contract_issues(sql, p) == []
    assert attribution_result_contract_issues(sql.replace("touch_time <= t.target_time", "touch_time >= t.target_time"), p)

def test_mysql_epoch_utc_template_has_no_postgres_functions():
    fields = {**FIELDS, "occurred_at":{"type":"bigint","field_role":"event_time","extra_properties":{"encoding":"epoch_milliseconds"}}}
    sql = compile_sql(metadata_fields={"events":fields},dialect="mysql",engine="mysql",business_timezone="UTC")
    tree = sqlglot.parse_one(sql.replace("{{dashboard_start_date}}","'2026-09-01'").replace("{{dashboard_end_date}}","'2026-09-28'"),read="mysql")
    assert "TO_TIMESTAMP" not in sql and "AT TIME ZONE" not in sql
    assert "TIMESTAMPDIFF" in sql and tree.named_selects[-2] == "contribution_rate"

def test_mysql_calendar_bounds_use_verified_second_precision_functions():
    from apps.dashboard.crud.attribution_sql_plan import AttributionConfigurationError
    fields = {**FIELDS,"occurred_at":{"type":"bigint","field_role":"event_time","extra_properties":{"encoding":"epoch_milliseconds"}}}
    sql = compile_sql(metadata_fields={"events":fields},dialect="mysql",engine="mysql")
    assert "CONVERT_TZ" in sql and "TIMESTAMPDIFF(SECOND" in sql
    assert "TIMESTAMPDIFF(MICROSECOND" not in sql

def test_json_numeric_property_type_is_preserved_in_all_roles():
    from attribution_compiler_fixture import TRACKING
    conf = config(); conf['attribution']['targetMetric']['metricField'] = {**field('price'),'kind':'tracking-property','eventName':'convert'}
    tracking = {**TRACKING,'event_name_mappings':[{'event_name':'convert','properties':[{'property_name':'price','source_field':'payload','json_path':'$.price','property_type':'number'}]}, {'event_name':'email'},{'event_name':'search'}]}
    p = plan(conf,tracking_metadata=tracking)
    tree = sqlglot.parse_one(p.metric,read='postgres')
    assert tree.args['to'].this in {sqlglot.exp.DataType.Type.DECIMAL,sqlglot.exp.DataType.Type.DOUBLE}

def test_related_property_rejects_different_sql_type_families():
    from apps.dashboard.crud.attribution_sql_plan import AttributionConfigurationError
    conf = config()
    conf['attribution']['events'][0]['relatedProperty'] = {'enabled':True,'targetProperty':field('day'),'touchProperty':field('session')}
    with pytest.raises(AttributionConfigurationError): plan(conf)

def test_mysql_json_null_is_checked_before_numeric_conversion():
    from attribution_compiler_fixture import TRACKING
    conf = config(); conf['attribution']['targetMetric']['metricField'] = {**field('price'),'kind':'tracking-property','eventName':'convert'}
    tracking = {**TRACKING,'event_name_mappings':[{'event_name':'convert','properties':[{'property_name':'price','source_field':'payload','json_path':'$.price','property_type':'number'}]}, {'event_name':'email'},{'event_name':'search'}]}
    fields = {**FIELDS,'occurred_at':{'type':'bigint','field_role':'event_time','extra_properties':{'encoding':'epoch_milliseconds'}}}
    p = plan(conf,tracking_metadata=tracking,metadata_fields={'events':fields},dialect='mysql',engine='mysql')
    assert 'JSON_TYPE' in p.metric and 'CASE' in p.metric
