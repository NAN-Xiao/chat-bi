"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
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
from common.error import DataUnavailableError, SingleMessageError


@contextmanager
def _fake_session_scope():
    """
    是什么：_fake_session_scope 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    yield object()


def _sql_answer(sql: str = "select 1 as value", tables: list[str] | None = None) -> str:
    """
    是什么：_sql_answer 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    payload = {
        "success": True,
        "sql": sql,
        "tables": tables or ["orders"],
        "chart_type": "table",
    }
    return json.dumps(payload)


def _sql_answer_with_message(sql: str, message: str, tables: list[str] | None = None) -> str:
    payload = {
        "success": True,
        "sql": sql,
        "tables": tables or ["orders"],
        "chart_type": "table",
        "message": message,
    }
    return json.dumps(payload)


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    """
    是什么：_events 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


@pytest.fixture(autouse=True)
def _patch_graph_runtime(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：_patch_graph_runtime 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    monkeypatch.setattr(graph, "_session_scope", _fake_session_scope)
    monkeypatch.setattr(graph, "check_connection", lambda ds, trans=None: True)
    monkeypatch.setattr(
        graph,
        "start_log",
        lambda **kwargs: SimpleNamespace(id=1, error=False),
    )
    monkeypatch.setattr(graph, "end_log", lambda **kwargs: kwargs["log"])

    def _trigger_log_error(session, log, full_message=None):
        log.error = True
        if full_message is not None:
            log.messages = full_message
        return log

    monkeypatch.setattr(graph, "trigger_log_error", _trigger_log_error)


class FakeSmartQAService:
    """
    类说明：FakeSmartQAService 把测试的一组操作放在一起，对外提供更容易调用的业务能力。
    """
    def __init__(
        self,
        *,
        current_assistant: Any = None,
        sql_answer: str | None = None,
    ) -> None:
        """
        是什么：FakeSmartQAService.__init__ 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.ds = SimpleNamespace(id=1, type="PostgreSQL", type_name="PostgreSQL")
        self.record = SimpleNamespace(
            id=9001,
            chat_id=9000,
            question="test question",
            regenerate_record_id=None,
        )
        self.chat_question = SimpleNamespace(
            question="test question",
            data_skill="",
            ai_modal_id=None,
            ai_modal_name=None,
        )
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
        self.saved_analysis: list[str] = []
        self.executed: list[dict[str, Any]] = []
        self.chart_generated = False
        self.finished = False
        self.chart_chunks = [
            {"content": '{"type":"table","title":"Result","columns":[{"value":"value"}]}', "reasoning_content": ""},
        ]

    def get_record(self):
        """
        是什么：FakeSmartQAService.get_record 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        return self.record

    def trans(self, key: str):
        """
        是什么：FakeSmartQAService.trans 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return f"{key}: "

    def load_data_skills(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.load_data_skills 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        pass

    def filter_custom_prompts(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.filter_custom_prompts 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        pass

    def save_agent_context_snapshot(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.save_agent_context_snapshot 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        pass

    def load_tracking_config(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.load_tracking_config 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        pass

    def init_messages(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.init_messages 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        pass

    def validate_history_ds(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.validate_history_ds 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        pass

    def generate_sql_text_streaming_reasoning(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.generate_sql_text_streaming_reasoning 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：根据已有信息生成测试的结果，比如答案、SQL、图表或建议。
        """
        if kwargs.get("in_chat"):
            yield graph._sse({
                "content": "",
                "reasoning_content": "thinking",
                "type": "sql-result",
            })
        return self.sql_answer

    def regenerate_sql_after_validation_error_streaming_reasoning(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.regenerate_sql_after_validation_error_streaming_reasoning 是一段测试代码，用来模拟 Data Skill 校验后的 SQL 重试。
        """
        if False:
            yield None
        return self.sql_answer

    def check_sql(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.check_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        payload = json.loads(self.sql_answer)
        return payload["sql"], payload.get("tables")

    def get_chart_type_from_sql_answer(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.get_chart_type_from_sql_answer 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        return "table"

    def save_checked_sql(self, *, session, sql):
        """
        是什么：FakeSmartQAService.save_checked_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_sql.append(sql)
        return sql

    def generate_assistant_dynamic_sql(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.generate_assistant_dynamic_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：根据已有信息生成测试的结果，比如答案、SQL、图表或建议。
        """
        return None

    def check_save_sql(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.check_save_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        raise AssertionError("dynamic SQL should not be saved in this scenario")

    def save_permission_denied_data(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.save_permission_denied_data 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        result = {
            "status": "failed",
            "error_type": PERMISSION_DENIED_ERROR_TYPE,
            "fields": [],
            "data": [],
        }
        self.saved_data.append(result)
        return result

    def execute_sql(self, **kwargs):
        """
        是什么：FakeSmartQAService.execute_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试的主要流程跑起来，一步步调用需要的处理。
        """
        self.executed.append(kwargs)
        return {"fields": ["value"], "data": [{"value": 1}]}

    def save_sql_data(self, *, session, data_obj):
        """
        是什么：FakeSmartQAService.save_sql_data 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_data.append(data_obj)

    def generate_chart(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.generate_chart 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：根据已有信息生成测试的结果，比如答案、SQL、图表或建议。
        """
        self.chart_generated = True
        yield from self.chart_chunks

    def check_save_chart(self, *, session, res, result):
        """
        是什么：FakeSmartQAService.check_save_chart 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        assert session is not None
        assert result["fields"] == ["value"]
        return json.loads(res)

    def save_error(self, *, session, message):
        """
        是什么：FakeSmartQAService.save_error 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_errors.append(message)

    def save_analysis(self, *, session, answer):
        """
        是什么：FakeSmartQAService.save_analysis 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_analysis.append(answer)
        return self.record

    def finish(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.finish 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试这次处理做收尾，记录结果并关掉不再需要的资源。
        """
        self.finished = True


def test_generate_sql_finish_step_stops_before_execute(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_generate_sql_finish_step_stops_before_execute 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
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
    """
    是什么：test_graph_records_run_id_and_node_trace 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
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
        "execute_saas_skill",
        "generate_sql",
        "prepare_sql",
        "execute_sql",
    ]
    assert all(entry["status"] == "success" for entry in trace)
    assert all(isinstance(entry["duration_ms"], float) for entry in trace)
    assert trace[-1]["stop"] is True


def test_query_data_finish_step_stops_before_chart(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_query_data_finish_step_stops_before_chart 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
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


def test_sql_answer_message_is_streamed_as_plain_business_feedback(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_sql_answer_message_is_streamed_as_plain_business_feedback 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：确认部分数据缺失提示不会变成错误卡片。
    """
    message = "当前数据源没有 pdau 埋点，已生成 DAU 部分。"
    service = FakeSmartQAService(
        sql_answer=_sql_answer_with_message("select 1 as value", message),
    )
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

    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    saved_feedback = json.loads(service.saved_analysis[-1])
    assert feedback_event["content"] == message
    assert saved_feedback["content"] == message
    assert not any(event["type"] == "error" for event in events)
    assert service.saved_errors == []
    assert service.finished is True


def test_data_unavailable_execution_is_logged_but_not_streamed_as_error(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_data_unavailable_execution_is_logged_but_not_streamed_as_error 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：确认缺表/缺字段执行失败会留日志，但用户侧看到普通业务提示。
    """
    message = "当前数据源缺少本次问题所需的表、字段或埋点数据：public.fact_events。"
    service = FakeSmartQAService(sql_answer=_sql_answer('select * from "public"."fact_events"'))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    def _raise_data_unavailable(**kwargs):
        service.executed.append(kwargs)
        raise DataUnavailableError(message)

    service.execute_sql = _raise_data_unavailable

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    execute_log = service.current_logs[OperationEnum.EXECUTE_SQL]

    assert feedback_event["content"] == message
    assert execute_log.error is True
    assert execute_log.messages["error_type"] == "data_unavailable"
    assert execute_log.messages["message"] == message
    assert not any(event["type"] == "error" for event in events)
    assert not any(event["type"] == "chart" for event in events)
    assert service.saved_errors == []
    assert service.finished is True
    assert events[-1]["type"] == "finish"


def test_data_skill_schema_unavailable_is_streamed_as_business_feedback(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：Data Skill 校验发现 schema 缺表时，应给用户普通业务提示，失败详情留在生成 SQL 日志。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select * from fact_events"))
    schema_error = "Data Skill 要求使用 fact_sessions 表计算 DAU，但当前数据库 Schema 中不存在该表。"
    service.current_logs[OperationEnum.GENERATE_SQL] = SimpleNamespace(id=1, error=False)

    def _raise_schema_unavailable(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        service.current_logs[operate].error = True
        raise llm.DataSkillSqlValidationError(schema_error)

    service.check_sql = _raise_schema_unavailable
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
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    sql_log = service.current_logs[OperationEnum.GENERATE_SQL]

    assert "当前数据源缺少本次问题所需的表、字段或埋点数据" in feedback_event["content"]
    assert sql_log.error is True
    assert service.saved_sql == []
    assert service.executed == []
    assert service.saved_errors == []
    assert service.finished is True
    assert events[-1]["type"] == "finish"
    assert not any(event["type"] == "error" for event in events)


def test_permission_denied_during_sql_validation_stops_graph(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_permission_denied_during_sql_validation_stops_graph 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select secret from orders"))

    def _deny_query(**kwargs):
        """
        是什么：_deny_query 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
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
    """
    是什么：test_single_message_error_is_saved_and_streamed 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer='{"success": false, "message": "forced"}')

    def _raise_single_message(*, session, res, operate):
        """
        是什么：_raise_single_message 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
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
    """
    是什么：test_dynamic_assistant_datasource_executes_expanded_sql 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    sql_answer = _sql_answer("select * from orders", ["orders"])
    service = FakeSmartQAService(
        current_assistant=SimpleNamespace(type=1),
        sql_answer=sql_answer,
    )

    def _dynamic_sql(session, sql, tables):
        """
        是什么：_dynamic_sql 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        assert session is not None
        assert sql == "select * from orders"
        assert tables == ["orders"]
        return {
            "orders": "select id, amount from public.orders",
            "app_temp_sql_text": _sql_answer("select * from app_dynamic_temp_table_orders", ["orders"]),
        }

    def _check_save_sql(*, session, res, operate):
        """
        是什么：_check_save_sql 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
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
    """
    是什么：test_non_chat_stream_query_data_returns_markdown 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
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
    """
    是什么：test_non_stream_full_chart_returns_json_result 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
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
    """
    是什么：test_chart_generation_tolerates_reasoning_only_chunk 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
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
    """
    是什么：test_llm_service_routes_smart_qa_to_graph 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=8001)
    calls: list[dict[str, Any]] = []

    def _fake_graph(service_arg, *, in_chat: bool, stream: bool, finish_step: ChatFinishStep, return_img: bool):
        """
        是什么：_fake_graph 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
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
