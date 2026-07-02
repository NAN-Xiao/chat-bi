import json
from types import SimpleNamespace

from apps.chat.task import saas_skill


def _skill_text(definition: dict) -> str:
    return "<Data-Skills>\n<!-- saas-skill:" + json.dumps(definition, ensure_ascii=False) + " -->\n</Data-Skills>"


def test_parse_and_match_executable_saas_skill_extracts_recent_days():
    definition = {
        "id": "revenue_drop_with_voice",
        "name": "收入下滑舆情分析",
        "intent": ["收入下滑分析", "用户舆情分析"],
        "parameters": {"days": {"type": "integer", "default": 28}},
        "sources": [
            {"name": "revenue", "type": "sql", "sql_template": "select 1"},
            {"name": "voice", "type": "external_mcp", "tool": "sentiment"},
        ],
    }

    match = saas_skill.find_matching_executable_saas_skill(
        _skill_text(definition),
        "结合用户舆情分析最近7天的收入下滑问题",
    )

    assert match is not None
    assert match.definition["id"] == "revenue_drop_with_voice"
    assert match.params["days"] == 7


def test_saas_skill_params_support_bounds_value_map_and_lists():
    definition = {
        "id": "chatmon_alert_count",
        "name": "ChatMon 告警数量",
        "intent": ["告警数量", "舆情趋势"],
        "parameters": {
            "days": {"type": "integer", "default": 7, "max": 7},
            "source": {
                "type": "string",
                "patterns": ["(游戏内|社区|game_chat|external_community)"],
                "value_map": {"游戏内": "game_chat", "社区": "external_community"},
            },
            "priority_in": {
                "type": "array",
                "patterns": ["((?:P[0-2][,，、/\\s]*)+)"],
            },
        },
        "sources": [
            {
                "name": "alerts",
                "type": "external_mcp",
                "tool": "alerts.count",
                "arguments_template": {
                    "start_date": "{{start_date}}",
                    "end_date": "{{end_date}}",
                    "source": "{{source}}",
                    "priority_in": "{{priority_in}}",
                },
            },
        ],
    }

    match = saas_skill.find_matching_executable_saas_skill(
        _skill_text(definition),
        "查一下最近30天游戏内 P0/P1 舆情趋势",
    )

    assert match is not None
    assert match.params["days"] == 7
    assert match.params["source"] == "game_chat"
    assert match.params["priority_in"] == ["P0", "P1"]

    rendered = saas_skill.render_template_value(
        definition["sources"][0]["arguments_template"],
        match.params,
    )
    assert rendered["source"] == "game_chat"
    assert rendered["priority_in"] == ["P0", "P1"]


def test_merge_saas_skill_sources_joins_by_declared_fields():
    revenue = saas_skill.SaasSkillSourceResult(
        name="revenue",
        source_type="sql",
        fields=["date", "revenue"],
        data=[
            {"date": "2026-06-01", "revenue": 100},
            {"date": "2026-06-02", "revenue": 80},
        ],
        spec={},
    )
    voice = saas_skill.SaasSkillSourceResult(
        name="voice",
        source_type="external_mcp",
        fields=["date", "negative_count"],
        data=[
            {"date": "2026-06-02", "negative_count": 18},
            {"date": "2026-06-03", "negative_count": 4},
        ],
        spec={},
    )

    merged = saas_skill.merge_saas_skill_sources(
        [revenue, voice],
        {"join_fields": ["date"]},
    )

    assert merged["fields"] == ["date", "revenue", "negative_count"]
    assert merged["data"] == [
        {"date": "2026-06-01", "revenue": 100},
        {"date": "2026-06-02", "revenue": 80, "negative_count": 18},
        {"date": "2026-06-03", "negative_count": 4},
    ]


def test_execute_saas_skill_runs_sql_and_bound_mcp_then_merges(monkeypatch):
    definition = {
        "id": "revenue_drop_with_voice",
        "name": "收入下滑舆情分析",
        "intent": ["收入下滑分析", "用户舆情分析"],
        "parameters": {"days": {"type": "integer", "default": 28}},
        "sources": [
            {
                "name": "revenue",
                "type": "sql",
                "sql_template": "select date, revenue from revenue_daily where date >= current_date - interval '{{days}} days'",
            },
            {
                "name": "voice",
                "type": "external_mcp",
                "tool": "sentiment_summary",
                "arguments_template": {"days": "{{days}}"},
                "result_path": "items",
            },
        ],
        "merge": {"join_fields": ["date"]},
    }
    match = saas_skill.find_matching_executable_saas_skill(
        _skill_text(definition),
        "结合用户舆情分析最近3天的收入下滑问题",
    )
    assert match is not None

    executed_sql = {}

    class FakeService:
        current_user = SimpleNamespace(id=1, tenant_id=10)
        table_name_list = ["revenue_daily"]

        def execute_sql(self, session, sql, scope_sql=None, scope_allowed_tables=None):
            executed_sql["sql"] = sql
            assert "3 days" in sql
            return {
                "fields": ["date", "revenue"],
                "data": [{"date": "2026-06-02", "revenue": 80}],
            }

    def fake_preview(session, current_user, **kwargs):
        assert kwargs["external_mcp_server_id"] == 99
        assert kwargs["tool"] == "sentiment_summary"
        assert kwargs["arguments"] == {"days": 3}
        return {
            "status": "success",
            "fields": ["date", "negative_count"],
            "data": [{"date": "2026-06-02", "negative_count": 18}],
            "raw": {"items": []},
            "mcp": {"tool": "sentiment_summary"},
        }

    monkeypatch.setattr(saas_skill, "require_current_tenant_id", lambda user: 10)
    monkeypatch.setattr(saas_skill, "get_bound_external_mcp_id_for_tenant", lambda session, tenant_id: 99)
    monkeypatch.setattr(saas_skill, "preview_external_mcp_tool", fake_preview)

    result = saas_skill.execute_saas_skill(object(), FakeService(), match)

    assert executed_sql["sql"].endswith("interval '3 days'")
    assert result.merged_result["data"] == [
        {"date": "2026-06-02", "revenue": 80, "negative_count": 18}
    ]
    assert result.chart["type"] == "table"
