"""
脚本说明：验证手动看板 AI SQL 生成器的模型响应解析和异步调用行为。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from apps.ai_model.model_factory import LLMConfig
from apps.dashboard.crud import ai_sql_generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


class _Chunk:
    def __init__(self, content: Any) -> None:
        self.content = content


class _AsyncInvokePreferredLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.ainvoke_called = False

    def stream(self, _messages: list[Any]):
        raise AssertionError("async graph nodes must not call sync stream")

    async def astream(self, _messages: list[Any]):
        raise AssertionError("dashboard AI SQL generation must not call streaming astream")

    async def ainvoke(self, _messages: list[Any]):
        self.ainvoke_called = True
        return _Chunk(self.content)


class _SyncInvokeOnlyLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.invoke_called = False

    def stream(self, _messages: list[Any]):
        raise AssertionError("dashboard AI SQL generation must not call streaming stream")

    def invoke(self, _messages: list[Any]):
        self.invoke_called = True
        return _Chunk(self.content)


def test_response_from_model_text_parses_string_false_as_failed() -> None:
    """
    是什么：LLM 把 success 返回成字符串 false 时不能误判为成功。
    """
    response = ai_sql_generator._response_from_model_text(
        '{"success":"false","sql":"select 1","message":"配置不完整"}',
    )

    assert response.success is False
    assert response.sql == "select 1"
    assert response.message == "配置不完整"


def test_text_chunk_content_skips_unknown_complex_list_items() -> None:
    """
    是什么：复杂 chunk 项没有文本字段时，不把对象 repr 拼进 JSON 文本。
    """
    content = ai_sql_generator._text_chunk_content([
        {"text": '{"success":true'},
        SimpleNamespace(value="repr should not leak"),
        {"content": ',"sql":"select 1"}'},
    ])

    assert "repr should not leak" not in content
    assert content == '{"success":true,"sql":"select 1"}'


def test_async_invoke_llm_json_uses_ainvoke_not_streaming() -> None:
    """
    是什么：异步图节点的 LLM 调用走 ainvoke，避免手动看板生成 SQL 使用流式输出。
    """
    llm = _AsyncInvokePreferredLlm('{"success":true,"sql":"select 1"}')

    response = asyncio.run(ai_sql_generator._async_invoke_llm_json(llm, [HumanMessage(content="生成 SQL")]))

    assert llm.ainvoke_called is True
    assert response.success is True
    assert response.sql == "select 1"


def test_invoke_llm_json_uses_invoke_not_streaming() -> None:
    """
    是什么：同步兜底调用也走 invoke，避免手动看板生成 SQL 使用流式输出。
    """
    llm = _SyncInvokeOnlyLlm('{"success":true,"sql":"select 1"}')

    response = ai_sql_generator._invoke_llm_json(llm, [HumanMessage(content="生成 SQL")])

    assert llm.invoke_called is True
    assert response.success is True
    assert response.sql == "select 1"


def test_create_dashboard_ai_sql_llm_disables_enable_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：手动看板三次 LLM 调用创建模型时，要统一关闭模型思考输出。
    """
    config = LLMConfig(
        model_id=7,
        model_type="openai",
        model_name="qwen3.5-plus",
        api_key="test-key",
        api_base_url="https://example.test/v1",
        additional_params={
            "temperature": 0.6,
            "extra_body": {"enable_thinking": True, "foo": "bar"},
        },
    )
    captured: dict[str, Any] = {}

    async def _fake_config(_model_id: int | None = None):
        return config

    def _fake_create_llm(updated_config: LLMConfig):
        captured["config"] = updated_config
        return SimpleNamespace(llm="fake-llm")

    monkeypatch.setattr(ai_sql_generator, "get_default_config", _fake_config)
    monkeypatch.setattr(ai_sql_generator.LLMFactory, "create_llm", _fake_create_llm)

    llm = asyncio.run(ai_sql_generator._create_dashboard_ai_sql_llm(7))

    assert llm == "fake-llm"
    assert captured["config"].additional_params["temperature"] == 0.6
    assert captured["config"].additional_params["extra_body"] == {
        "enable_thinking": False,
        "foo": "bar",
    }


def test_write_llm_output_debug_file_writes_jsonl(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：手动看板点击计算/生成时，LLM 原始输出要能落到 JSONL 文件便于排查。
    """
    output_file = tmp_path / "dashboard-ai-sql-llm-output.jsonl"
    monkeypatch.setattr(ai_sql_generator, "DASHBOARD_AI_SQL_LLM_OUTPUT_FILE", output_file)

    ai_sql_generator._write_llm_output_debug_file(
        node="generate_sql",
        full_text='{"success":true,"sql":"select 1"}',
        require_sql=True,
    )

    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["node"] == "generate_sql"
    assert payload["require_sql"] is True
    assert payload["output"] == '{"success":true,"sql":"select 1"}'
    assert payload["created_at"]


def test_dashboard_prompt_describes_formula_metrics_contract() -> None:
    """
    是什么：手动图表 SQL 生成提示词必须明确公式指标结构和除零规则。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看转化率",
            chart_type="line",
            context={
                "metrics": [{"id": "m1", "alias": "注册人数"}, {"id": "m2", "alias": "登录人数"}],
                "formulaMetrics": [
                    {
                        "id": "f1",
                        "alias": "注册登录比",
                        "decimalPlaces": 2,
                        "tokens": [
                            {"type": "metric", "metricId": "m1", "metricAlias": "注册人数"},
                            {"type": "operator", "value": "/"},
                            {"type": "metric", "metricId": "m2", "metricAlias": "登录人数"},
                        ],
                    }
                ],
                "groups": [],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="postgresql", type_name="PostgreSQL"),
        data_skill="",
        tracking_config="",
    )

    assert "formulaMetrics" in prompt
    assert "atomicMetric" in prompt
    assert "NULLIF" in prompt
    assert "ROUND" in prompt
    assert "外层 SELECT" in prompt


def test_dashboard_prompt_for_mysql_forbids_full_outer_join() -> None:
    """
    是什么：MySQL 数据源下手动图表 SQL 生成提示词要禁止生成 FULL OUTER JOIN。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看美国地区 ARPU",
            chart_type="table",
            context={
                "time": {"field": {"table": "event", "field": "dt"}, "grain": "day", "range": "30d"},
                "metrics": [{"alias": "后端充值"}, {"alias": "当日活跃"}],
                "formulaMetrics": [{"alias": "ARPU"}],
                "groups": [],
                "filters": {"logic": "and", "rules": [{"field": {"table": "event", "field": "country"}, "operator": "eq", "value": "US"}]},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
        sql_dialect="mysql",
    )

    assert "FULL OUTER JOIN" in prompt
    assert "不能使用" in prompt
    assert "UNION" in prompt
    assert "条件聚合" in prompt


def test_dashboard_prompt_for_mysql_does_not_globally_forbid_unsigned_casts() -> None:
    """
    是什么：MySQL 数据源下手动图表 SQL 生成提示词不能错误禁止标准方言支持的 UNSIGNED。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看最近 7 天每日新增用户",
            chart_type="line",
            context={
                "time": {"field": {"table": "event", "field": "dt"}, "grain": "day", "range": "7d"},
                "metrics": [{"alias": "新增用户数"}],
                "groups": [],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
        sql_dialect="mysql",
    )

    assert "不能使用 CAST(... AS UNSIGNED)" not in prompt


def test_dashboard_prompt_requires_tracking_event_prefilter_for_multiple_event_metrics() -> None:
    """
    是什么：多个事件类指标共用事件名字段时，提示词要要求先用 WHERE IN 收窄扫描范围。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看英雄养成事件",
            chart_type="table",
            context={
                "metrics": [
                    {
                        "alias": "英雄升星次数",
                        "field": {
                            "kind": "tracking-event",
                            "eventTable": "event",
                            "eventNameField": "event",
                            "eventName": "HeroStarUp",
                        },
                        "aggregation": "count",
                    },
                    {
                        "alias": "英雄升级次数",
                        "field": {
                            "kind": "tracking-event",
                            "eventTable": "event",
                            "eventNameField": "event",
                            "eventName": "HeroLevelUp",
                        },
                        "aggregation": "count",
                    },
                ],
                "groups": [],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
    )

    assert "WHERE" in prompt
    assert "IN" in prompt
    assert "收窄扫描范围" in prompt


def test_dashboard_prompt_treats_event_metric_filters_as_optional() -> None:
    """
    是什么：事件指标没有筛选条件也是合法配置，不能要求每个事件都补筛选。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看 DAU",
            chart_type="line",
            context={
                "metrics": [],
                "formulaMetrics": [
                    {
                        "id": "f1",
                        "alias": "DAU",
                        "decimalPlaces": 2,
                        "tokens": [
                            {
                                "type": "atomicMetric",
                                "metric": {
                                    "field": {
                                        "kind": "tracking-event",
                                        "eventTable": "event",
                                        "eventNameField": "event",
                                        "eventName": "UserActive",
                                    },
                                    "aggregation": "count_distinct",
                                    "metric": {"table": "event", "field": "uid"},
                                    "filters": {"logic": "and", "rules": []},
                                },
                            }
                        ],
                    }
                ],
                "groups": [{"field": {"table": "event", "field": "country"}}],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
    )

    assert "指标内筛选 rules 是可选配置" in prompt
    assert "没有 rules" in prompt
    assert "不要要求补筛选条件" in prompt
    assert "不要生成空 WHERE" in prompt


def _cross_event_arpu_formula_request() -> DashboardAiSqlGenerateRequest:
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看近 30 天每日 ARPU",
        chart_type="line",
        context={
            "metrics": [],
            "formulaMetrics": [
                {
                    "id": "arpu",
                    "alias": "ARPU",
                    "decimalPlaces": 2,
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "id": "revenue",
                                "field": {
                                    "kind": "tracking-event",
                                    "eventTable": "event",
                                    "eventNameField": "event",
                                    "eventName": "ServerPayLog",
                                },
                                "metric": {
                                    "table": "event",
                                    "field": "personal.money",
                                    "category": "number",
                                    "isJsonSubfield": True,
                                    "sourceField": "personal",
                                    "jsonPath": "$.money",
                                    "expression": "CAST(JSON_UNQUOTE(JSON_EXTRACT(`event`.`personal`, '$.money')) AS DECIMAL(38, 10))",
                                },
                                "aggregation": "sum",
                                "alias": "后端充值金额",
                                "label": "后端充值金额求和",
                                "filters": [],
                            },
                        },
                        {"type": "operator", "value": "/"},
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "id": "active_users",
                                "field": {
                                    "kind": "tracking-event",
                                    "eventTable": "event",
                                    "eventNameField": "event",
                                    "eventName": "UserActive",
                                },
                                "metric": {
                                    "table": "event",
                                    "field": "uid",
                                    "category": "string",
                                },
                                "aggregation": "count_distinct",
                                "alias": "当日活跃用户数",
                                "label": "当日活跃用户去重数",
                                "filters": [],
                            },
                        },
                    ],
                }
            ],
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def test_formula_ir_allows_cross_event_atomic_metric_formula_without_blocking() -> None:
    """
    是什么：ARPU 这类跨事件 atomicMetric 公式要解析成 IR，并由代码层判定可继续生成 SQL。
    """
    request = _cross_event_arpu_formula_request()

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is True
    assert validation.issues == []
    assert any("不同事件" in warning for warning in validation.warnings)
    formula = formula_ir["formulas"][0]
    assert formula["alias"] == "ARPU"
    assert formula["decimal_places"] == 2
    assert formula["expression"]["type"] == "binary"
    assert formula["expression"]["operator"] == "/"
    assert {item["event"] for item in formula["base_metrics"]} == {"ServerPayLog", "UserActive"}


def test_formula_ir_preserves_json_subfield_mapping() -> None:
    """
    是什么：公式事件指标的 JSON 子字段映射必须完整进入公式 IR，供 SQL 节点确定性使用。
    """
    request = _cross_event_arpu_formula_request()

    formula = ai_sql_generator._build_formula_ir(
        ai_sql_generator._normalize_manual_config(request)
    )["formulas"][0]
    revenue = next(item for item in formula["base_metrics"] if item["id"] == "revenue")

    assert revenue["metric_field"]["sourceField"] == "personal"
    assert revenue["metric_field"]["jsonPath"] == "$.money"


def test_normalize_manual_config_compiles_json_subfield_expression() -> None:
    """
    是什么：后端必须按当前方言从 sourceField/jsonPath 编译受控 JSON 表达式。
    """
    request = _cross_event_arpu_formula_request()

    normalized = ai_sql_generator._normalize_manual_config(request, datasource_type="mysql")
    metric_field = normalized["formula_metrics"][0]["tokens"][0]["metric"]["metric"]

    assert metric_field["expression"] == (
        "CAST(JSON_UNQUOTE(JSON_EXTRACT(`event`.`personal`, '$.money')) AS DECIMAL(38, 10))"
    )


def test_deterministic_validation_blocks_json_subfield_without_mapping() -> None:
    """
    是什么：JSON 子字段没有物理列、路径或受控表达式时，不能让 LLM 猜测 SQL。
    """
    request = _cross_event_arpu_formula_request()
    measure = request.context["formulaMetrics"][0]["tokens"][0]["metric"]["metric"]
    measure.update({"sourceField": "", "jsonPath": "", "expression": ""})

    normalized = ai_sql_generator._normalize_manual_config(request)
    validation = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
    )

    assert validation.success is False
    assert any("JSON 字段映射不完整" in issue for issue in validation.issues)


def test_deterministic_validation_allows_non_json_field_with_source_metadata() -> None:
    """
    是什么：普通物理字段即使带有 sourceField 元数据，也不能被误判为 JSON 子字段。
    """
    request = _cross_event_arpu_formula_request()
    active_users = request.context["formulaMetrics"][0]["tokens"][2]["metric"]["metric"]
    active_users.update({"sourceField": "uid", "isJsonSubfield": False})

    normalized = ai_sql_generator._normalize_manual_config(request)
    validation = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
    )

    assert validation.success is True
    assert not any("当日活跃用户数" in issue and "JSON 字段映射" in issue for issue in validation.issues)


def test_json_subfield_sql_validation_rejects_wrong_host_column() -> None:
    """
    是什么：LLM 把 JSON 宿主列或路径写错时，即使 SQL 语法有效也必须被拒绝。
    """
    requirements = [{"label": "后端充值金额", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.personal.money')) FROM event e"

    issues = ai_sql_generator._json_subfield_sql_issues(sql, requirements, dialect="mysql")

    assert any("JSON 列或路径" in issue for issue in issues)


def test_json_subfield_sql_validation_reports_exact_missing_config_location() -> None:
    requirements = [
        {
            "label": "全局筛选[0]",
            "source_field": "currentinfo",
            "json_path": "$._eventTime",
        }
    ]

    issues = ai_sql_generator._json_subfield_sql_issues(
        "SELECT e.event FROM event e",
        requirements,
        dialect="mysql",
    )

    assert issues[0] == (
        "全局筛选[0]：JSON 字段 currentinfo + $._eventTime 未出现在生成 SQL 中。"
    )


def test_json_subfield_sql_validation_accepts_matching_mysql_host_column() -> None:
    """
    是什么：MySQL SQL 使用当前字段配置的宿主列和路径时必须通过校验。
    """
    requirements = [{"label": "后端充值金额", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) FROM event e"

    assert ai_sql_generator._json_subfield_sql_issues(sql, requirements, dialect="mysql") == []


def test_json_subfield_sql_validation_accepts_postgres_json_path() -> None:
    """
    是什么：PostgreSQL 的 JSONB 路径语法也必须映射到同一份字段元数据。
    """
    requirements = [{"label": "收入", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT (e.personal::jsonb #>> '{money}') FROM event e"

    assert ai_sql_generator._json_subfield_sql_issues(sql, requirements, dialect="postgres") == []


def test_json_subfield_sql_validation_accepts_clickhouse_json_path() -> None:
    """
    是什么：ClickHouse 的 JSON_VALUE 路径也必须映射到同一份字段元数据。
    """
    requirements = [{"label": "收入", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT JSON_VALUE(e.personal, '$.money') FROM event e"

    assert ai_sql_generator._json_subfield_sql_issues(sql, requirements, dialect="clickhouse") == []


def test_validate_sql_node_blocks_json_subfield_mapping_mismatch() -> None:
    """
    是什么：图节点必须在只读校验前拒绝宿主列或路径错误的 JSON SQL。
    """
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        sql="SELECT JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.personal.money')) FROM event e",
    )

    result = ai_sql_generator._node_validate_sql({
        "response": response,
        "json_subfield_requirements": [
            {"label": "后端充值金额", "source_field": "personal", "json_path": "$.money"}
        ],
        "sql_dialect": "mysql",
    })

    assert result["response"].success is False
    assert "JSON 字段映射" in result["response"].message


def test_formula_ir_allows_arppu_atomic_metric_formula_without_blocking() -> None:
    """
    是什么：ARPPU 由同一事件下的收入和付费用户数组成，也应由 IR 正常表达并通过校验。
    """
    request = _cross_event_arpu_formula_request()
    request.intent = "看近 30 天每日 ARPPU"
    request.context["formulaMetrics"][0]["id"] = "arppu"
    request.context["formulaMetrics"][0]["alias"] = "ARPPU"
    request.context["formulaMetrics"][0]["tokens"][2]["metric"]["id"] = "paying_users"
    request.context["formulaMetrics"][0]["tokens"][2]["metric"]["field"]["eventName"] = "ServerPayLog"
    request.context["formulaMetrics"][0]["tokens"][2]["metric"]["alias"] = "付费用户数"
    request.context["formulaMetrics"][0]["tokens"][2]["metric"]["label"] = "付费用户去重数"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is True
    assert validation.issues == []
    assert validation.warnings == []


def test_formula_ir_allows_payer_rate_and_conversion_cross_event_formulas_without_blocking() -> None:
    """
    是什么：付费率、转化率这类跨事件分子分母公式不能因为跨事件本身被阻断。
    """
    for alias, numerator_event, denominator_event in [
        ("付费率", "ServerPayLog", "UserActive"),
        ("注册登录转化率", "UserLogin", "UserRegister"),
    ]:
        request = _cross_event_arpu_formula_request()
        request.context["formulaMetrics"][0]["id"] = alias
        request.context["formulaMetrics"][0]["alias"] = alias
        request.context["formulaMetrics"][0]["tokens"][0]["metric"] = {
            "id": "numerator_users",
            "field": {
                "kind": "tracking-event",
                "eventTable": "event",
                "eventNameField": "event",
                "eventName": numerator_event,
            },
            "metric": {"table": "event", "field": "uid", "category": "string"},
            "aggregation": "count_distinct",
            "alias": "分子用户数",
            "label": "分子用户去重数",
            "filters": [],
        }
        request.context["formulaMetrics"][0]["tokens"][2]["metric"] = {
            "id": "denominator_users",
            "field": {
                "kind": "tracking-event",
                "eventTable": "event",
                "eventNameField": "event",
                "eventName": denominator_event,
            },
            "metric": {"table": "event", "field": "uid", "category": "string"},
            "aggregation": "count_distinct",
            "alias": "分母用户数",
            "label": "分母用户去重数",
            "filters": [],
        }

        normalized = ai_sql_generator._normalize_manual_config(request)
        formula_ir = ai_sql_generator._build_formula_ir(normalized)
        validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

        assert validation.success is True
        assert validation.issues == []
        assert any("不同事件" in warning for warning in validation.warnings)


def test_formula_ir_blocks_incomplete_formula_token_sequence() -> None:
    """
    是什么：公式 token 不完整要由确定性校验阻断，不再交给 LLM 猜测。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"] = request.context["formulaMetrics"][0]["tokens"][:2]

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("除号后缺少指标或数字" in issue for issue in validation.issues)


def test_formula_ir_blocks_dividing_by_literal_zero() -> None:
    """
    是什么：明确除以常量 0 属于确定性阻断，不能交给 SQL 节点自由生成。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"] = [
        request.context["formulaMetrics"][0]["tokens"][0],
        {"type": "operator", "value": "/"},
        {"type": "number", "value": "0"},
    ]

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("除以常量 0" in issue for issue in validation.issues)


def test_formula_ir_blocks_sum_on_known_non_numeric_field() -> None:
    """
    是什么：字段元数据明确是非数值时，sum/avg 要在确定性校验阶段阻断。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["metric"]["category"] = "string"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("不是数值字段" in issue for issue in validation.issues)
    assert any("personal.money" in issue for issue in validation.issues)


def test_formula_ir_blocks_avg_on_chinese_text_category_field() -> None:
    """
    是什么：中文 tracking 元数据的“文本”类别同样必须阻断平均值聚合。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["aggregation"] = "avg"
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["metric"]["category"] = "文本"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("不是数值字段" in issue for issue in validation.issues)


def test_formula_ir_allows_sum_on_chinese_numeric_category_field() -> None:
    """
    是什么：中文 tracking 元数据的“数值”类别允许求和。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["metric"]["category"] = "数值"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is True
    assert not any("不是数值字段" in issue for issue in validation.issues)


def test_formula_ir_blocks_atomic_metric_missing_aggregation() -> None:
    """
    是什么：公式内 atomicMetric 必须显式声明聚合方式，不能静默降级为 count。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"].pop("aggregation")

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("缺少聚合方式" in issue for issue in validation.issues)


def test_formula_ir_blocks_atomic_metric_missing_metric_field_even_for_count() -> None:
    """
    是什么：公式内 atomicMetric 缺少计算字段要阻断，即使聚合方式是 count。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["aggregation"] = "count"
    request.context["formulaMetrics"][0]["tokens"][0]["metric"].pop("metric")

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("缺少计算字段" in issue for issue in validation.issues)


def test_formula_ir_allows_sum_on_integer_category_field() -> None:
    """
    是什么：字段 category/type 是 int、bigint、decimal 等数值类型名时，sum 不应被误阻断。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["metric"]["category"] = "bigint"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is True
    assert not any("不是数值字段" in issue for issue in validation.issues)


def test_formula_ir_blocks_formula_referencing_another_formula_metric() -> None:
    """
    是什么：第一版不支持公式引用另一个公式指标，需要明确阻断。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"].append({
        "id": "double_arpu",
        "alias": "双倍 ARPU",
        "tokens": [
            {"type": "metric", "metricId": "arpu"},
            {"type": "operator", "value": "*"},
            {"type": "number", "value": "2"},
        ],
    })

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("暂不支持公式引用另一个公式指标" in issue for issue in validation.issues)


def test_deterministic_validation_blocks_unsupported_aggregation() -> None:
    """
    是什么：后端不能信任前端传入的任意聚合方式，未知聚合要阻断。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["aggregation"] = "median"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("不支持的聚合方式" in issue for issue in validation.issues)


def test_deterministic_validation_blocks_tracking_event_missing_required_metadata() -> None:
    """
    是什么：tracking-event 缺少事件表、事件名字段或事件名时，不能进入 SQL 生成。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["field"] = {
        "kind": "tracking-event",
        "eventTable": "event",
        "eventNameField": "event",
        "eventName": "",
    }

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(request, normalized, formula_ir)

    assert validation.success is False
    assert any("缺少事件名" in issue for issue in validation.issues)


def test_deterministic_validation_blocks_unauthorized_table_field() -> None:
    """
    是什么：字段所属表不在 allowed_tables 时要阻断，避免绕过数据源权限上下文。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["field"]["eventTable"] = "secret_payments"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        formula_ir,
        allowed_tables=["event"],
    )

    assert validation.success is False
    assert any("无权限" in issue and "secret_payments" in issue for issue in validation.issues)


def test_dashboard_event_scope_uses_workspace_default_event_table() -> None:
    config = SimpleNamespace(
        id=1,
        enabled=True,
        datasource_id=6,
        default_event_table="event_log",
    )

    scope = ai_sql_generator._dashboard_event_scope(config, datasource_id=6)

    assert scope == {
        "mode": "event",
        "status": "active",
        "default_event_table": "event_log",
        "table_list": ["event_log"],
        "issues": [],
    }


def test_dashboard_event_scope_blocks_invalid_workspace_configuration() -> None:
    missing_table = ai_sql_generator._dashboard_event_scope(
        SimpleNamespace(id=1, enabled=True, datasource_id=6, default_event_table=None),
        datasource_id=6,
    )
    mismatched_datasource = ai_sql_generator._dashboard_event_scope(
        SimpleNamespace(id=1, enabled=True, datasource_id=7, default_event_table="event"),
        datasource_id=6,
    )
    unavailable_table = ai_sql_generator._dashboard_event_scope(
        SimpleNamespace(id=1, enabled=True, datasource_id=6, default_event_table="event_log"),
        datasource_id=6,
        allowed_tables=["event"],
    )

    assert missing_table["status"] == "missing-default-table"
    assert missing_table["table_list"] == []
    assert missing_table["issues"] == ["当前工作空间未配置默认事件表，事件配置不可用。"]
    assert mismatched_datasource["status"] == "datasource-mismatch"
    assert unavailable_table["status"] == "table-unavailable"
    assert unavailable_table["issues"] == ["默认事件表 event_log 不存在或不可访问，事件配置不可用。"]


def test_dashboard_event_scope_keeps_unconfigured_workspace_in_general_mode() -> None:
    scope = ai_sql_generator._dashboard_event_scope(
        SimpleNamespace(id=None, enabled=True, datasource_id=6, default_event_table=None),
        datasource_id=6,
    )

    assert scope["mode"] == "general"
    assert scope["status"] == "general"
    assert scope["table_list"] is None
    assert scope["issues"] == []


def test_deterministic_validation_blocks_field_missing_from_schema() -> None:
    """
    是什么：字段不在当前 schema 白名单时要阻断，避免把不存在字段交给 SQL 节点猜。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["metric"]["field"] = "not_exists"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        formula_ir,
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"event", "uid", "personal.money"}},
    )

    assert validation.success is False
    assert any("字段不存在或无权限" in issue and "not_exists" in issue for issue in validation.issues)


def test_schema_field_allowlist_uses_table_name_without_mschema_comment() -> None:
    """
    是什么：M-Schema 表头带表注释时，字段仍应归入真实表名，不能把注释拼进权限键。
    """
    schema = """# Table: event, 事件明细表。每行是一条用户行为记录。
[
(event:text, 事件名称),
(time:date, 事件时间),
(currentinfo._eventTime:text, JSON 事件时间)
]
"""

    allowed_fields = ai_sql_generator._allowed_fields_by_table_from_schema(schema)

    assert allowed_fields == {
        "event": {"event", "time", "currentinfo._eventtime"},
    }


def test_deterministic_validation_blocks_cross_table_formula_without_join_rule() -> None:
    """
    是什么：第一版没有显式关联规则时，跨物理表公式要阻断；同一事件表内的跨事件公式仍允许。
    """
    request = _cross_event_arpu_formula_request()
    request.context["formulaMetrics"][0]["tokens"][0]["metric"]["field"]["eventTable"] = "payments"
    request.context["formulaMetrics"][0]["tokens"][2]["metric"]["field"]["eventTable"] = "sessions"

    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    validation = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        formula_ir,
        allowed_tables=["payments", "sessions"],
    )

    assert validation.success is False
    assert any("跨表" in issue and "关联规则" in issue for issue in validation.issues)


def test_explain_advice_keeps_success_when_deterministic_validation_passed() -> None:
    """
    是什么：advice 层只能合并 warning/suggestion，不能把已通过的确定性校验改成失败。
    """
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(success=True, sql="select 1")
    validation = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        warnings=["公式分子分母来自不同事件，系统会先分别聚合再相除。"],
        suggestions=["建议把公式别名改成业务可读名称。"],
    )

    result = ai_sql_generator._node_explain_advice({
        "response": response,
        "validation_result": validation,
        "graph_trace": [],
    })

    merged = result["response"]
    assert merged.success is True
    assert merged.sql == "select 1"
    assert merged.issues == []
    assert merged.warnings == validation.warnings
    assert merged.suggestions == validation.suggestions


def test_route_after_deterministic_validation_ignores_legacy_diagnosis_failure() -> None:
    """
    是什么：是否继续生成 SQL 只看确定性校验结果，不能再被旧 LLM diagnosis 失败状态阻断。
    """
    route = ai_sql_generator._route_after_deterministic_validate({
        "validation_result": ai_sql_generator.DashboardAiSqlGenerateResponse(success=True),
        "diagnosis": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=False,
            issues=["LLM 误判：跨事件公式不能生成。"],
        ),
    })

    assert route == "build_sql_plan"


def test_deterministic_validation_blocks_invalid_server_event_scope() -> None:
    request = _cross_event_arpu_formula_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)

    result = ai_sql_generator._node_deterministic_validate({
        "request": request,
        "normalized_config": normalized,
        "formula_ir": formula_ir,
        "allowed_tables": ["event"],
        "allowed_fields_by_table": {
            "event": {"event", "uid", "dt", "personal.money"},
        },
        "event_scope": {
            "mode": "event",
            "status": "table-unavailable",
            "default_event_table": "event_log",
            "table_list": [],
            "issues": ["默认事件表 event_log 不存在或不可访问，事件配置不可用。"],
        },
        "graph_trace": [],
    })

    validation = result["validation_result"]
    assert validation.success is False
    assert validation.issues[0] == "默认事件表 event_log 不存在或不可访问，事件配置不可用。"
    assert ai_sql_generator._route_after_deterministic_validate(result) == "finalize_response"


def test_validate_sql_rejects_multiple_statements_even_when_first_is_select() -> None:
    """
    是什么：SQL 校验不能只看开头；SELECT 后拼接写操作也必须阻断。
    """
    result = ai_sql_generator._node_validate_sql({
        "response": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=True,
            sql="SELECT 1; DROP TABLE users;",
        ),
        "datasource": SimpleNamespace(type="postgresql", type_name="PostgreSQL"),
        "graph_trace": [],
    })["response"]

    assert result.success is False
    assert any("只读" in issue or "exactly one statement" in issue for issue in result.issues)


def test_validate_sql_demotes_model_issues_after_readonly_sql_passed() -> None:
    """
    是什么：确定性校验和只读 SQL 校验通过后，LLM 生成节点的业务建议不能继续作为阻断 issues。
    """
    model_issue = "公式分母逻辑可能与业务口径不符，建议确认是否应使用付费用户数。"
    result = ai_sql_generator._node_validate_sql({
        "response": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=False,
            sql="SELECT 1",
            issues=[model_issue],
        ),
        "datasource": SimpleNamespace(type="postgresql", type_name="PostgreSQL"),
        "graph_trace": [],
    })["response"]

    assert result.success is True
    assert result.issues == []
    assert model_issue in result.suggestions


def test_dashboard_sql_prompt_includes_formula_ir_and_sql_plan() -> None:
    """
    是什么：SQL 生成节点要读取公式 IR 和 SQL plan，而不是依赖自然语言诊断猜公式。
    """
    request = _cross_event_arpu_formula_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    sql_plan = ai_sql_generator._build_sql_plan(normalized, formula_ir)

    prompt = ai_sql_generator._dashboard_sql_user_prompt({
        "request": request,
        "datasource": SimpleNamespace(name="测试数据源", type="postgresql", type_name="PostgreSQL"),
        "validation_result": ai_sql_generator.DashboardAiSqlGenerateResponse(success=True),
        "formula_ir": formula_ir,
        "sql_plan": sql_plan,
        "data_skill": "",
        "tracking_config": "",
        "allowed_tables": ["event"],
    })

    assert "<deterministic-validation>" in prompt
    assert "<formula-ir>" in prompt
    assert "<sql-plan>" in prompt
    assert "ServerPayLog" in prompt
    assert "UserActive" in prompt
    assert "NULLIF" in prompt


def test_dashboard_prompt_recommends_cte_layers_for_complex_analysis() -> None:
    """
    是什么：手动图表 SQL 生成提示词要把复杂分析优先引导为 CTE 分层结构。
    """
    prompt = ai_sql_generator._dashboard_sql_system_prompt() + "\n" + ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="按渠道看新增留存",
            chart_type="table",
            context={
                "time": {"field": {"table": "users", "field": "created_at"}, "grain": "day", "range": "过去30天"},
                "metrics": [{"alias": "用户注册用户数", "aggregation": "count_distinct"}],
                "groups": [{"field": {"table": "users", "field": "channel"}}],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="postgresql", type_name="PostgreSQL"),
        data_skill="",
        tracking_config="",
    )

    assert "复杂分析" in prompt
    assert "CTE" in prompt
    assert "bounds" in prompt
    assert "cohort" in prompt
    assert "behavior" in prompt
    assert "matched" in prompt
    assert "aggregated" in prompt
    assert "成熟窗口" in prompt


def _retention_request(**overrides):
    retention = {
        "entityField": {"table": "event", "field": "user_id", "value": "event.user_id"},
        "initialEvent": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "register", "field": "event_name",
        },
        "returnEvent": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "login", "field": "event_name",
        },
        "simultaneous": {"enabled": False, "event": None, "aggregation": "count"},
        "relatedProperty": {
            "enabled": False,
            "initialProperty": None,
            "returnProperty": None,
            "simultaneousProperty": None,
            "asGroup": False,
        },
    }
    retention.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="table",
        context={
            "analysisModel": "retention",
            "chart": {"type": "table"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "retention": retention,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def _funnel_request(**overrides):
    steps = [
        {
            "event": {
                "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
                "eventName": event_name, "field": "event_name",
            },
            "alias": alias,
            "filters": {"logic": "and", "rules": []},
            "relatedProperty": None,
        }
        for event_name, alias in (("register", "注册"), ("login", "登录"), ("purchase", "购买"))
    ]
    funnel = {
        "entityField": {"table": "event", "field": "user_id", "value": "event.user_id"},
        "steps": steps,
        "window": {"mode": "duration", "value": 1, "unit": "day"},
        "relatedPropertyEnabled": False,
    }
    funnel.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="funnel",
        context={
            "analysisModel": "funnel",
            "chart": {"type": "funnel"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "funnel": funnel,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def _distribution_request(**overrides):
    distribution = {
        "entityField": {"table": "event", "field": "user_id", "value": "event.user_id"},
        "event": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "login", "field": "event_name",
        },
        "eventFilters": {"logic": "and", "rules": []},
        "metric": {
            "kind": "property",
            "field": {"table": "event", "field": "amount", "type": "numeric"},
            "aggregation": "sum",
        },
        "interval": {"mode": "custom", "customBounds": [0, 10, 100]},
        "simultaneous": {"enabled": False, "event": None, "aggregation": "count", "metricField": None},
    }
    distribution.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="table",
        context={
            "analysisModel": "distribution",
            "chart": {"type": "table"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "distribution": distribution,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def _interval_request(**overrides):
    interval = {
        "entityField": {"table": "event", "field": "user_id", "value": "event.user_id"},
        "startEvent": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "login", "field": "event_name",
        },
        "startEventFilters": {"logic": "and", "rules": []},
        "endEvent": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "purchase", "field": "event_name",
        },
        "endEventFilters": {"logic": "and", "rules": []},
        "relatedProperty": {
            "enabled": True,
            "startProperty": {
                "kind": "tracking-property", "table": "event", "field": "session_id",
                "eventName": "login", "propertyType": "string",
            },
            "endProperty": {
                "kind": "tracking-property", "table": "event", "field": "session_id",
                "eventName": "purchase", "propertyType": "string",
            },
        },
        "limitSeconds": 3600,
    }
    interval.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="table",
        context={
            "analysisModel": "interval",
            "chart": {"type": "table"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "interval": interval,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def _path_request(**overrides):
    login = {
        "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
        "eventName": "login", "field": "event_name",
    }
    purchase = {
        "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
        "eventName": "purchase", "field": "event_name",
    }
    path = {
        "events": [
            {
                "id": "path-1",
                "event": login,
                "splitProperties": [{
                    "kind": "tracking-property", "table": "event", "field": "platform",
                    "eventName": "login", "propertyType": "string",
                }],
            },
            {"id": "path-2", "event": purchase, "splitProperties": []},
        ],
        "initialEvent": login,
        "sessionGapSeconds": 1800,
    }
    path.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="sankey",
        context={
            "analysisModel": "path",
            "chart": {"type": "sankey"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "path": path,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def test_path_config_has_independent_normalization_and_validation() -> None:
    request = _path_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "platform", "dt"}},
    )

    assert normalized["analysis_model"] == "path"
    assert normalized["path"]["sessionGapSeconds"] == 1800
    assert normalized["retention"] == {}
    assert normalized["funnel"] == {}
    assert normalized["distribution"] == {}
    assert normalized["interval"] == {}
    assert result.success is True
    assert result.analysis_model == "path"
    assert ai_sql_generator._config_reference_table_names(normalized, {}) == {"event"}


def test_path_rejects_invalid_initial_event_split_property_and_session_gap() -> None:
    request = _path_request(
        initialEvent={
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "logout", "field": "event_name",
        },
        sessionGapSeconds=86401,
    )
    request.context["path"]["events"][0]["splitProperties"] = [{
        "kind": "tracking-property", "table": "event", "field": "platform",
        "eventName": "purchase", "propertyType": "string",
    }]
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "platform", "dt"}},
    )

    assert "路径分析初始事件必须来自参与分析的事件。" in result.issues
    assert "路径分析会话间隔必须是 1 秒到 24 小时。" in result.issues
    assert "路径参与事件1拆分属性1不属于当前参与事件。" in result.issues


def test_path_prompt_sql_plan_and_result_contract_keep_sankey_semantics() -> None:
    request = _path_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("path")
    plan = ai_sql_generator._build_sql_plan(normalized, formula_ir)
    valid_sql = (
        "WITH ordered AS (SELECT LAG(event_name) OVER (PARTITION BY session_id ORDER BY dt) AS previous_event, "
        "session_id, dt FROM event), edges AS (SELECT previous_event AS path_source, event_name AS path_target, "
        "COUNT(*) AS path_value, 1 AS path_step FROM ordered WHERE session_gap_seconds <= 1800 GROUP BY previous_event, event_name) "
        "SELECT path_source, path_target, path_value, path_step FROM edges"
    )

    assert "只能使用 path 配置" in prompt
    assert "初始事件" in prompt
    assert "30 个" in prompt
    assert "sessionGapSeconds" in prompt
    assert "相邻" in prompt
    assert plan["analysis_model"] == "path"
    assert plan["result_contract"]["type"] == "path_sankey"
    assert plan["result_contract"]["required_columns"] == ["path_source", "path_target", "path_value", "path_step"]
    assert ai_sql_generator._path_sql_result_issues(valid_sql, normalized) == []
    invalid = ai_sql_generator._path_sql_result_issues("SELECT path_source, path_target FROM event", normalized)
    assert invalid
    assert any("path_value" in issue for issue in invalid)


def test_distribution_config_has_independent_normalization_and_validation() -> None:
    request = _distribution_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "amount", "dt"}},
    )

    assert normalized["analysis_model"] == "distribution"
    assert normalized["distribution"]["metric"]["kind"] == "property"
    assert normalized["retention"] == {}
    assert normalized["funnel"] == {}
    assert result.success is True
    assert result.analysis_model == "distribution"
    assert ai_sql_generator._config_reference_table_names(normalized, {}) == {"event"}


def test_distribution_rejects_invalid_interval_metric_and_simultaneous_config() -> None:
    request = _distribution_request(
        metric={"kind": "property", "field": None, "aggregation": "unsupported"},
        interval={"mode": "custom", "customBounds": [10, 10, 0]},
        simultaneous={"enabled": True, "event": None, "aggregation": "avg", "metricField": None},
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
    )

    assert result.success is False
    assert "分布分析选择事件属性指标时，请先选择事件属性。" in result.issues
    assert "分布分析使用了不支持的事件属性聚合方式：unsupported。" in result.issues
    assert "分布分析自定义区间需要 2 到 20 个严格递增的数字边界。" in result.issues
    assert "分布分析使用同时展示时请选择参与事件。" in result.issues


def test_distribution_count_metric_always_uses_discrete_intervals() -> None:
    request = _distribution_request(
        metric={"kind": "count", "field": None, "aggregation": "sum"},
        interval={"mode": "auto", "customBounds": [0, 10, 100]},
    )

    normalized = ai_sql_generator._normalize_manual_config(request)

    assert normalized["distribution"]["interval"] == {"mode": "discrete", "customBounds": []}


def test_distribution_prompt_and_result_contract_are_not_scatter_or_event_analysis() -> None:
    request = _distribution_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("distribution")
    valid_sql = (
        "SELECT distribution_date, total_entities, interval_order, interval_label, "
        "COUNT(DISTINCT entity_id) AS entity_count, "
        "COUNT(DISTINCT entity_id) * 100.0 / NULLIF(total_entities, 0) AS entity_rate "
        "FROM distribution_result GROUP BY distribution_date, interval_order, interval_label, total_entities"
    )

    assert "只使用 distribution 配置" in prompt or "只能使用 distribution 配置" in prompt
    assert "主体必须先聚合再分桶" in prompt
    assert "不得按日期或分组分别计算" in prompt
    assert "YYYY-MM-DD" in prompt
    assert "simultaneous_entity_value" in prompt
    assert "显式 LEFT JOIN" in prompt
    assert "禁止在 JOIN 条件中使用引用外层" in prompt
    assert normalized["analysis_model"] == "distribution"
    assert normalized["chart"]["type"] == "table"
    assert ai_sql_generator._distribution_sql_result_issues(valid_sql, normalized) == []
    invalid = ai_sql_generator._distribution_sql_result_issues(
        "SELECT interval_label, COUNT(*) AS entity_count FROM distribution_result GROUP BY interval_label",
        normalized,
    )
    assert invalid
    assert any("distribution_date" in issue for issue in invalid)
    assert any("total_entities" in issue for issue in invalid)


def test_distribution_sql_validation_rejects_adb_correlated_subquery_before_execution() -> None:
    request = _distribution_request(simultaneous={
        "enabled": True,
        "event": {
            "kind": "tracking-event",
            "eventTable": "event",
            "eventNameField": "event_name",
            "eventName": "login",
            "field": "event_name",
        },
        "aggregation": "count",
        "metricField": None,
    })
    normalized = ai_sql_generator._normalize_manual_config(request)
    sql = """
    WITH bucketed AS (
        SELECT dt AS distribution_date, user_id AS entity_id, 1 AS interval_order FROM event
    ),
    intervals AS (
        SELECT distribution_date, interval_order, '1' AS interval_label,
               COUNT(DISTINCT entity_id) AS entity_count,
               COUNT(DISTINCT entity_id) AS total_entities
        FROM bucketed GROUP BY distribution_date, interval_order
    ),
    simultaneous_agg AS (
        SELECT dt, user_id, COUNT(*) AS sim_value FROM event GROUP BY dt, user_id
    )
    SELECT i.distribution_date, i.total_entities, i.interval_order, i.interval_label,
           i.entity_count,
           i.entity_count * 100.0 / NULLIF(i.total_entities, 0) AS entity_rate,
           COALESCE(SUM(sa.sim_value), 0) AS simultaneous_value
    FROM intervals i
    LEFT JOIN simultaneous_agg sa
      ON i.distribution_date = sa.dt
     AND EXISTS (
         SELECT 1 FROM bucketed b
         WHERE b.distribution_date = i.distribution_date
           AND b.interval_order = i.interval_order
           AND b.entity_id = sa.user_id
     )
    GROUP BY i.distribution_date, i.total_entities, i.interval_order, i.interval_label, i.entity_count
    """

    response = ai_sql_generator.DashboardAiSqlGenerateResponse(success=True, sql=sql, chart_type="table")
    validated = ai_sql_generator._node_validate_sql({
        "response": response,
        "normalized_config": normalized,
        "datasource": SimpleNamespace(type="mysql"),
        "sql_dialect": "mysql",
        "graph_trace": [],
    })["response"]

    assert validated.success is False
    assert "数据源方言" in validated.message
    assert any("JOIN 条件不能使用引用外层列的关联子查询" in issue for issue in validated.issues)


def test_interval_config_has_independent_normalization_and_validation() -> None:
    request = _interval_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "session_id", "dt"}},
    )

    assert normalized["analysis_model"] == "interval"
    assert normalized["interval"]["limitSeconds"] == 3600
    assert normalized["retention"] == {}
    assert normalized["funnel"] == {}
    assert normalized["distribution"] == {}
    assert result.success is True
    assert result.analysis_model == "interval"
    assert ai_sql_generator._config_reference_table_names(normalized, {}) == {"event"}


def test_interval_allows_same_event_and_rejects_invalid_limit_or_property_type() -> None:
    same_event = {
        "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
        "eventName": "login", "field": "event_name",
    }
    valid_request = _interval_request(
        startEvent=same_event,
        endEvent=same_event,
        relatedProperty={"enabled": False, "startProperty": None, "endProperty": None},
    )
    valid_normalized = ai_sql_generator._normalize_manual_config(valid_request)
    valid_result = ai_sql_generator._deterministic_validate_manual_config(
        valid_request,
        valid_normalized,
        ai_sql_generator._build_formula_ir(valid_normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )
    assert valid_result.success is True

    invalid_request = _interval_request(
        limitSeconds=59,
        relatedProperty={
            "enabled": True,
            "startProperty": {
                "kind": "tracking-property", "table": "event", "field": "level_id",
                "eventName": "login", "propertyType": "integer",
            },
            "endProperty": {
                "kind": "tracking-property", "table": "event", "field": "level_name",
                "eventName": "purchase", "propertyType": "string",
            },
        },
    )
    invalid_normalized = ai_sql_generator._normalize_manual_config(invalid_request)
    invalid_result = ai_sql_generator._deterministic_validate_manual_config(
        invalid_request,
        invalid_normalized,
        ai_sql_generator._build_formula_ir(invalid_normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "level_id", "level_name", "dt"}},
    )
    assert invalid_result.success is False
    assert "间隔分析上限必须是 1 分钟到 180 天。" in invalid_result.issues
    assert "起点事件属性和终点事件属性的类型必须一致。" in invalid_result.issues


def test_interval_prompt_and_result_contract_enforce_pairing_semantics() -> None:
    request = _interval_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("interval")
    valid_sql = (
        "SELECT interval_date, COUNT(DISTINCT entity_id) AS entity_count, COUNT(*) AS interval_count, "
        "MAX(interval_seconds) AS max_interval_seconds, "
        "PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY interval_seconds) AS p75_interval_seconds, "
        "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY interval_seconds) AS median_interval_seconds, "
        "PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY interval_seconds) AS p25_interval_seconds, "
        "MIN(interval_seconds) AS min_interval_seconds, AVG(interval_seconds) AS avg_interval_seconds "
        "FROM valid_intervals GROUP BY interval_date"
    )

    assert "只能使用 interval 配置" in prompt
    assert "连续出现多个起点时只保留最后一个起点" in prompt
    assert "相同事件" in prompt and "N-1" in prompt
    assert "所有时长列必须为数值秒" in prompt
    assert ai_sql_generator._interval_sql_result_issues(valid_sql, normalized) == []
    invalid_issues = ai_sql_generator._interval_sql_result_issues(
        "SELECT interval_date, COUNT(*) AS interval_count FROM valid_intervals GROUP BY interval_date",
        normalized,
    )
    assert any("entity_count" in issue for issue in invalid_issues)
    assert any("分位数" in issue for issue in invalid_issues)


def test_funnel_config_uses_ordered_steps_and_deterministic_validation() -> None:
    request = _funnel_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert normalized["analysis_model"] == "funnel"
    assert len(normalized["funnel"]["steps"]) == 3
    assert result.success is True
    assert ai_sql_generator._config_reference_table_names(normalized, {}) == {"event"}


def test_funnel_config_rejects_missing_step_and_invalid_chart() -> None:
    request = _funnel_request(
        steps=[{"event": None, "relatedProperty": None}],
        window={"mode": "duration", "value": 0, "unit": "day"},
        relatedPropertyEnabled=True,
    )
    request.context["chart"] = {"type": "table"}
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
    )

    assert result.success is False
    assert "漏斗分析至少需要配置两个步骤。" in result.issues
    assert "漏斗步骤1请先选择事件。" in result.issues
    assert "使用关联属性时请选择漏斗步骤1关联属性。" in result.issues
    assert "漏斗分析窗口期必须是正整数。" in result.issues
    assert "漏斗分析只能使用漏斗图结果。" in result.issues


@pytest.mark.parametrize(
    "window",
    [
        {"mode": "same_day", "value": 1, "unit": "day"},
        {"mode": "duration", "value": 14, "unit": "day"},
        {"mode": "duration", "value": 12, "unit": "hour"},
        {"mode": "duration", "value": 30, "unit": "minute"},
    ],
)
def test_funnel_config_accepts_supported_window_modes(window) -> None:
    request = _funnel_request(window=window)
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )
    assert normalized["funnel"]["window"] == window
    assert result.success is True


def _attribution_request(**overrides):
    login = {
        "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
        "eventName": "login", "field": "event_name",
    }
    purchase = {
        "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
        "eventName": "purchase", "field": "event_name",
    }
    attribution = {
        "entityField": {"table": "event", "field": "user_id"},
        "method": "linear",
        "window": {"mode": "custom", "value": 7, "unit": "day"},
        "targetEvent": purchase,
        "targetEventFilters": {"logic": "and", "rules": []},
        "targetMetric": {"aggregation": "count", "metricField": None},
        "includeDirect": True,
        "events": [
            {"id": "touch-1", "event": login, "filters": {"logic": "and", "rules": []}},
        ],
    }
    attribution.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="table",
        context={
            "analysisModel": "attribution",
            "chart": {"type": "table"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "attribution": attribution,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def test_attribution_config_has_independent_normalization_and_validation() -> None:
    request = _attribution_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert normalized["analysis_model"] == "attribution"
    assert normalized["attribution"]["window"]["value"] == 7
    assert normalized["retention"] == {}
    assert normalized["funnel"] == {}
    assert normalized["distribution"] == {}
    assert normalized["interval"] == {}
    assert normalized["path"] == {}
    assert result.success is True
    assert result.analysis_model == "attribution"
    assert ai_sql_generator._config_reference_table_names(normalized, {}) == {"event"}


def test_attribution_rejects_invalid_window_and_target_metric() -> None:
    request = _attribution_request(
        window={"mode": "custom", "value": 0, "unit": "day"},
        targetMetric={"aggregation": "sum", "metricField": None},
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
    )

    assert result.success is False
    assert "归因分析窗口期必须在 1 分钟到 365 天之间。" in result.issues
    assert "目标事件使用非次数聚合时，请选择计算字段。" in result.issues


def test_attribution_prompt_plan_and_result_contract_keep_linear_semantics() -> None:
    request = _attribution_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("attribution")
    plan = ai_sql_generator._build_sql_plan(normalized, ai_sql_generator._build_formula_ir(normalized))
    valid_sql = (
        "WITH matched AS (SELECT target_id, 1.0 / NULLIF(touch_count, 0) AS linear_weight FROM targets) "
        "SELECT attribution_event, COUNT(DISTINCT target_id) AS target_count, "
        "SUM(target_value * linear_weight) AS attributed_value, "
        "SUM(target_value) * 100.0 / NULLIF(SUM(target_value), 0) AS contribution_rate FROM matched "
        "GROUP BY attribution_event"
    )

    assert "只能使用 attribution 配置" in prompt
    assert "线性归因" in prompt
    assert plan["analysis_model"] == "attribution"
    assert plan["result_contract"]["type"] == "attribution_table"
    assert ai_sql_generator._attribution_sql_result_issues(valid_sql, normalized) == []
    invalid = ai_sql_generator._attribution_sql_result_issues(
        "SELECT attribution_event, COUNT(*) AS target_count FROM matched GROUP BY attribution_event",
        normalized,
    )
    assert invalid
    assert any("attributed_value" in issue for issue in invalid)


def _ranking_request(**overrides):
    ranking = {
        "entityField": {"table": "event", "field": "user_id", "value": "event.user_id"},
        "metric": {
            "event": {
                "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
                "eventName": "login", "field": "event_name",
            },
            "alias": "登录次数",
            "aggregation": "count",
            "metricField": "",
            "direction": "desc",
        },
        "tieHandling": "skip",
        "simultaneousMetrics": [{
            "id": "metric-1",
            "event": {
                "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
                "eventName": "purchase", "field": "event_name",
            },
            "alias": "购买次数",
            "aggregation": "count",
            "metricField": "",
        }],
        "simultaneousProperties": [{"table": "event", "field": "country", "value": "event.country"}],
    }
    ranking.update(overrides)
    return DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="table",
        context={
            "analysisModel": "ranking",
            "chart": {"type": "table"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
            },
            "ranking": ranking,
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )


def test_ranking_config_has_independent_normalization_and_validation() -> None:
    request = _ranking_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt", "country"}},
    )

    assert normalized["analysis_model"] == "ranking"
    assert normalized["ranking"]["tieHandling"] == "skip"
    assert normalized["retention"] == {}
    assert normalized["distribution"] == {}
    assert normalized["path"] == {}
    assert result.success is True
    assert result.analysis_model == "ranking"


def test_ranking_rejects_invalid_direction_and_metric_field() -> None:
    request = _ranking_request(metric={
        "event": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "login", "field": "event_name",
        },
        "aggregation": "sum",
        "metricField": {"table": "event", "field": "country", "type": "string"},
        "direction": "sideways",
    })
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt", "country"}},
    )

    assert result.success is False
    assert any("排序方向" in issue for issue in result.issues)
    assert any("不是数值字段" in issue for issue in result.issues)


def test_ranking_prompt_plan_and_result_contract_keep_rank_semantics() -> None:
    request = _ranking_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    ) + "\n" + ai_sql_generator._dashboard_sql_system_prompt("ranking")
    plan = ai_sql_generator._build_sql_plan(normalized, ai_sql_generator._build_formula_ir(normalized))
    valid_sql = (
        "WITH entity_values AS (SELECT user_id AS ranking_entity, COUNT(*) AS ranking_value FROM event GROUP BY user_id), "
        "ranked AS (SELECT RANK() OVER (ORDER BY ranking_value DESC) AS rank, ranking_entity, ranking_value, "
        "COUNT(*) AS simultaneous_metric_1, MAX(country) AS ranking_property_1 FROM entity_values GROUP BY ranking_entity, ranking_value) "
        "SELECT rank, ranking_entity, ranking_value, simultaneous_metric_1, ranking_property_1 FROM ranked ORDER BY rank"
    )

    assert "只能使用 ranking 配置" in prompt
    assert "attribution/ranking 字段信息" in prompt
    assert "并列名次" in prompt
    assert plan["analysis_model"] == "ranking"
    assert plan["result_contract"]["type"] == "ranking_table"
    assert plan["result_contract"]["required_columns"] == [
        "rank", "ranking_entity", "ranking_value", "simultaneous_metric_1", "ranking_property_1",
    ]
    assert ai_sql_generator._ranking_sql_result_issues(valid_sql, normalized) == []
    invalid = ai_sql_generator._ranking_sql_result_issues(
        "SELECT ranking_entity, ranking_value FROM entity_values",
        normalized,
    )
    assert invalid
    assert any("rank" in issue for issue in invalid)

def test_funnel_config_migrates_legacy_window_days() -> None:
    request = _funnel_request(window=None, windowDays=7)
    normalized = ai_sql_generator._normalize_manual_config(request)

    assert normalized["funnel"]["window"] == {"mode": "duration", "value": 7, "unit": "day"}
    assert "windowDays" not in normalized["funnel"]


@pytest.mark.parametrize(
    ("window", "expected_issue"),
    [
        ({"mode": "calendar_week", "value": 1, "unit": "day"}, "模式必须是当天或时长"),
        ({"mode": "duration", "value": 1, "unit": "second"}, "单位必须是天、小时或分钟"),
        ({"mode": "duration", "value": 1.5, "unit": "hour"}, "必须是正整数"),
        ({"mode": "duration", "value": 366, "unit": "day"}, "不能超过 365 天"),
    ],
)
def test_funnel_config_rejects_invalid_window(window, expected_issue) -> None:
    request = _funnel_request(window=window)
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert result.success is False
    assert any(expected_issue in issue for issue in result.issues)


def test_funnel_prompt_and_result_validation_require_fixed_columns() -> None:
    request = _funnel_request()
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    invalid = ai_sql_generator._funnel_sql_result_issues(
        "SELECT step_name, step_count FROM funnel_result",
        normalized,
    )
    valid = ai_sql_generator._funnel_sql_result_issues(
        "SELECT step_order, step_name, step_count, step_rate, step_conversion_rate, step_dropoff_rate FROM funnel_result",
        normalized,
    )

    assert "按同一分析主体去重计数" in prompt
    assert "funnel.window.mode=same_day" in prompt
    assert "1 天：按精确经过时长计算" in prompt
    assert "step_conversion_rate" in prompt
    assert invalid and "step_order" in invalid[0]
    assert valid == []


def test_funnel_same_day_prompt_does_not_convert_to_rolling_24_hours() -> None:
    request = _funnel_request(window={"mode": "same_day", "value": 1, "unit": "day"})
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    )

    assert "步骤 1 所在的同一个自然日" in prompt
    assert "不等同于滚动 24 小时" in prompt


def test_funnel_subject_and_step_fields_enforce_datasource_permissions() -> None:
    request = _funnel_request(
        entityField={"table": "private_event", "field": "user_id"},
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert result.success is False
    assert any("漏斗分析主体" in issue and "权限" in issue for issue in result.issues)


def test_retention_config_uses_independent_deterministic_validation() -> None:
    request = _retention_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)

    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        formula_ir,
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert result.success is True
    assert "至少需要配置一个分析指标" not in result.issues


def test_retention_config_allows_same_initial_and_return_event() -> None:
    same_event = {
        "kind": "tracking-event",
        "eventTable": "event",
        "eventNameField": "event_name",
        "eventName": "register",
        "field": "event_name",
    }
    request = _retention_request(initialEvent=same_event, returnEvent=same_event)
    normalized = ai_sql_generator._normalize_manual_config(request)

    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert result.success is True
    assert "初始事件和回访事件不能相同。" not in result.issues


def test_retention_config_rejects_missing_subject_and_events() -> None:
    request = _retention_request(entityField=None, initialEvent=None, returnEvent=None)
    normalized = ai_sql_generator._normalize_manual_config(request)

    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
    )

    assert result.success is False
    assert "留存分析请先选择分析主体。" in result.issues
    assert "留存分析请先选择初始事件。" in result.issues
    assert "留存分析请先选择回访事件。" in result.issues


def test_retention_prompt_and_sql_validation_require_fixed_cohort_columns() -> None:
    request = _retention_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    validation = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )
    sql_plan = ai_sql_generator._build_sql_plan(
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
    )
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    )
    invalid_sql = (
        "SELECT cohort_date, cohort_size, day_0 FROM retention_result "
        "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(success=True, sql=invalid_sql, chart_type="table")
    validated = ai_sql_generator._node_validate_sql({
        "response": response,
        "normalized_config": normalized,
        "graph_trace": [],
    })["response"]

    assert validation.analysis_model == "retention"
    assert sql_plan["analysis_model"] == "retention"
    assert sql_plan["result_contract"] == {
        "type": "cohort_table",
        "window_days": 7,
        "required_columns": ["cohort_date", "cohort_size", *[f"day_{day}" for day in range(8)]],
        "day_value": "retention_rate",
        "final_grain": ["cohort_date"],
    }
    assert "固定 Cohort 宽表" in prompt
    assert "day_0 到 day_7" in prompt
    assert validated.success is False
    assert "day_7" in validated.issues[0]


def test_retention_system_prompt_uses_wide_result_without_changing_event_prompt() -> None:
    retention_prompt = ai_sql_generator._dashboard_sql_system_prompt("retention")
    event_prompt = ai_sql_generator._dashboard_sql_system_prompt("event")

    assert "禁止把最终结果生成为按 period_offset 展开的长表" in retention_prompt
    assert "sql-plan.result_contract.required_columns" in retention_prompt
    assert "AS day_0" in retention_prompt
    assert "day_1 到 day_7" in retention_prompt
    assert "base_count,\n    matched_count,\n    matched_rate" not in retention_prompt
    assert "推荐 SQL 结构范式" in event_prompt
    assert "matched_rate" in event_prompt
    assert "留存专用 Cohort 宽表结构" not in event_prompt


def test_sql_validation_routes_retention_and_distribution_failures_to_one_repair() -> None:
    failed_response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        sql="SELECT cohort_date FROM matched",
        issues=["留存 SQL 缺少固定结果列：cohort_size、day_0。"],
    )

    assert ai_sql_generator._route_after_sql_validate({
        "normalized_config": {"analysis_model": "retention"},
        "response": failed_response,
        "sql_repair_attempts": 0,
    }) == "repair_retention_sql"
    assert ai_sql_generator._route_after_sql_validate({
        "normalized_config": {"analysis_model": "retention"},
        "response": failed_response,
        "sql_repair_attempts": 1,
    }) == "explain_advice"
    assert ai_sql_generator._route_after_sql_validate({
        "normalized_config": {"analysis_model": "event"},
        "response": failed_response,
        "sql_repair_attempts": 0,
    }) == "explain_advice"
    assert ai_sql_generator._route_after_sql_validate({
        "normalized_config": {"analysis_model": "funnel"},
        "response": failed_response,
        "sql_repair_attempts": 0,
    }) == "explain_advice"
    assert ai_sql_generator._route_after_sql_validate({
        "normalized_config": {"analysis_model": "distribution"},
        "response": failed_response,
        "sql_repair_attempts": 0,
    }) == "repair_distribution_sql"
    assert ai_sql_generator._route_after_sql_validate({
        "normalized_config": {"analysis_model": "distribution"},
        "response": failed_response,
        "sql_repair_attempts": 1,
    }) == "explain_advice"


def test_retention_repair_prompt_carries_contract_original_sql_and_issues() -> None:
    request = _retention_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    failed_sql = "SELECT cohort_dt, period_offset, matched_rate FROM matched"
    issue = "留存 SQL 缺少固定结果列：cohort_date、cohort_size、day_0。"
    prompt = ai_sql_generator._dashboard_sql_repair_user_prompt({
        "request": request,
        "datasource": SimpleNamespace(name="测试", type="mysql", type_name="MySQL"),
        "validation_result": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=True,
            analysis_model="retention",
        ),
        "formula_ir": formula_ir,
        "sql_plan": ai_sql_generator._build_sql_plan(normalized, formula_ir),
        "normalized_config": normalized,
        "response": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=False,
            sql=failed_sql,
            issues=[issue],
        ),
        "data_skill": "",
        "tracking_config": "",
        "allowed_tables": ["event"],
    })

    assert "<failed-sql>" in prompt
    assert failed_sql in prompt
    assert issue in prompt
    assert '"type": "cohort_table"' in prompt
    assert "完整重写 SQL" in prompt


def test_distribution_repair_prompt_carries_dialect_issue_and_explicit_join_contract() -> None:
    request = _distribution_request()
    normalized = ai_sql_generator._normalize_manual_config(request)
    formula_ir = ai_sql_generator._build_formula_ir(normalized)
    issue = "MySQL/AnalyticDB 的 JOIN 条件不能使用引用外层列的关联子查询。"
    prompt = ai_sql_generator._dashboard_sql_repair_user_prompt({
        "request": request,
        "datasource": SimpleNamespace(name="测试", type="mysql", type_name="MySQL"),
        "validation_result": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=True,
            analysis_model="distribution",
        ),
        "formula_ir": formula_ir,
        "sql_plan": ai_sql_generator._build_sql_plan(normalized, formula_ir),
        "normalized_config": normalized,
        "response": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=False,
            sql="SELECT * FROM intervals i LEFT JOIN metrics m ON EXISTS (SELECT 1 FROM bucketed b WHERE b.dt = i.dt)",
            issues=[issue],
        ),
        "data_skill": "",
        "tracking_config": "",
        "allowed_tables": ["event"],
    })

    assert "未通过分布 SQL 协议或方言校验" in prompt
    assert issue in prompt
    assert "显式 LEFT JOIN" in prompt


def test_retention_prompt_requires_typed_yyyymmdd_date_operations() -> None:
    prompt = ai_sql_generator._dashboard_config_prompt(
        _retention_request(),
        SimpleNamespace(name="测试", type="starrocks", type_name="StarRocks"),
        "",
        "",
        sql_dialect="mysql",
    )

    assert "YYYYMMDD 编码键，不是 DATE" in prompt
    assert "STR_TO_DATE(CAST(<yyyymmdd_expr> AS CHAR), '%Y%m%d')" in prompt
    assert "DATE_ADD(<cohort_date>, INTERVAL <window_days> DAY)" in prompt
    assert "DATEDIFF(<behavior_date>, <cohort_date>)" in prompt
    assert "禁止使用 FROM_DAYS" in prompt


def test_retention_sql_validation_rejects_untyped_yyyymmdd_date_operations() -> None:
    invalid_sql = """
WITH cohort AS (
    SELECT uid AS entity_id, dt AS cohort_dt
    FROM event
    WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
), behavior AS (
    SELECT uid AS entity_id, dt AS behavior_dt FROM event
), matched AS (
    SELECT
        c.entity_id,
        FROM_DAYS(c.cohort_dt) AS cohort_date,
        DATEDIFF(FROM_DAYS(c.cohort_dt), FROM_DAYS(b.behavior_dt)) AS days_diff
    FROM cohort c
    LEFT JOIN behavior b
      ON c.entity_id = b.entity_id
     AND b.behavior_dt <= c.cohort_dt + INTERVAL 7 DAY
)
SELECT cohort_date, 1 AS cohort_size,
       1 AS day_0, 1 AS day_1, 1 AS day_2, 1 AS day_3,
       1 AS day_4, 1 AS day_5, 1 AS day_6, 1 AS day_7
FROM matched
"""
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        sql=invalid_sql,
        chart_type="table",
    )

    validated = ai_sql_generator._node_validate_sql({
        "response": response,
        "normalized_config": ai_sql_generator._normalize_manual_config(_retention_request()),
        "sql_dialect": "starrocks",
        "graph_trace": [],
    })["response"]

    assert validated.success is False
    assert any("FROM_DAYS" in issue for issue in validated.issues)
    assert any("直接加减 INTERVAL" in issue for issue in validated.issues)
    assert any("DATEDIFF 参数顺序错误" in issue for issue in validated.issues)


def test_retention_sql_validation_allows_typed_yyyymmdd_date_operations() -> None:
    valid_sql = """
WITH event_dates AS (
    SELECT
        uid AS entity_id,
        STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS event_date
    FROM event
    WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
), matched AS (
    SELECT
        c.entity_id,
        c.event_date AS cohort_date,
        b.event_date AS behavior_date,
        DATEDIFF(b.event_date, c.event_date) AS days_diff
    FROM event_dates c
    LEFT JOIN event_dates b
      ON c.entity_id = b.entity_id
     AND b.event_date <= DATE_ADD(c.event_date, INTERVAL 7 DAY)
)
SELECT cohort_date, COUNT(DISTINCT entity_id) AS cohort_size,
       COUNT(DISTINCT CASE WHEN days_diff = 0 THEN entity_id END) AS day_0,
       COUNT(DISTINCT CASE WHEN days_diff = 1 THEN entity_id END) AS day_1,
       COUNT(DISTINCT CASE WHEN days_diff = 2 THEN entity_id END) AS day_2,
       COUNT(DISTINCT CASE WHEN days_diff = 3 THEN entity_id END) AS day_3,
       COUNT(DISTINCT CASE WHEN days_diff = 4 THEN entity_id END) AS day_4,
       COUNT(DISTINCT CASE WHEN days_diff = 5 THEN entity_id END) AS day_5,
       COUNT(DISTINCT CASE WHEN days_diff = 6 THEN entity_id END) AS day_6,
       COUNT(DISTINCT CASE WHEN days_diff = 7 THEN entity_id END) AS day_7
FROM matched
GROUP BY cohort_date
"""
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        sql=valid_sql,
        chart_type="table",
    )

    validated = ai_sql_generator._node_validate_sql({
        "response": response,
        "normalized_config": ai_sql_generator._normalize_manual_config(_retention_request()),
        "sql_dialect": "starrocks",
        "graph_trace": [],
    })["response"]

    assert validated.success is True
    assert not validated.issues


def test_retention_simultaneous_and_related_property_are_validated() -> None:
    request = _retention_request(
        simultaneous={
            "enabled": True,
            "event": {
                "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
                "eventName": "purchase", "field": "event_name",
            },
            "aggregation": "count",
        },
        relatedProperty={
            "enabled": True,
            "initialProperty": {
                "kind": "tracking-property", "table": "event", "field": "account_id", "eventName": "register",
            },
            "returnProperty": {
                "kind": "tracking-property", "table": "event", "field": "account_id", "eventName": "login",
            },
            "simultaneousProperty": {
                "kind": "tracking-property", "table": "event", "field": "account_id", "eventName": "purchase",
            },
            "asGroup": True,
        },
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "account_id", "dt"}},
    )
    required_sql = "SELECT cohort_date, cohort_size, " + ", ".join(
        [f"day_{day}" for day in range(8)] + ["simultaneous_value", "related_property"]
    )

    assert result.success is True
    assert ai_sql_generator._retention_sql_result_issues(required_sql, normalized) == []


def test_retention_simultaneous_reuses_event_metric_aggregation_validation() -> None:
    event = {
        "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
        "eventName": "purchase", "field": "event_name",
    }
    amount = {"table": "event", "field": "amount", "category": "number"}
    request = _retention_request(simultaneous={
        "enabled": True,
        "event": event,
        "aggregation": "sum",
        "metricField": amount,
    })
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "amount", "dt"}},
    )
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    )

    assert result.success is True
    assert "simultaneous.metricField" in prompt
    assert "sum/avg/max/min" in prompt
    assert "禁止改用其他字段或默认字段" in prompt


def test_retention_simultaneous_non_count_aggregation_requires_metric_field() -> None:
    request = _retention_request(simultaneous={
        "enabled": True,
        "event": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "purchase", "field": "event_name",
        },
        "aggregation": "max",
        "metricField": None,
    })
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt"}},
    )

    assert result.success is False
    assert "同时展示指标 缺少计算字段。" in result.issues


def test_retention_sql_validates_simultaneous_aggregation_function() -> None:
    request = _retention_request(simultaneous={
        "enabled": True,
        "event": {
            "kind": "tracking-event", "eventTable": "event", "eventNameField": "event_name",
            "eventName": "purchase", "field": "event_name",
        },
        "aggregation": "sum",
        "metricField": {"table": "event", "field": "amount", "category": "number"},
    })
    normalized = ai_sql_generator._normalize_manual_config(request)
    fixed_columns = ", ".join(["cohort_date", "cohort_size"] + [f"day_{day}" for day in range(8)])
    valid_sql = f"SELECT {fixed_columns}, SUM(amount) AS simultaneous_value FROM retention_result"
    invalid_sql = f"SELECT {fixed_columns}, AVG(amount) AS simultaneous_value FROM retention_result"

    assert ai_sql_generator._retention_sql_result_issues(valid_sql, normalized) == []
    invalid_issues = ai_sql_generator._retention_sql_result_issues(invalid_sql, normalized)
    assert any("simultaneous_value" in issue and "SUM" in issue for issue in invalid_issues)


def test_retention_event_aliases_and_filters_keep_event_identity_and_validate_scope() -> None:
    request = _retention_request(
        initialEventAlias="新增用户",
        returnEventAlias="活跃回访",
        initialEventFilters={
            "logic": "and",
            "rules": [{
                "type": "rule",
                "field": {
                    "kind": "tracking-property",
                    "table": "event",
                    "field": "channel",
                    "eventName": "register",
                },
                "operator": "eq",
                "value": "organic",
            }],
        },
        returnEventFilters={
            "logic": "or",
            "rules": [{
                "type": "rule",
                "field": {
                    "kind": "tracking-property",
                    "table": "event",
                    "field": "platform",
                    "eventName": "login",
                },
                "operator": "eq",
                "value": "ios",
            }],
        },
    )
    normalized = ai_sql_generator._normalize_manual_config(request)
    result = ai_sql_generator._deterministic_validate_manual_config(
        request,
        normalized,
        ai_sql_generator._build_formula_ir(normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt", "channel", "platform"}},
    )
    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="postgresql", type_name="PostgreSQL"),
        "",
        "",
    )

    assert result.success is True
    assert "不得替换 SQL 事件条件中的 eventName" in prompt
    assert "必须分别应用于初始事件明细和回访事件明细" in prompt

    invalid_request = _retention_request(
        returnEventFilters={
            "logic": "and",
            "rules": [{
                "type": "rule",
                "field": {
                    "kind": "tracking-property",
                    "table": "event",
                    "field": "channel",
                    "eventName": "register",
                },
                "operator": "eq",
                "value": "organic",
            }],
        },
    )
    invalid_normalized = ai_sql_generator._normalize_manual_config(invalid_request)
    invalid_result = ai_sql_generator._deterministic_validate_manual_config(
        invalid_request,
        invalid_normalized,
        ai_sql_generator._build_formula_ir(invalid_normalized),
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"user_id", "event_name", "dt", "channel"}},
    )

    assert invalid_result.success is False
    assert "回访事件筛选1不属于当前选择的事件。" in invalid_result.issues


def test_dashboard_prompt_requires_safe_cte_time_boundaries() -> None:
    """
    是什么：时间边界层必须先独立计算聚合结果，不能把聚合或窗口函数放进同层 WHERE。
    """
    prompt = ai_sql_generator._dashboard_sql_system_prompt()

    assert "bounds CTE 必须只返回一行时间边界" in prompt
    assert "聚合函数和窗口函数不得出现在同一查询层的 WHERE 条件中" in prompt
    assert "必须先在独立 CTE 中计算最大日期" in prompt
    assert "禁止生成 WHERE date_field >= <包含 MAX(date_field) 的表达式>" in prompt
    assert "仅当当前图表配置要求可变时间范围时，日期边界必须使用当前配置提供的看板日期参数占位符" in prompt
    assert "MySQL/MariaDB 最近 30 个完整自然日边界示例" not in prompt
    assert "DATE_SUB(CURDATE" not in prompt


def test_dashboard_sql_prompt_requires_configured_date_tokens() -> None:
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        context={
            "time": {
                "field": {"table": "event", "field": "dt"},
                "dateParameterType": "yyyymmdd_number",
                "dateExpression": {"version": 1, "mode": "preset", "preset": "past_30_days"},
            },
        },
    )

    prompt = ai_sql_generator._dashboard_sql_system_prompt() + "\n" + ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="mysql", type_name="MySQL"),
        "",
        "",
    )

    assert "{{dashboard_start_yyyymmdd}}" in prompt
    assert "{{dashboard_end_yyyymmdd}}" in prompt
    assert "DATE_SUB(CURDATE" not in prompt
    assert "禁止使用数据库当前日期函数" in prompt


def test_validate_sql_node_rejects_current_date_function_and_missing_date_tokens() -> None:
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        sql="SELECT * FROM event WHERE dt >= DATE_SUB(CURDATE(), INTERVAL 29 DAY)",
    )

    result = ai_sql_generator._node_validate_sql({
        "response": response,
        "normalized_config": {
            "chart": {"type": "line"},
            "time": {
                "field": {"table": "event", "field": "dt"},
                "date_parameter_type": "yyyymmdd_number",
            },
        },
        "graph_trace": [],
    })["response"]

    assert result.success is False
    assert "看板日期参数" in result.message


def test_validate_sql_node_allows_mysql_unsigned_cast() -> None:
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        sql="SELECT CAST(DATE_FORMAT(NOW(), '%Y%m%d') AS UNSIGNED) AS dt",
    )

    result = ai_sql_generator._node_validate_sql({
        "response": response,
        "sql_dialect": "mysql",
        "graph_trace": [],
    })["response"]

    assert result.success is True
    assert not result.issues


def test_metric_chart_can_use_dashboard_date_parameters() -> None:
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        chart_type="metric",
        context={
                "chart": {"type": "metric"},
                "time": {
                    "field": {"table": "event", "field": "dt"},
                    "dateParameterType": "yyyymmdd_number",
                },
        },
    )

    prompt = ai_sql_generator._dashboard_config_prompt(
        request,
        SimpleNamespace(name="测试", type="mysql", type_name="MySQL"),
        "",
        "",
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=True,
        chart_type="metric",
        sql=(
            "SELECT COUNT(*) AS 今日销售额 FROM event WHERE dt BETWEEN "
            "{{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
        ),
    )
    result = ai_sql_generator._node_validate_sql({
        "response": response,
        "normalized_config": {
            "chart": {"type": "metric"},
            "time": {
                "field": request.context["time"]["field"],
                "date_parameter_type": "yyyymmdd_number",
            },
        },
        "graph_trace": [],
    })["response"]

    assert "日期占位符" in prompt
    assert result.success is True


def test_collect_context_uses_business_sql_context_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：看板 AI 生成 SQL 前通过 SQL Engine 统一业务库上下文取 schema、字典和 Data Skill。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看登录人数",
        chart_type="line",
        context={"selectedFields": []},
    )
    datasource = SimpleNamespace(id=1, name="业务库", type="postgresql", type_name="PostgreSQL")
    business_context = SimpleNamespace(
        datasource=datasource,
        schema="【Schema】\n# Table: event\n[(event_name:text)]\n",
        sql_dialect="postgres",
        allowed_tables=["event"],
        data_skill="<Data-Skills>口径</Data-Skills>",
        tracking_config="<Tracking>事件字典</Tracking>",
        skill_model_id=99,
        warnings=[],
        business_context_hash="ctx",
    )
    calls: list[dict[str, Any]] = []

    class _Session:
        def get(self, model, obj_id):
            if getattr(model, "__name__", "") == "CoreDatasource":
                return datasource
            return None

    def _build(**kwargs):
        calls.append(kwargs)
        return business_context

    monkeypatch.setattr(ai_sql_generator, "require_current_tenant_id", lambda _user: 2001)
    monkeypatch.setattr(
        ai_sql_generator,
        "get_tracking_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            id=None,
            enabled=True,
            datasource_id=1,
            default_event_table=None,
        ),
    )
    monkeypatch.setattr(ai_sql_generator.BusinessSqlContextService, "build", staticmethod(_build))

    result = ai_sql_generator._node_collect_context({
        "session": _Session(),
        "current_user": SimpleNamespace(id=1001, tenant_id=2001),
        "request": request,
        "graph_trace": [],
    })

    assert result["business_sql_context"] is business_context
    assert result["schema"] == business_context.schema
    assert result["sql_dialect"] == "postgres"
    assert result["allowed_tables"] == ["event"]
    assert result["allowed_fields_by_table"]["event"] == {"event_name"}
    assert result["data_skill"] == business_context.data_skill
    assert result["tracking_config"] == business_context.tracking_config
    assert calls[0]["tenant_id"] == 2001
    assert calls[0]["datasource_id"] == 1
    assert calls[0]["target_scope"] == ai_sql_generator.CustomPromptTargetScopeEnum.SMART_QA
    assert calls[0]["table_list"] is None
    assert result["event_scope"]["mode"] == "general"


def test_collect_context_limits_business_schema_to_workspace_default_event_table(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = DashboardAiSqlGenerateRequest(
        datasource=6,
        intent="看登录人数",
        chart_type="line",
        context={"selectedFields": []},
    )
    datasource = SimpleNamespace(id=6, name="业务库", type="mysql", type_name="MySQL")
    business_context = SimpleNamespace(
        datasource=datasource,
        schema="【Schema】\n# Table: event\n[(event:text), (uid:text)]\n",
        sql_dialect="mysql",
        allowed_tables=["event"],
        data_skill="",
        tracking_config="",
        skill_model_id=None,
        warnings=[],
        business_context_hash="ctx-event",
    )
    calls: list[dict[str, Any]] = []
    tracking_calls: list[dict[str, Any]] = []

    class _Session:
        def get(self, model, obj_id):
            if getattr(model, "__name__", "") == "CoreDatasource":
                return datasource
            return None

    def _build(**kwargs):
        calls.append(kwargs)
        return business_context

    monkeypatch.setattr(ai_sql_generator, "require_current_tenant_id", lambda _user: 2001)
    def _tracking_config(*_args, **kwargs):
        tracking_calls.append(kwargs)
        return SimpleNamespace(
            id=1,
            enabled=True,
            datasource_id=6,
            default_event_table="event",
        )

    monkeypatch.setattr(ai_sql_generator, "get_tracking_config", _tracking_config)
    monkeypatch.setattr(ai_sql_generator.BusinessSqlContextService, "build", staticmethod(_build))

    result = ai_sql_generator._node_collect_context({
        "session": _Session(),
        "current_user": SimpleNamespace(id=1001, tenant_id=2001),
        "request": request,
        "graph_trace": [],
    })

    assert calls[0]["table_list"] == ["event"]
    assert result["allowed_tables"] == ["event"]
    assert result["event_scope"]["status"] == "active"
    assert result["event_scope"]["default_event_table"] == "event"
    assert tracking_calls == [{"include_legacy": False}]


def test_timed_graph_node_logs_sync_node_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：同步 graph 节点执行完成后，要记录节点名、状态、耗时和请求上下文。
    """
    logs: list[str] = []

    monkeypatch.setattr(ai_sql_generator.AppLogUtil, "info", lambda message: logs.append(message))

    def _handler(_state: dict[str, Any]) -> dict[str, Any]:
        return {"result": "ok"}

    result = asyncio.run(ai_sql_generator._timed_graph_node(
        "collect_context",
        _handler,
        {
            "request": DashboardAiSqlGenerateRequest(datasource=3),
            "current_user": SimpleNamespace(id=1001, tenant_id=2001),
        },
    ))

    assert result == {"result": "ok"}
    assert len(logs) == 1
    assert "Dashboard manual chart graph node finished" in logs[0]
    assert "node=collect_context" in logs[0]
    assert "status=ok" in logs[0]
    assert "elapsed_ms=" in logs[0]
    assert "datasource_id=3" in logs[0]
    assert "tenant_id=2001" in logs[0]
    assert "user_id=1001" in logs[0]


def test_timed_graph_node_logs_async_node_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：异步 graph 节点异常时，也要记录失败状态和耗时，然后继续抛出原异常。
    """
    warnings: list[str] = []

    monkeypatch.setattr(ai_sql_generator.AppLogUtil, "warning", lambda message: warnings.append(message))

    async def _handler(_state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("LLM unavailable")

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        asyncio.run(ai_sql_generator._timed_graph_node(
            "deterministic_validate",
            _handler,
            {
                "request": DashboardAiSqlGenerateRequest(datasource=3),
                "tenant_id": 2001,
                "current_user": SimpleNamespace(id=1001, tenant_id=2001),
            },
        ))

    assert len(warnings) == 1
    assert "Dashboard manual chart graph node failed" in warnings[0]
    assert "node=deterministic_validate" in warnings[0]
    assert "status=error" in warnings[0]
    assert "elapsed_ms=" in warnings[0]
    assert "datasource_id=3" in warnings[0]
    assert "tenant_id=2001" in warnings[0]
    assert "user_id=1001" in warnings[0]
    assert "error=LLM unavailable" in warnings[0]


def test_global_json_filter_requires_complete_mapping() -> None:
    normalized = {
        "time": {},
        "metrics": [],
        "formula_metrics": [],
        "groups": [],
        "filters": {
            "logic": "and",
            "rules": [
                {
                    "field": {
                        "table": "event",
                        "field": "userinfo.country",
                        "sourceField": "userinfo",
                        "jsonPath": "$.country",
                        "isJsonSubfield": True,
                    },
                    "operator": "eq",
                    "value": "US",
                }
            ],
        },
    }

    issues = ai_sql_generator._configured_field_permission_issues(
        normalized,
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"userinfo"}},
    )

    assert any("全局筛选1 的 JSON 字段映射不完整" in item for item in issues)
    assert any("expression" in item for item in issues)


def test_dashboard_prompt_keeps_user_properties_on_event_userinfo() -> None:
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            title="按国家统计活跃",
            chart_type="table",
            context={
                "time": {"field": {"table": "event", "field": "dt"}, "grain": "day", "range": "30d"},
                "metrics": [
                    {
                        "field": {
                            "kind": "tracking-event",
                            "table": "event",
                            "field": "event",
                            "eventName": "UserActive",
                        },
                        "aggregation": "count",
                    }
                ],
                "groups": [],
                "filters": {
                    "logic": "and",
                    "rules": [
                        {
                            "field": {
                                "table": "event",
                                "field": "userinfo.country",
                                "sourceField": "userinfo",
                                "jsonPath": "$.country",
                                "expression": "JSON_UNQUOTE(JSON_EXTRACT(`event`.`userinfo`, '$.country'))",
                            },
                            "operator": "eq",
                            "value": "US",
                        }
                    ],
                },
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
    )

    assert "全局筛选只允许使用 context.filters 中提供的 event.userinfo JSON 子字段" in prompt
    assert "不得把用户属性改为 user 表" in prompt
