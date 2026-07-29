from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.chat.service.chat_date_filter import (
    ChatDateFilterConfigurationError,
    normalize_chat_date_filter,
    render_chat_date_filter_sql,
)
from apps.chat.models.chat_model import ChatFinishStep
from apps.chat.models.chat_model import OperationEnum
from apps.chat.task.llm import LLMService
from apps.chat.task import smart_qa_graph
from apps.chat.curd import chat as chat_crud


DATE_TEMPLATE_SQL = (
    "SELECT * FROM event "
    "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
)
DATE_LITERAL_SQL = (
    "SELECT * FROM event "
    "WHERE `e`.`dt` BETWEEN 20260701 AND 20260728"
)
DATE_LITERAL_TEMPLATE_SQL = (
    "SELECT * FROM event "
    "WHERE `e`.`dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
)
DATE_FILTER = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
}


def test_normalize_accepts_complete_past_seven_days_yyyymmdd_template():
    pivot = normalize_chat_date_filter(DATE_FILTER, DATE_TEMPLATE_SQL, "line")

    assert pivot == {"enabled": False, **DATE_FILTER}


def test_normalize_rejects_token_without_configuration():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter(None, DATE_TEMPLATE_SQL, "line")


def test_normalize_rejects_fixed_metric_date_configuration():
    with pytest.raises(ChatDateFilterConfigurationError, match="metric_chart"):
        normalize_chat_date_filter(DATE_FILTER, DATE_TEMPLATE_SQL, "metric")


def test_normalize_rejects_current_date_function_for_date_filter():
    with pytest.raises(ChatDateFilterConfigurationError, match="database_current_date"):
        normalize_chat_date_filter(
            DATE_FILTER,
            "SELECT * FROM event WHERE dt >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
            "line",
        )


def test_render_uses_past_seven_days_before_execution():
    sql = render_chat_date_filter_sql(
        DATE_TEMPLATE_SQL,
        "mysql",
        {"enabled": False, **DATE_FILTER},
        today=date(2026, 7, 29),
    )

    assert "20260722" in sql
    assert "20260728" in sql
    assert "{{dashboard_start_yyyymmdd}}" not in sql
    assert "{{dashboard_end_yyyymmdd}}" not in sql


def test_llm_service_renders_date_template_only_for_execution():
    service = object.__new__(LLMService)
    service.ds = SimpleNamespace(type="mysql")
    service.chat_date_pivot = {"enabled": False, **DATE_FILTER}

    execution_sql = service.render_chat_sql_for_execution(DATE_TEMPLATE_SQL)

    assert "{{dashboard_start_yyyymmdd}}" not in execution_sql
    assert "{{dashboard_end_yyyymmdd}}" not in execution_sql
    assert "BETWEEN" in execution_sql


def test_check_sql_keeps_date_template_and_date_filter_pivot():
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="趋势", data_skill="")
    service.chat_date_pivot = None
    response = {
        "success": True,
        "sql": DATE_TEMPLATE_SQL,
        "tables": ["event"],
        "chart-type": "line",
        "date_filter": DATE_FILTER,
    }

    sql, tables = service.check_sql(
        session=object(),
        res=__import__("json").dumps(response),
        operate=OperationEnum.GENERATE_SQL,
    )

    assert sql == DATE_TEMPLATE_SQL
    assert tables == ["event"]
    assert service.chat_date_pivot == {"enabled": False, **DATE_FILTER}


def test_check_sql_rewrites_date_literals_to_template_for_declared_date_filter():
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="DAU趋势", data_skill="")
    service.chat_date_pivot = None
    response = {
        "success": True,
        "sql": DATE_LITERAL_SQL,
        "tables": ["event"],
        "chart-type": "line",
        "date_filter": DATE_FILTER,
    }

    sql, tables = service.check_sql(
        session=object(),
        res=__import__("json").dumps(response),
        operate=OperationEnum.GENERATE_SQL,
    )

    assert sql == DATE_LITERAL_TEMPLATE_SQL
    assert tables == ["event"]
    assert service.chat_date_pivot == {"enabled": False, **DATE_FILTER}


def test_prepare_sql_saves_template_but_validates_rendered_sql(monkeypatch):
    class FakeSessionScope:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    saved_sql = []
    validated_sql = []
    service = SimpleNamespace(
        current_assistant=None,
        current_user=object(),
        ds=SimpleNamespace(type="mysql"),
        table_name_list=["event"],
        change_title=False,
        chat_date_pivot={"enabled": False, **DATE_FILTER},
        check_sql=lambda **_kwargs: (DATE_TEMPLATE_SQL, ["event"]),
        get_chart_type_from_sql_answer=lambda _answer: "line",
        save_checked_sql=lambda **kwargs: saved_sql.append(kwargs["sql"]) or kwargs["sql"],
        render_chat_sql_for_execution=lambda sql: render_chat_date_filter_sql(
            sql,
            "mysql",
            {"enabled": False, **DATE_FILTER},
            today=date(2026, 7, 29),
        ),
    )

    monkeypatch.setattr(smart_qa_graph, "_session_scope", lambda: FakeSessionScope())
    monkeypatch.setattr(
        smart_qa_graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (validated_sql.append(kwargs["sql"]) or kwargs["sql"], {"event"}),
    )
    monkeypatch.setattr(
        smart_qa_graph,
        "_rewrite_sql_for_missing_events",
        lambda _service, sql: smart_qa_graph._MissingEventSqlRewrite(sql=sql, executable=True),
    )

    state = smart_qa_graph._prepare_sql(
        {
            "service": service,
            "in_chat": False,
            "stream": False,
            "finish_step": ChatFinishStep.QUERY_DATA,
            "json_result": {},
            "full_sql_text": '{"success":true}',
        }
    )

    assert saved_sql == [DATE_TEMPLATE_SQL]
    assert "{{dashboard_start_yyyymmdd}}" not in validated_sql[0]
    assert "{{dashboard_start_yyyymmdd}}" not in state["real_execute_sql"]


def test_live_chart_refresh_renders_persisted_date_pivot_before_execution(monkeypatch):
    class FakeResult:
        def first(self):
            return SimpleNamespace(
                datasource=1,
                sql=DATE_TEMPLATE_SQL,
                chart={"type": "line", "pivot": {"enabled": False, **DATE_FILTER}},
            )

    class FakeSession:
        def execute(self, _statement):
            return FakeResult()

        def get(self, _model, _identifier):
            return SimpleNamespace(type="mysql")

    executed_sql = []
    monkeypatch.setattr(chat_crud, "_current_tenant_id", lambda _user: 1)
    monkeypatch.setattr(chat_crud, "_saved_record_missing_event_projection", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_crud,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, _datasource, sql: executed_sql.append(sql) or {"data": []},
    )
    monkeypatch.setattr(
        chat_crud,
        "render_chat_date_filter_sql",
        lambda sql, _datasource_type, pivot: render_chat_date_filter_sql(
            sql,
            "mysql",
            pivot,
            today=date(2026, 7, 29),
        ),
        raising=False,
    )
    result = chat_crud.get_chart_data_with_user_live(FakeSession(), SimpleNamespace(id=2), 3)

    assert result == {"data": []}
    assert "{{dashboard_start_yyyymmdd}}" not in executed_sql[0]
    assert "20260722" in executed_sql[0]


def test_chat_sql_template_requires_date_filter_contract():
    source = (Path(__file__).resolve().parents[1] / "templates" / "template.yaml").read_text(
        encoding="utf-8"
    )

    assert '"date_filter"' in source
    assert '"past_7_days"' in source
