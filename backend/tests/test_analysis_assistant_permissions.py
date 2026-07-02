"""
脚本说明：验证分析助手在数据权限收紧后不会复用历史、上下文或导出快照。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.analysis_assistant.models import AnalysisAssistantConversation
from apps.system.schemas.system_schema import UserInfoDTO


class _FakeSession:
    """
    类说明：提供分析助手权限测试需要的最小 session 行为。
    """

    def get(self, model, obj_id):
        if getattr(model, "__name__", "") == "CoreDatasource":
            return SimpleNamespace(id=obj_id, name="测试项目", type="postgresql")
        return None


def _user() -> UserInfoDTO:
    return UserInfoDTO(
        id=1001,
        account="analysis-permission-test",
        name="Analysis Permission Test",
        email="analysis-permission-test@example.com",
        password="unused",
        tenant_id=2001,
        tenant_role="member",
        has_workspace=True,
        workspace_status="active",
    )


def _conversation() -> AnalysisAssistantConversation:
    return AnalysisAssistantConversation(
        id=9001,
        tenant_id=2001,
        create_by=1001,
        title="收入分析",
        datasource_id=1,
        datasource_name="测试项目",
        messages=[
            {"role": "user", "content": "看收入趋势"},
            {
                "role": "assistant",
                "content": "",
                "blocks": [
                    {
                        "id": "q1",
                        "title": "收入趋势",
                        "purpose": "查看收入",
                        "sql": "select day, revenue from fact_payments",
                        "fields": ["day", "revenue"],
                        "data": [{"day": "2026-06-30", "revenue": 12.5}],
                        "chart": {"type": "line"},
                        "summary": "收入为 12.5",
                    }
                ],
                "final": "收入为 12.5",
            },
        ],
        create_time=datetime(2026, 6, 30, 20, 0, 0),
        update_time=datetime(2026, 6, 30, 20, 5, 0),
    )


def test_history_detail_scrubs_saved_blocks_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：命中任意数据权限时，分析助手历史不返回旧 rows、字段、图表、SQL 和最终总结。
    """
    monkeypatch.setattr(analysis_api, "is_normal_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        analysis_api,
        "validate_user_query_sql_or_raise",
        lambda *_args, **_kwargs: ("select day, revenue from fact_payments", {"fact_payments"}),
    )
    monkeypatch.setattr(analysis_api, "has_applicable_permissions", lambda *_args, **_kwargs: True)

    detail = analysis_api._conversation_detail(_conversation(), _FakeSession(), _user())

    block = detail.messages[1]["blocks"][0]
    assert block["error_type"] == "permission_denied"
    assert block["error"] == "没有查看权限"
    assert block["fields"] == []
    assert block["data"] == []
    assert block["chart"] is None
    assert block["summary"] == ""
    assert block["sql"] == ""
    assert detail.messages[1]["final"] == "没有查看权限"


def test_history_detail_keeps_saved_blocks_without_permission_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：没有命中数据权限时，分析助手历史仍可复用已保存快照，不触发实时查询。
    """
    monkeypatch.setattr(analysis_api, "is_normal_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        analysis_api,
        "validate_user_query_sql_or_raise",
        lambda *_args, **_kwargs: ("select day, revenue from fact_payments", {"fact_payments"}),
    )
    monkeypatch.setattr(analysis_api, "has_applicable_permissions", lambda *_args, **_kwargs: False)

    detail = analysis_api._conversation_detail(_conversation(), _FakeSession(), _user())

    block = detail.messages[1]["blocks"][0]
    assert block["data"] == [{"day": "2026-06-30", "revenue": 12.5}]
    assert block["sql"] == "select day, revenue from fact_payments"
    assert detail.messages[1]["final"] == "收入为 12.5"


def test_chat_request_drops_client_context_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：命中数据权限时，分析助手实时问答不把前端历史/页面上下文交给模型。
    """
    monkeypatch.setattr(analysis_api, "is_normal_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "has_applicable_permissions", lambda *_args, **_kwargs: True)

    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        context="旧看板里收入是 12.5",
        messages=[
            analysis_api.AnalysisAssistantMessage(role="assistant", content="旧收入是 12.5"),
            analysis_api.AnalysisAssistantMessage(role="user", content="继续分析"),
        ],
    )

    sanitized = analysis_api._sanitize_analysis_request_context_for_current_permissions(
        _FakeSession(),
        _user(),
        request,
    )

    assert sanitized.context is None
    assert len(sanitized.messages) == 1
    assert sanitized.messages[0].role == "user"
    assert sanitized.messages[0].content == "继续分析"


def test_export_report_rejects_client_snapshot_when_permissions_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：导出依赖客户端提交的数据快照；命中权限时直接拒绝，避免把旧数据写进文件。
    """
    monkeypatch.setattr(analysis_api, "is_normal_user", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "has_applicable_permissions", lambda *_args, **_kwargs: True)

    request = analysis_api.AnalysisAssistantExportRequest(
        datasource_id=1,
        format="pdf",
        blocks=[
            analysis_api.AnalysisAssistantExportBlock(
                title="收入趋势",
                fields=["day", "revenue"],
                data=[{"day": "2026-06-30", "revenue": 12.5}],
            )
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(analysis_api.export_report(request, _user(), _FakeSession()))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "没有查看权限"
