"""Numeric JSON property types must agree in UI payload normalization and metadata compilation."""
import asyncio
import copy
from types import SimpleNamespace

import pytest

from apps.system.crud.tracking_expression import compile_tracking_json_expression
from apps.system.crud.tracking_event_schema import _normalized_type
from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from test_retention_sql_graph import config, event, field, FIELDS


@pytest.mark.parametrize("dialect", ["mysql", "postgresql", "clickhouse"])
@pytest.mark.parametrize("kind", ["int", "integer", "bigint", "float", "double", "decimal", "numeric", "整数类型", "number"])
def test_numeric_aliases_match_authoritative_property_type(kind, dialect):
    assert compile_tracking_json_expression("events", "payload", "$.level", kind, dialect) == (
        compile_tracking_json_expression("events", "payload", "$.level", _normalized_type(kind), dialect)
    )


@pytest.mark.parametrize("kind", ["amount", "metric", "text", "boolean", "datetime"])
def test_business_labels_do_not_infer_numeric_semantics(kind):
    assert "DECIMAL" not in compile_tracking_json_expression("events", "payload", "$.v", kind, "mysql")


@pytest.mark.parametrize("kind", ["int", "double", "decimal", "number"])
def test_real_normalization_and_retention_plan_agree_on_ui_numeric_payload(monkeypatch, kind):
    fields = {**copy.deepcopy(FIELDS), "payload": {"type": "json"}}
    tracking = {"enabled": True, "default_event_table": "events", "default_event_name_field": "event_name",
        "event_name_mappings": [{"event_name": "start"}, {"event_name": "return", "properties": [
            {"property_name":"level","property_type":kind,"source_field":"payload","json_path":"$.level"}]}]}
    def context(_):
        return {"schema":"# Table: events\n[\n"+"\n".join(f"({k}:{v['type']})," for k,v in fields.items())+"\n]",
            "allowed_tables":["events"],"allowed_fields_by_table":{"events":set(fields)},
            "sql_dialect":"mysql","datasource":SimpleNamespace(type="mysql"),"tracking_metadata":tracking,"event_scope":{}}
    monkeypatch.setattr(generator,"_node_collect_context",context)
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw: pytest.fail("must not call LLM"))
    c=config();c["retention"]["simultaneous"]={"enabled":True,"event":event("return"),"aggregation":"avg",
        "metricField":{**field("level"),"kind":"tracking-property","eventName":"return","propertyName":"level",
            "type":kind,"semanticType":kind,"propertyType":kind,"sourceField":"payload","jsonPath":"$.level","isJsonSubfield":True}}
    result=asyncio.run(generator._build_manual_chart_graph().ainvoke({"request":DashboardAiSqlGenerateRequest(datasource=1,context=c)}))
    assert result["response"].success, result["response"].issues
    assert "AVG(s.metric_value)" in result["response"].sql
    assert "AS DECIMAL(38, 10)" in result["response"].sql
