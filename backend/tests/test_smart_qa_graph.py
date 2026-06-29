from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from apps.chat.models.chat_model import ChatFinishStep, OperationEnum
from apps.chat.task import llm
from apps.chat.task import smart_qa_graph as graph
from apps.datasource.crud.permission_errors import PERMISSION_DENIED_ERROR_TYPE
from common.error import SingleMessageError


@contextmanager
def _fake_session_scope():
    yield object()


def _sql_answer(sql: str = "select 1 as value", tables: list[str] | None = None) -> str:
    payload = {
        "success": True,
        "sql": sql,
        "tables": tables or ["orders"],
        "chart_type": "table",
    }
    return json.dumps(payload)


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


@pytest.fixture(autouse=True)
def _patch_graph_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(graph, "_session_scope", _fake_session_scope)
    monkeypatch.setattr(graph, "check_connection", lambda ds, trans=None: True)
    monkeypatch.setattr(
        graph,
        "start_log",
        lambda **kwargs: SimpleNamespace(id=1, error=False),
    )
    monkeypatch.setattr(graph, "end_log", lambda **kwargs: kwargs["log"])
    monkeypatch.setattr(graph, "trigger_log_error", lambda session, log: log)


class FakeSmartQAService:
    def __init__(
        self,
        *,
        current_assistant: Any = None,
        sql_answer: str | None = None,
    ) -> None:
        self.ds = SimpleNamespace(id=1, type="PostgreSQL", type_name="PostgreSQL")
        self.record = SimpleNamespace(
            id=9001,
            chat_id=9000,
            question="test question",
            regenerate_record_id=None,
        )
        self.chat_question = SimpleNamespace(question="test question")
        self.current_user = SimpleNamespace(id=1)
        self.current_assistant = current_assistant
        self.current_logs: dict[OperationEnum, Any] = {}
        self.table_name_list = ["orders"]
        self.change_title = False
        self.out_ds_instance = None
        self.sql_answer = sql_answer or _sql_answer()
        self.saved_sql: list[str] = []
        self.saved_data: list[dict[str, Any]] = []
        self.saved_errors: list[str] = []
        self.executed: list[dict[str, Any]] = []
        self.chart_generated = False
        self.finished = False
        self.chart_chunks = [
            {"content": '{"type":"table","title":"Result","columns":[{"value":"value"}]}', "reasoning_content": ""},
        ]

    def get_record(self):
        return self.record

    def trans(self, key: str):
        return f"{key}: "

    def load_data_skills(self, *args, **kwargs):
        pass

    def filter_custom_prompts(self, *args, **kwargs):
        pass

    def save_agent_context_snapshot(self, *args, **kwargs):
        pass

    def load_tracking_config(self, *args, **kwargs):
        pass

    def init_messages(self, *args, **kwargs):
        pass

    def validate_history_ds(self, *args, **kwargs):
        pass

    def generate_sql_text_streaming_reasoning(self, *args, **kwargs):
        if kwargs.get("in_chat"):
            yield graph._sse({
                "content": "",
                "reasoning_content": "thinking",
                "type": "sql-result",
            })
        return self.sql_answer

    def check_sql(self, *args, **kwargs):
        payload = json.loads(self.sql_answer)
        return payload["sql"], payload.get("tables")

    def get_chart_type_from_sql_answer(self, *args, **kwargs):
        return "table"

    def save_checked_sql(self, *, session, sql):
        self.saved_sql.append(sql)
        return sql

    def generate_assistant_dynamic_sql(self, *args, **kwargs):
        return None

    def check_save_sql(self, *args, **kwargs):
        raise AssertionError("dynamic SQL should not be saved in this scenario")

    def save_permission_denied_data(self, *args, **kwargs):
        result = {
            "status": "failed",
            "error_type": PERMISSION_DENIED_ERROR_TYPE,
            "fields": [],
            "data": [],
        }
        self.saved_data.append(result)
        return result

    def execute_sql(self, **kwargs):
        self.executed.append(kwargs)
        return {"fields": ["value"], "data": [{"value": 1}]}

    def save_sql_data(self, *, session, data_obj):
        self.saved_data.append(data_obj)

    def generate_chart(self, *args, **kwargs):
        self.chart_generated = True
        yield from self.chart_chunks

    def check_save_chart(self, *, session, res, result):
        assert session is not None
        assert result["fields"] == ["value"]
        return json.loads(res)

    def save_error(self, *, session, message):
        self.saved_errors.append(message)

    def finish(self, *args, **kwargs):
        self.finished = True


def test_generate_sql_finish_step_stops_before_execute(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_SQL,
        ),
    )
    events = _events(chunks)

    assert service.saved_sql == ["select 1 as value"]
    assert service.executed == []
    assert service.finished is True
    assert [event["type"] for event in events if event["type"] in {"sql", "finish"}] == ["sql", "finish"]
    assert not any(event["type"] == "sql-data" for event in events)
    assert not any(event["type"] == "chart" for event in events)


def test_graph_records_run_id_and_node_trace(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )

    trace = service._smart_qa_graph_trace
    assert service._smart_qa_graph_run_id.startswith("smartqa-9001-")
    assert service._smart_qa_graph_failed_node is None
    assert service._smart_qa_graph_error_type is None
    assert [entry["node"] for entry in trace] == [
        "prepare_context",
        "emit_record_metadata",
        "ensure_datasource",
        "generate_sql",
        "prepare_sql",
        "execute_sql",
    ]
    assert all(entry["status"] == "success" for entry in trace)
    assert all(isinstance(entry["duration_ms"], float) for entry in trace)
    assert trace[-1]["stop"] is True


def test_query_data_finish_step_stops_before_chart(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )
    events = _events(chunks)

    assert service.saved_sql == ["select 1 as value"]
    assert len(service.executed) == 1
    assert service.saved_data == [{"fields": ["value"], "data": [{"value": 1}]}]
    assert service.finished is True
    assert [event["type"] for event in events if event["type"] in {"sql-data", "finish"}] == [
        "sql-data",
        "finish",
    ]
    assert not any(event["type"] == "chart-result" for event in events)
    assert not any(event["type"] == "chart" for event in events)


def test_permission_denied_during_sql_validation_stops_graph(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select secret from orders"))

    def _deny_query(**kwargs):
        assert kwargs["sql"] == "select secret from orders"
        raise Exception("permission denied: allowed tables")

    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", _deny_query)

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    event_types = [event["type"] for event in events]
    sql_data_event = next(event for event in events if event["type"] == "sql-data")

    assert service.saved_sql == ["select secret from orders"]
    assert service.saved_data and service.saved_data[-1]["error_type"] == PERMISSION_DENIED_ERROR_TYPE
    assert service.executed == []
    assert service.finished is True
    assert sql_data_event["status"] == "failed"
    assert sql_data_event["error_type"] == PERMISSION_DENIED_ERROR_TYPE
    assert event_types[-1] == "finish"
    assert "chart" not in event_types


def test_single_message_error_is_saved_and_streamed(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer='{"success": false, "message": "forced"}')

    def _raise_single_message(*, session, res, operate):
        assert session is not None
        assert res == '{"success": false, "message": "forced"}'
        assert operate == OperationEnum.GENERATE_SQL
        raise SingleMessageError("forced invalid sql")

    service.check_sql = _raise_single_message
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    error_event = next(event for event in events if event["type"] == "error")

    assert service.saved_sql == []
    assert service.executed == []
    assert service.saved_errors == ["forced invalid sql"]
    assert service.finished is True
    assert service._smart_qa_graph_failed_node == "prepare_sql"
    assert service._smart_qa_graph_error_type == "single_message"
    assert service._smart_qa_graph_trace[-1]["node"] == "prepare_sql"
    assert service._smart_qa_graph_trace[-1]["status"] == "error"
    assert error_event["content"] == "forced invalid sql"
    assert not any(event["type"] == "finish" for event in events)


def test_dynamic_assistant_datasource_executes_expanded_sql():
    sql_answer = _sql_answer("select * from orders", ["orders"])
    service = FakeSmartQAService(
        current_assistant=SimpleNamespace(type=1),
        sql_answer=sql_answer,
    )

    def _dynamic_sql(session, sql, tables):
        assert session is not None
        assert sql == "select * from orders"
        assert tables == ["orders"]
        return {
            "orders": "select id, amount from public.orders",
            "app_temp_sql_text": _sql_answer("select * from app_dynamic_temp_table_orders", ["orders"]),
        }

    def _check_save_sql(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_DYNAMIC_SQL
        assert json.loads(res)["sql"] == "select * from app_dynamic_temp_table_orders"
        return "select * from app_dynamic_temp_table_orders"

    service.generate_assistant_dynamic_sql = _dynamic_sql
    service.check_save_sql = _check_save_sql

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )
    events = _events(chunks)

    assert len(service.executed) == 1
    assert service.executed[0]["sql"] == "select id, amount from public.orders"
    assert service.executed[0]["scope_sql"] == "select * from app_dynamic_temp_table_orders"
    assert service.executed[0]["scope_allowed_tables"] == ["app_dynamic_temp_table_orders"]
    assert service.finished is True
    assert [event["type"] for event in events if event["type"] in {"sql-data", "finish"}] == [
        "sql-data",
        "finish",
    ]
    assert not any(event["type"] == "chart" for event in events)


def test_non_chat_stream_query_data_returns_markdown(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=False,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )

    assert service.finished is True
    assert service.chart_generated is False
    assert any("```sql" in chunk and "select 1 as value" in chunk for chunk in chunks)
    assert any("| value" in chunk and "\u200b1" in chunk for chunk in chunks)


def test_non_stream_full_chart_returns_json_result(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )
    monkeypatch.setattr(
        graph,
        "get_chat_chart_data",
        lambda session, record_id: {"fields": ["value"], "data": [{"value": 1}]},
    )
    monkeypatch.setattr(
        graph,
        "get_table_schema",
        lambda **kwargs: ("table orders(value int)", ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=False,
            stream=False,
            finish_step=ChatFinishStep.GENERATE_CHART,
            return_img=False,
        ),
    )

    assert service.finished is True
    assert service.chart_generated is True
    assert chunks == [
        {
            "success": True,
            "record_id": 9001,
            "sql": "select 1 as value",
            "data": {"fields": ["value"], "data": [{"value": 1}]},
            "chart": {"type": "table", "title": "Result", "columns": [{"value": "value"}]},
        }
    ]


def test_chart_generation_tolerates_reasoning_only_chunk(monkeypatch: pytest.MonkeyPatch):
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    service.chart_chunks = [
        {"content": None, "reasoning_content": "thinking chart"},
        {"content": '{"type":"table","title":"Result","columns":[{"value":"value"}]}', "reasoning_content": ""},
    ]
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )
    monkeypatch.setattr(
        graph,
        "get_table_schema",
        lambda **kwargs: ("table orders(value int)", ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    chart_result_events = [event for event in events if event["type"] == "chart-result"]

    assert service.chart_generated is True
    assert chart_result_events[0]["content"] == ""
    assert chart_result_events[0]["reasoning_content"] == "thinking chart"
    assert any(event["type"] == "chart" for event in events)
    assert events[-1]["type"] == "finish"


def test_llm_service_routes_smart_qa_to_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=8001)
    calls: list[dict[str, Any]] = []

    def _fake_graph(service_arg, *, in_chat: bool, stream: bool, finish_step: ChatFinishStep, return_img: bool):
        calls.append(
            {
                "service": service_arg,
                "in_chat": in_chat,
                "stream": stream,
                "finish_step": finish_step,
                "return_img": return_img,
            }
        )
        yield "graph-result"

    monkeypatch.setattr(graph, "run_smart_qa_graph", _fake_graph)

    assert list(
        service.run_task(
            in_chat=False,
            stream=False,
            finish_step=ChatFinishStep.QUERY_DATA,
            return_img=False,
        )
    ) == ["graph-result"]
    assert calls == [
        {
            "service": service,
            "in_chat": False,
            "stream": False,
            "finish_step": ChatFinishStep.QUERY_DATA,
            "return_img": False,
        },
    ]
