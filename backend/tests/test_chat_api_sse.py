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
    return AssistantHeader(
        id=3001,
        name="API Assistant",
        domain="http://localhost",
        type=1,
        custom_model=None,
    )


async def _response_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(chunk)
    return "".join(chunks)


async def _sse_events(response) -> list[dict[str, Any]]:
    body = await _response_body(response)
    events: list[dict[str, Any]] = []
    for block in body.split("\n\n"):
        if not block.startswith("data:"):
            continue
        events.append(json.loads(block[5:]))
    return events


class FakeLLMService:
    instances: list[FakeLLMService] = []
    create_calls: list[dict[str, Any]] = []

    def __init__(self, *, chunks: list[Any] | None = None) -> None:
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
        self.init_record_calls.append(session)

    def run_task_async(
        self,
        *,
        in_chat: bool,
        stream: bool,
        finish_step: ChatFinishStep,
        return_img: bool,
    ) -> None:
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
        yield from self.chunks


@pytest.fixture(autouse=True)
def _patch_common_api_dependencies(monkeypatch: pytest.MonkeyPatch):
    FakeLLMService.instances = []
    FakeLLMService.create_calls = []

    async def _allow_request(*_args, **_kwargs):
        return None

    monkeypatch.setattr(chat_api, "LLMService", FakeLLMService)
    monkeypatch.setattr(chat_api, "_tenant_rate_limit_response", _allow_request)
    monkeypatch.setattr(chat_api, "_current_tenant_id", lambda current_user: int(current_user.tenant_id))


def test_question_answer_stream_sse_and_finish_step() -> None:
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
    with pytest.raises(chat_api.HTTPException) as exc:
        chat_api._parse_chat_finish_step(999)

    assert exc.value.status_code == 400
    assert "finish_step must be one of" in exc.value.detail


def test_stream_sql_non_stream_json_status() -> None:
    service = FakeLLMService(chunks=[{"success": False, "message": "boom"}])

    async def _create(*_args, **_kwargs):
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
    def __iter__(self):
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
    def execute(self, stmt):
        return FakeAnalysisResult()


def test_analysis_api_streams_sse_events(monkeypatch: pytest.MonkeyPatch) -> None:
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
