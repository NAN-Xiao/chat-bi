"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.responses import JSONResponse

from apps.chat.api import chat as chat_api
from apps.chat.models.chat_model import (
    ChatFinishStep,
    ChatQuestion,
    ChatRecord,
)
from apps.system.schemas.system_schema import AssistantHeader, UserInfoDTO


def _user() -> UserInfoDTO:
    """
    是什么：_user 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return UserInfoDTO(
        id=1001,
        account="api-test",
        name="API Test",
        email="api-test@example.com",
        password="unused",
        tenant_id=2001,
        tenant_role="owner",
        has_workspace=True,
        workspace_status="active",
    )


def _assistant() -> AssistantHeader:
    """
    是什么：_assistant 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return AssistantHeader(
        id=3001,
        name="API Assistant",
        domain="http://localhost",
        type=1,
        custom_model=None,
    )


async def _response_body(response) -> str:
    """
    是什么：_response_body 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(chunk)
    return "".join(chunks)


async def _sse_events(response) -> list[dict[str, Any]]:
    """
    是什么：_sse_events 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    body = await _response_body(response)
    events: list[dict[str, Any]] = []
    for block in body.split("\n\n"):
        if not block.startswith("data:"):
            continue
        events.append(json.loads(block[5:]))
    return events


class FakeLLMService:
    """
    类说明：FakeLLMService 把测试的一组操作放在一起，对外提供更容易调用的业务能力。
    """
    instances: list[FakeLLMService] = []
    create_calls: list[dict[str, Any]] = []

    def __init__(self, *, chunks: list[Any] | None = None) -> None:
        """
        是什么：FakeLLMService.__init__ 是 FakeLLMService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.chunks = chunks or [
            'data:{"type":"id","id":9001}\n\n',
            'data:{"type":"sql","content":"select 1"}\n\n',
            'data:{"type":"finish"}\n\n',
        ]
        self.init_record_calls: list[Any] = []
        self.run_task_async_calls: list[dict[str, Any]] = []
        self.run_analysis_async_calls: list[dict[str, Any]] = []
        FakeLLMService.instances.append(self)

    @classmethod
    async def create(cls, session, current_user, request_question, current_assistant=None, *args, **kwargs):
        """
        是什么：FakeLLMService.create 是 FakeLLMService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        cls.create_calls.append({
            "session": session,
            "current_user": current_user,
            "request_question": request_question,
            "current_assistant": current_assistant,
            "args": args,
            "kwargs": kwargs,
        })
        return cls()

    def init_record(self, *, session):
        """
        是什么：FakeLLMService.init_record 是 FakeLLMService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.init_record_calls.append(session)

    def run_task_async(
        self,
        *,
        in_chat: bool,
        stream: bool,
        finish_step: ChatFinishStep,
        return_img: bool,
    ) -> None:
        """
        是什么：FakeLLMService.run_task_async 是 FakeLLMService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试的主要流程跑起来，一步步调用需要的处理。
        """
        self.run_task_async_calls.append({
            "in_chat": in_chat,
            "stream": stream,
            "finish_step": finish_step,
            "return_img": return_img,
        })

    def run_analysis_or_predict_task_async(
        self,
        session,
        action_type: str,
        base_record: ChatRecord,
        in_chat: bool,
        stream: bool,
    ) -> None:
        """
        是什么：FakeLLMService.run_analysis_or_predict_task_async 是 FakeLLMService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试的主要流程跑起来，一步步调用需要的处理。
        """
        self.run_analysis_async_calls.append({
            "session": session,
            "action_type": action_type,
            "base_record": base_record,
            "in_chat": in_chat,
            "stream": stream,
        })
        if action_type == "analysis":
            self.chunks = [
                'data:{"type":"id","id":9101}\n\n',
                'data:{"type":"analysis-result","content":"analysis"}\n\n',
                'data:{"type":"analysis_finish"}\n\n',
            ]
        else:
            self.chunks = [
                {"success": True, "record_id": 9102, "origin_data": {"fields": []}, "predict_data": []},
            ]

    def await_result(self):
        """
        是什么：FakeLLMService.await_result 是 FakeLLMService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试处理过程中的消息或结果一段段传出去。
        """
        yield from self.chunks


@pytest.fixture(autouse=True)
def _patch_common_api_dependencies(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：_patch_common_api_dependencies 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    FakeLLMService.instances = []
    FakeLLMService.create_calls = []

    async def _allow_request(*_args, **_kwargs):
        """
        是什么：_allow_request 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        return None

    monkeypatch.setattr(chat_api, "LLMService", FakeLLMService)
    monkeypatch.setattr(chat_api, "_tenant_rate_limit_response", _allow_request)
    monkeypatch.setattr(chat_api, "_current_tenant_id", lambda current_user: int(current_user.tenant_id))


def test_question_answer_stream_sse_and_finish_step() -> None:
    """
    是什么：test_question_answer_stream_sse_and_finish_step 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    response = asyncio.run(
        chat_api.question_answer_inner(
            session=object(),
            current_user=_user(),
            request_question=ChatQuestion(chat_id=8001, question="show value"),
            current_assistant=None,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_SQL,
            embedding=True,
        )
    )

    events = asyncio.run(_sse_events(response))
    service = FakeLLMService.instances[-1]

    assert response.media_type == "text/event-stream"
    assert [event["type"] for event in events] == ["id", "sql", "finish"]
    assert service.run_task_async_calls == [
        {
            "in_chat": True,
            "stream": True,
            "finish_step": ChatFinishStep.GENERATE_SQL,
            "return_img": True,
        }
    ]
    assert FakeLLMService.create_calls[-1]["kwargs"]["embedding"] is True


def test_question_answer_invalid_finish_step_returns_400() -> None:
    """
    是什么：test_question_answer_invalid_finish_step_returns_400 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    with pytest.raises(chat_api.HTTPException) as exc:
        chat_api._parse_chat_finish_step(999)

    assert exc.value.status_code == 400
    assert "finish_step must be one of" in exc.value.detail


def test_stream_sql_non_stream_json_status() -> None:
    """
    是什么：test_stream_sql_non_stream_json_status 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeLLMService(chunks=[{"success": False, "message": "boom"}])

    async def _create(*_args, **_kwargs):
        """
        是什么：_create 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        return service

    original_create = FakeLLMService.create
    try:
        FakeLLMService.create = _create
        response = asyncio.run(
            chat_api.stream_sql(
                session=object(),
                current_user=_user(),
                request_question=ChatQuestion(chat_id=8001, question="show value"),
                current_assistant=None,
                in_chat=False,
                stream=False,
            )
        )
    finally:
        FakeLLMService.create = original_create

    assert isinstance(response, JSONResponse)
    assert response.status_code == 500
    assert json.loads(response.body) == {"success": False, "message": "boom"}


def test_assistant_context_is_passed_to_llm_service() -> None:
    """
    是什么：test_assistant_context_is_passed_to_llm_service 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    assistant = _assistant()

    response = asyncio.run(
        chat_api.question_answer_inner(
            session=object(),
            current_user=_user(),
            request_question=ChatQuestion(chat_id=8001, question="assistant question"),
            current_assistant=assistant,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        )
    )

    events = asyncio.run(_sse_events(response))

    assert [event["type"] for event in events] == ["id", "sql", "finish"]
    assert FakeLLMService.create_calls[-1]["current_assistant"] is assistant
    assert FakeLLMService.instances[-1].run_task_async_calls[-1]["finish_step"] == ChatFinishStep.QUERY_DATA


class FakeAnalysisResult:
    """
    类说明：FakeAnalysisResult 把测试相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __iter__(self):
        """
        是什么：FakeAnalysisResult.__iter__ 是 FakeAnalysisResult 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：让这个对象能配合 Python 的特殊用法工作。
        """
        yield SimpleNamespace(
            id=7701,
            tenant_id=2001,
            question="base chart",
            chat_id=8001,
            datasource=1,
            engine_type="PostgreSQL",
            ai_modal_id=None,
            create_by=1001,
            chart='{"type":"table"}',
            data=None,
            custom_prompt_id=None,
            data_skill_id=None,
            agent_context_snapshot=None,
        )


class FakeAnalysisSession:
    """
    类说明：FakeAnalysisSession 把测试相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def execute(self, stmt):
        """
        是什么：FakeAnalysisSession.execute 是 FakeAnalysisSession 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试的主要流程跑起来，一步步调用需要的处理。
        """
        return FakeAnalysisResult()


def test_analysis_api_streams_sse_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：test_analysis_api_streams_sse_events 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    monkeypatch.setattr(chat_api, "get_chart_data_with_user", lambda *args, **kwargs: {"fields": [], "data": []})

    response = asyncio.run(
        chat_api.analysis_or_predict(
            session=FakeAnalysisSession(),
            current_user=_user(),
            chat_record_id=7701,
            action_type="analysis",
            current_assistant=None,
            in_chat=True,
            stream=True,
        )
    )
    events = asyncio.run(_sse_events(response))
    service = FakeLLMService.instances[-1]

    assert response.media_type == "text/event-stream"
    assert [event["type"] for event in events] == ["id", "analysis-result", "analysis_finish"]
    assert service.run_analysis_async_calls[-1]["action_type"] == "analysis"
    assert service.run_analysis_async_calls[-1]["base_record"].id == 7701


def test_predict_api_non_stream_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：test_predict_api_non_stream_json 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    monkeypatch.setattr(chat_api, "get_chart_data_with_user", lambda *args, **kwargs: {"fields": [], "data": []})

    response = asyncio.run(
        chat_api.analysis_or_predict(
            session=FakeAnalysisSession(),
            current_user=_user(),
            chat_record_id=7701,
            action_type="predict",
            current_assistant=None,
            in_chat=False,
            stream=False,
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "success": True,
        "record_id": 9102,
        "origin_data": {"fields": []},
        "predict_data": [],
    }


def test_analysis_api_invalid_action_returns_stream_error() -> None:
    """
    是什么：test_analysis_api_invalid_action_returns_stream_error 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    response = asyncio.run(
        chat_api.analysis_or_predict(
            session=FakeAnalysisSession(),
            current_user=_user(),
            chat_record_id=7701,
            action_type="bad-action",
            current_assistant=None,
            in_chat=True,
            stream=True,
        )
    )

    events = asyncio.run(_sse_events(response))

    assert events == [{"content": "Type bad-action Not Found", "type": "error"}]
