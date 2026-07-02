"""
脚本说明：这个脚本验证聊天历史加载只读取已保存快照，不在默认详情接口里重跑业务 SQL。
"""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from apps.chat.curd import chat as chat_crud
from apps.chat.models.chat_model import Chat
from apps.system.schemas.system_schema import UserInfoDTO


class _FakeResult:
    """
    类说明：_FakeResult 模拟 SQLAlchemy 查询结果，供历史加载测试使用。
    """

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """
    类说明：_FakeSession 只实现 get_chat_with_records 本测试路径需要的最小数据库接口。
    """

    def __init__(self):
        self._execute_calls = 0

    def get(self, model, obj_id):
        if getattr(model, "__name__", "") == "Chat":
            return Chat(
                id=obj_id,
                tenant_id=2001,
                create_by=1001,
                create_time=datetime(2026, 6, 30, 20, 0, 0),
                brief="历史会话",
                chat_type="chat",
                datasource=1,
                engine_type="PostgreSQL",
            )
        if getattr(model, "__name__", "") == "CoreDatasource":
            return SimpleNamespace(id=obj_id, name="测试数据源", type="postgresql")
        return None

    def execute(self, _stmt):
        self._execute_calls += 1
        if self._execute_calls == 1:
            cached_data = json.dumps(
                {
                    "fields": ["day", "revenue"],
                    "data": [{"day": "2026-06-30", "revenue": 12.5}],
                }
            )
            cached_predict_data = json.dumps([{"day": "2026-07-01", "revenue": 14.0}])
            return _FakeResult(
                [
                    SimpleNamespace(
                        id=9001,
                        tenant_id=2001,
                        chat_id=8001,
                        create_time=datetime(2026, 6, 30, 20, 1, 0),
                        finish_time=datetime(2026, 6, 30, 20, 1, 5),
                        question="最近 7 天收入",
                        sql_answer="",
                        sql="select day, revenue from fact_payments",
                        datasource=1,
                        chart_answer="",
                        chart='{"type":"line"}',
                        analysis=None,
                        predict=None,
                        datasource_select_answer=None,
                        analysis_record_id=None,
                        predict_record_id=None,
                        regenerate_record_id=None,
                        custom_prompt_id=None,
                        data_skill_id=None,
                        agent_context_snapshot=None,
                        recommended_question=None,
                        first_chat=False,
                        finish=True,
                        error=None,
                        data=cached_data,
                        predict_data=cached_predict_data,
                        sql_reasoning_content=None,
                        chart_reasoning_content=None,
                        analysis_reasoning_content=None,
                        predict_reasoning_content=None,
                    )
                ]
            )
        return _FakeResult([])


class _SingleRecordSession(_FakeSession):
    """
    类说明：_SingleRecordSession 用一条自定义聊天记录测试历史脱敏分支。
    """

    def __init__(self, row):
        super().__init__()
        self._row = row

    def execute(self, _stmt):
        self._execute_calls += 1
        if self._execute_calls == 1:
            return _FakeResult([self._row])
        return _FakeResult([])


def _user() -> UserInfoDTO:
    return UserInfoDTO(
        id=1001,
        account="history-test",
        name="History Test",
        email="history-test@example.com",
        password="unused",
        tenant_id=2001,
        tenant_role="owner",
        has_workspace=True,
        workspace_status="active",
    )


def _history_row(**overrides):
    """
    是什么：构造 get_chat_with_records 查询出来的最小聊天记录行。
    """
    values = dict(
        id=9002,
        tenant_id=2001,
        chat_id=8001,
        create_time=datetime(2026, 6, 30, 20, 2, 0),
        finish_time=datetime(2026, 6, 30, 20, 2, 5),
        question="测试问题",
        sql_answer="模型生成过程",
        sql=None,
        datasource=1,
        chart_answer=None,
        chart=None,
        analysis=None,
        predict=None,
        datasource_select_answer=None,
        analysis_record_id=None,
        predict_record_id=None,
        regenerate_record_id=None,
        custom_prompt_id=None,
        data_skill_id=None,
        agent_context_snapshot=None,
        recommended_question=None,
        first_chat=False,
        finish=True,
        error=None,
        data=None,
        predict_data=None,
        sql_reasoning_content="模型推理过程",
        chart_reasoning_content=None,
        analysis_reasoning_content=None,
        predict_reasoning_content=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_default_history_loading_uses_cached_data_without_executing_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：验证默认历史详情接口不会因为记录里有 SQL 就实时执行 SQL。
    """

    def _unexpected_live_data(*_args, **_kwargs):
        raise AssertionError("默认历史加载不应执行历史 SQL")

    monkeypatch.setattr(chat_crud, "get_chart_data_with_user", _unexpected_live_data)
    monkeypatch.setattr(chat_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_allowed_by_current_permissions", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_requires_live_data_for_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        chat_crud,
        "_source_record_requires_live_data_for_current_permissions",
        lambda *_args, **_kwargs: False,
    )

    chat_info = chat_crud.get_chat_with_records(
        session=_FakeSession(),
        chart_id=8001,
        current_user=_user(),
        current_assistant=None,
        with_data=False,
    )

    assert len(chat_info.records) == 1
    assert chat_info.records[0]["data"] == {
        "fields": ["day", "revenue"],
        "data": [{"day": "2026-06-30", "revenue": 12.5}],
    }
    assert chat_info.records[0]["predict_data"] == [{"day": "2026-07-01", "revenue": 14.0}]


def test_history_loading_scrubs_cached_data_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：验证当前用户命中任意数据权限时，默认历史详情不会返回旧快照数据。
    """

    def _unexpected_live_data(*_args, **_kwargs):
        raise AssertionError("默认历史加载不应执行历史 SQL")

    monkeypatch.setattr(chat_crud, "get_chart_data_with_user", _unexpected_live_data)
    monkeypatch.setattr(chat_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_allowed_by_current_permissions", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_requires_live_data_for_current_permissions", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        chat_crud,
        "_source_record_requires_live_data_for_current_permissions",
        lambda *_args, **_kwargs: False,
    )

    chat_info = chat_crud.get_chat_with_records(
        session=_FakeSession(),
        chart_id=8001,
        current_user=_user(),
        current_assistant=None,
        with_data=False,
    )

    assert len(chat_info.records) == 1
    assert chat_info.records[0]["data"]["status"] == "failed"
    assert chat_info.records[0]["data"]["error_type"] == "permission_denied"
    assert chat_info.records[0]["data"]["message"] == "没有查看权限"
    assert chat_info.records[0]["predict_data"] is None


def test_history_loading_preserves_business_error_without_sql_when_scrubbed(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：生成阶段的业务失败没有 SQL/数据结果时，历史记录应展示原始业务提示而不是权限错误。
    """
    message = (
        "DAU/PDAU 趋势不能使用 fact_events 事件明细直接替代活跃或付费口径。"
        "请按本 Data Skill 使用 fact_sessions 计算 DAU，使用 fact_payments 的成功净收入订单计算 PDAU。"
    )

    monkeypatch.setattr(chat_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_allowed_by_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(chat_crud, "_record_requires_live_data_for_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        chat_crud,
        "_source_record_requires_live_data_for_current_permissions",
        lambda *_args, **_kwargs: False,
    )

    chat_info = chat_crud.get_chat_with_records(
        session=_SingleRecordSession(_history_row(error=message)),
        chart_id=8001,
        current_user=_user(),
        current_assistant=None,
        with_data=False,
    )

    record = chat_info.records[0]
    assert record["error"] == message
    assert record["data"] is None
    assert record["sql"] is None
    assert record["sql_answer"] is None


def test_history_loading_still_scrubs_sql_record_when_permission_denied(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：真正带 SQL 或结果缓存的记录权限失效时，仍然不能泄露历史数据。
    """
    cached_data = json.dumps(
        {
            "fields": ["day", "revenue"],
            "data": [{"day": "2026-06-30", "revenue": 12.5}],
        }
    )

    monkeypatch.setattr(chat_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_allowed_by_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(chat_crud, "_record_requires_live_data_for_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        chat_crud,
        "_source_record_requires_live_data_for_current_permissions",
        lambda *_args, **_kwargs: False,
    )

    chat_info = chat_crud.get_chat_with_records(
        session=_SingleRecordSession(
            _history_row(
                sql="select day, revenue from fact_payments",
                error="原始 SQL 错误",
                data=cached_data,
            )
        ),
        chart_id=8001,
        current_user=_user(),
        current_assistant=None,
        with_data=False,
    )

    record = chat_info.records[0]
    assert record["error"] == "没有查看权限"
    assert record["data"]["status"] == "failed"
    assert record["data"]["error_type"] == "permission_denied"
    assert record["sql"] is None
    assert record["sql_answer"] is None


def test_history_loading_does_not_preserve_permission_error_without_sql(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：没有 SQL 的记录如果原始错误就是权限问题，也必须继续显示统一权限提示。
    """
    monkeypatch.setattr(chat_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_crud, "_record_allowed_by_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(chat_crud, "_record_requires_live_data_for_current_permissions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        chat_crud,
        "_source_record_requires_live_data_for_current_permissions",
        lambda *_args, **_kwargs: False,
    )

    chat_info = chat_crud.get_chat_with_records(
        session=_SingleRecordSession(_history_row(error="当前用户无权访问项目 1")),
        chart_id=8001,
        current_user=_user(),
        current_assistant=None,
        with_data=False,
    )

    record = chat_info.records[0]
    assert record["error"] == "没有查看权限"
    assert record["data"]["error_type"] == "permission_denied"
