"""
脚本说明：验证分析助手在数据权限收紧后不会复用历史、上下文或导出快照。
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.analysis_assistant.models import AnalysisAssistantConversation
from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimePolicy,
    AnalysisTimeResolution,
    AnalysisTimeSource,
    parse_analysis_time_intent,
    resolve_analysis_time_policy,
)
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


def _resolved_time(
    *,
    warnings: tuple[str, ...] = (),
    traces: tuple[str, ...] = (),
) -> AnalysisTimeResolution:
    policy = AnalysisTimePolicy(
        source=AnalysisTimeSource.DEFAULT_14_DAYS,
        window_days=14,
        anchor_date=date(2026, 7, 26),
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 26),
        start_inclusive=True,
        end_inclusive=True,
        anchor=AnalysisTimeAnchor("fact_orders", "business_date"),
        description="最近 14 个自然日",
    )
    return AnalysisTimeResolution(
        policy=policy,
        status="resolved",
        warnings=warnings,
        traces=traces,
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


def test_chat_builds_business_sql_context_before_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：分析助手实时 SQL 生成前通过 SQL Engine 统一业务库上下文取 schema、字典和 Data Skill。
    """
    datasource = analysis_api.CoreDatasource(
        id=1,
        name="测试项目",
        type="postgresql",
        type_name="PostgreSQL",
        configuration="{}",
    )
    class _BusinessContext(SimpleNamespace):
        def snapshot_metadata(self):
            return {
                "context_hash": "ctx",
                "datasource_id": "1",
                "sql_dialect": "postgres",
                "allowed_tables": ["fact_payments"],
            }

    business_context = _BusinessContext(
        datasource=datasource,
        schema="【Schema】\n# Table: fact_payments",
        allowed_tables=["fact_payments"],
        data_skill="<Data-Skills>收入口径</Data-Skills>",
        tracking_config="<Tracking>支付事件字典</Tracking>",
        business_context_hash="ctx",
    )
    calls: list[dict] = []
    snapshots: list[dict] = []

    def _build_context(**kwargs):
        calls.append(kwargs)
        return business_context

    class _Llm:
        def stream(self, _messages):
            raise AssertionError("本测试不消费 SSE 流，不应调用 LLM")

    async def _no_rate_limit(*_args, **_kwargs):
        return None

    async def _fake_create_llm(*_args, **_kwargs):
        return _Llm(), SimpleNamespace(model_id=7, model_name="test-model")

    async def _fake_resolve_time_policy(**_kwargs):
        return _resolved_time()

    monkeypatch.setattr(analysis_api, "_sanitize_analysis_request_context_for_current_permissions", lambda _s, _u, req: req)
    monkeypatch.setattr(analysis_api, "_tenant_rate_limit_response", _no_rate_limit)
    monkeypatch.setattr(analysis_api, "_get_datasource", lambda *_args, **_kwargs: datasource)
    monkeypatch.setattr(analysis_api, "_collect_custom_agent_context", lambda *_args, **_kwargs: ("", None))
    monkeypatch.setattr(analysis_api.BusinessSqlContextService, "build", staticmethod(_build_context))
    monkeypatch.setattr(
        analysis_api,
        "_create_llm",
        _fake_create_llm,
    )
    monkeypatch.setattr(
        analysis_api,
        "_resolve_chat_time_policy",
        _fake_resolve_time_policy,
    )

    def _snapshot(**kwargs):
        snapshots.append(kwargs)
        return {"snapshot": "ok"}

    monkeypatch.setattr(analysis_api, "build_agent_context_snapshot", _snapshot)

    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        data_skill_id=88,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="看收入趋势")],
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))

    assert response.media_type == "text/event-stream"
    assert calls[0]["tenant_id"] == 2001
    assert calls[0]["datasource_id"] == 1
    assert calls[0]["question"] == "看收入趋势"
    assert calls[0]["data_skill_id"] == 88
    assert snapshots[0]["data_skill_text"] == (
        "<Tracking>支付事件字典</Tracking>\n\n<Data-Skills>收入口径</Data-Skills>"
    )
    assert snapshots[0]["business_context"]["sql_dialect"] == "postgres"
    assert snapshots[0]["business_context"]["analysis_time_policy"] == {
        "source": "DEFAULT_14_DAYS",
        "window_days": 14,
        "start_date": "2026-07-13",
        "end_date": "2026-07-26",
        "start_inclusive": True,
        "end_inclusive": True,
        "anchor": {"table": "fact_orders", "field": "business_date"},
        "status": "resolved",
        "warnings": [],
    }


def test_chat_deduplicates_real_unresolved_time_policy_trace_after_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 unresolved 的同一 warning/trace 在轨迹中只输出一次。"""
    datasource = analysis_api.CoreDatasource(
        id=1,
        name="测试项目",
        type="postgresql",
        type_name="PostgreSQL",
        configuration="{}",
    )

    class _BusinessContext(SimpleNamespace):
        def snapshot_metadata(self):
            return {
                "context_hash": "ctx",
                "datasource_id": "1",
                "sql_dialect": "postgres",
                "allowed_tables": ["fact_payments"],
            }

    business_context = _BusinessContext(
        datasource=datasource,
        schema="【Schema】\n# Table: fact_payments",
        allowed_tables=["fact_payments"],
        data_skill="",
        tracking_config="",
        business_context_hash="ctx",
    )

    class _Llm:
        def stream(self, _messages):
            raise AssertionError("读取时间策略轨迹时不应进入计划生成")

    async def _no_rate_limit(*_args, **_kwargs):
        return None

    async def _fake_create_llm(*_args, **_kwargs):
        return _Llm(), SimpleNamespace(model_id=7, model_name="test-model")

    async def _fake_resolve_time_policy(**_kwargs):
        return resolve_analysis_time_policy(
            parse_analysis_time_intent("最近7天收入", []),
            skill_window_days=None,
            anchor=None,
            anchor_date=None,
        )

    monkeypatch.setattr(
        analysis_api,
        "_sanitize_analysis_request_context_for_current_permissions",
        lambda _s, _u, req: req,
    )
    monkeypatch.setattr(analysis_api, "_tenant_rate_limit_response", _no_rate_limit)
    monkeypatch.setattr(analysis_api, "_get_datasource", lambda *_args, **_kwargs: datasource)
    monkeypatch.setattr(
        analysis_api,
        "_collect_custom_agent_context",
        lambda *_args, **_kwargs: ("", None),
    )
    monkeypatch.setattr(
        analysis_api.BusinessSqlContextService,
        "build",
        staticmethod(lambda **_kwargs: business_context),
    )
    monkeypatch.setattr(analysis_api, "_create_llm", _fake_create_llm)
    monkeypatch.setattr(
        analysis_api,
        "_resolve_chat_time_policy",
        _fake_resolve_time_policy,
    )
    monkeypatch.setattr(
        analysis_api,
        "build_agent_context_snapshot",
        lambda **_kwargs: {"snapshot": "ok"},
    )
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="看收入趋势")],
    )

    async def _collect_first_three_chunks() -> list[str]:
        response = await analysis_api.chat(request, _user(), _FakeSession())
        chunks: list[str] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
            if len(chunks) == 3:
                break
        await response.body_iterator.aclose()
        return chunks

    chunks = asyncio.run(_collect_first_three_chunks())

    assert '"type":"context_snapshot"' in chunks[0]
    trace_chunks = [chunk for chunk in chunks if '"type":"trace"' in chunk]
    assert len(trace_chunks) == 1
    assert "无法确认当前数据源的时间锚点" in trace_chunks[0]
    assert '"type":"error"' in chunks[2]


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


def test_report_interpretation_rejects_client_context_when_permissions_apply(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：图表/报表解读命中数据权限风险时，不把前端旧上下文交给模型解读。
    """
    monkeypatch.setattr(analysis_api, "_datasource_has_current_permission_risk", lambda *_args, **_kwargs: True)

    def _unexpected_llm(*_args, **_kwargs):
        raise AssertionError("权限风险下不应创建 LLM 或读取解读上下文")

    monkeypatch.setattr(analysis_api, "_create_llm", _unexpected_llm)
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        context="旧图表数据：收入 12.5",
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
    )

    response = asyncio.run(analysis_api.report_interpretation(request, _user(), _FakeSession()))
    body = b"".join(asyncio.run(_collect_stream_body(response)))

    assert response.media_type == "text/event-stream"
    assert "permission_denied" in body.decode()
    assert "没有查看权限" in body.decode()


def test_report_interpretation_allows_permission_filtered_visible_data(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：实时看板目标已经通过资源校验且有可见数据时，行权限不能再整体禁止解读。
    """
    monkeypatch.setattr(analysis_api, "_datasource_has_current_permission_risk", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(analysis_api, "validate_dashboard_report_target", lambda *_args, **_kwargs: None)
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        context="当前可见图表数据：收入 12.5",
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
        report_target=analysis_api.ReportInterpretationTarget(
            dashboard_id="dashboard-1",
            component_ids=["chart-1"],
            has_visible_data=True,
            has_permission_denied=False,
        ),
    )

    response = analysis_api._report_interpretation_preflight(request, _user(), _FakeSession())

    assert response is None


def test_report_interpretation_rejects_permission_denied_chart(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：当前图表已经返回权限失败时，实时解读不能复用旧的成功数据。
    """
    validate_calls = []
    monkeypatch.setattr(
        analysis_api,
        "validate_dashboard_report_target",
        lambda *_args, **_kwargs: validate_calls.append(True),
    )
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        context="旧图表数据：收入 12.5",
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
        report_target=analysis_api.ReportInterpretationTarget(
            dashboard_id="dashboard-1",
            component_ids=["chart-1"],
            has_visible_data=True,
            has_permission_denied=True,
        ),
    )

    response = analysis_api._report_interpretation_preflight(request, _user(), _FakeSession())
    body = b"".join(asyncio.run(_collect_stream_body(response)))

    assert validate_calls == []
    assert "permission_denied" in body.decode()
    assert "没有查看权限" in body.decode()


def test_report_interpretation_preflight_maps_target_validation_failure_to_permission_denied(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """服务端目标校验失败时，解读入口只能返回统一权限错误。"""
    monkeypatch.setattr(
        analysis_api,
        "validate_dashboard_report_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPException(status_code=403)),
    )
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=11,
        context="旧图表数据：收入 12.5",
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
        report_target=analysis_api.ReportInterpretationTarget(
            dashboard_id="dashboard-1",
            component_ids=["chart-1"],
            has_visible_data=True,
            has_permission_denied=False,
        ),
    )

    response = analysis_api._report_interpretation_preflight(request, _user(), _FakeSession())
    body = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert "permission_denied" in body
    assert "没有查看权限" in body


def test_report_interpretation_uses_chart_execution_datasource_for_report_target(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """报表解读应按图表执行数据源加载 ROI 项目，而非要求用户直接授权。"""
    datasource = SimpleNamespace(id=22, name="ROI 项目", type="mysql")
    resolved_ids: list[int | None] = []
    monkeypatch.setattr(
        analysis_api,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_ids.append(datasource_id) or 22,
    )
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=22,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
        report_target=analysis_api.ReportInterpretationTarget(
            dashboard_id="dashboard-1",
            component_ids=["chart-1"],
            has_visible_data=True,
            has_permission_denied=False,
        ),
    )

    result = analysis_api._get_report_interpretation_datasource(
        _FakeSession(),
        _user(),
        request,
    )

    assert result.id == datasource.id
    assert resolved_ids == [22]


def test_report_interpretation_returns_no_data_for_valid_empty_target(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：目标合法但没有当前可见行时，应提示无数据而不是误报无权限。
    """
    monkeypatch.setattr(analysis_api, "validate_dashboard_report_target", lambda *_args, **_kwargs: None)
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        context="当前图表没有可见行",
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
        report_target=analysis_api.ReportInterpretationTarget(
            dashboard_id="dashboard-1",
            component_ids=["chart-1"],
            has_visible_data=False,
            has_permission_denied=False,
        ),
    )

    response = analysis_api._report_interpretation_preflight(request, _user(), _FakeSession())
    body = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert "当前没有可解读的数据" in body
    assert "没有查看权限" not in body


def test_report_interpretation_does_not_resolve_chat_time_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """报表解读沿用可见图表上下文，不解析综合分析聊天的时间策略。"""
    datasource = analysis_api.CoreDatasource(
        id=1,
        name="测试项目",
        type="postgresql",
        type_name="PostgreSQL",
        configuration="{}",
    )

    async def _no_rate_limit(*_args, **_kwargs):
        return None

    async def _fake_create_llm(*_args, **_kwargs):
        return object(), SimpleNamespace(model_id=7, model_name="test-model")

    async def _unexpected_time_policy(**_kwargs):
        raise AssertionError("报表解读不得解析综合分析聊天时间策略")

    monkeypatch.setattr(
        analysis_api,
        "_report_interpretation_preflight",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(analysis_api, "_tenant_rate_limit_response", _no_rate_limit)
    monkeypatch.setattr(
        analysis_api,
        "_get_report_interpretation_datasource",
        lambda *_args, **_kwargs: datasource,
    )
    monkeypatch.setattr(
        analysis_api,
        "_collect_data_skill_context",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        analysis_api,
        "_collect_tracking_context",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(analysis_api, "_create_llm", _fake_create_llm)
    monkeypatch.setattr(
        analysis_api,
        "_stream_report_interpretation",
        lambda *_args, **_kwargs: iter(()),
    )
    monkeypatch.setattr(
        analysis_api,
        "_resolve_chat_time_policy",
        _unexpected_time_policy,
    )
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        context="当前可见图表数据：收入 12.5",
        messages=[
            analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")
        ],
    )

    response = asyncio.run(
        analysis_api.report_interpretation(request, _user(), _FakeSession())
    )

    assert response.media_type == "text/event-stream"


def test_collect_data_skill_context_passes_full_current_user(monkeypatch) -> None:
    current_user = _user()
    captured = {}

    def find_data_skills(*args, **kwargs):
        captured.update(kwargs)
        return "skill context", [], None

    monkeypatch.setattr(analysis_api, "find_data_skills", find_data_skills)

    result = analysis_api._collect_data_skill_context(
        _FakeSession(),
        datasource_id=1,
        data_skill_id=None,
        current_user=current_user,
        question="今天按小时收入",
    )

    assert result == "skill context"
    assert captured["current_user"] is current_user


def _mock_time_safe_chat_runtime(
    monkeypatch: pytest.MonkeyPatch,
    queries: list[object],
) -> analysis_api.AnalysisAssistantRequest:
    datasource = analysis_api.CoreDatasource(
        id=1,
        name="测试项目",
        type="postgresql",
        type_name="PostgreSQL",
        configuration="{}",
    )

    class _BusinessContext(SimpleNamespace):
        def snapshot_metadata(self):
            return {
                "context_hash": "ctx",
                "datasource_id": "1",
                "sql_dialect": "postgres",
                "allowed_tables": ["fact_orders"],
            }

    business_context = _BusinessContext(
        datasource=datasource,
        schema=(
            "【Schema】\n# Table: fact_orders\n[\n"
            "(business_date:date, 业务日期),\n"
            "(amount:numeric, 金额)\n]"
        ),
        allowed_tables=["fact_orders"],
        data_skill="",
        tracking_config="",
        business_context_hash="ctx",
        sql_dialect="postgres",
    )

    class _Llm:
        def stream(self, _messages):
            yield SimpleNamespace(content="已完成")

    async def _no_rate_limit(*_args, **_kwargs):
        return None

    async def _fake_create_llm(*_args, **_kwargs):
        return _Llm(), SimpleNamespace(model_id=7, model_name="test-model")

    async def _fake_resolve_time_policy(**_kwargs):
        return _resolved_time()

    monkeypatch.setattr(
        analysis_api,
        "_sanitize_analysis_request_context_for_current_permissions",
        lambda _session, _user, request: request,
    )
    monkeypatch.setattr(analysis_api, "_tenant_rate_limit_response", _no_rate_limit)
    monkeypatch.setattr(
        analysis_api,
        "_get_datasource",
        lambda *_args, **_kwargs: datasource,
    )
    monkeypatch.setattr(
        analysis_api,
        "_collect_custom_agent_context",
        lambda *_args, **_kwargs: ("", None),
    )
    monkeypatch.setattr(
        analysis_api.BusinessSqlContextService,
        "build",
        staticmethod(lambda **_kwargs: business_context),
    )
    monkeypatch.setattr(analysis_api, "_create_llm", _fake_create_llm)
    monkeypatch.setattr(
        analysis_api,
        "_resolve_chat_time_policy",
        _fake_resolve_time_policy,
    )
    monkeypatch.setattr(
        analysis_api,
        "build_agent_context_snapshot",
        lambda **_kwargs: {"snapshot": "ok"},
    )
    monkeypatch.setattr(
        analysis_api,
        "_build_plan",
        lambda *_args, **_kwargs: {"intro": "测试分析", "queries": queries},
    )
    monkeypatch.setattr(
        analysis_api,
        "_semantic_validation_error",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        analysis_api,
        "_build_chart_config",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        analysis_api,
        "_summarise_block",
        lambda *_args, **_kwargs: "数据块摘要",
    )
    monkeypatch.setattr(
        analysis_api,
        "record_tenant_usage_detached",
        lambda **_kwargs: None,
    )
    return analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[
            analysis_api.AnalysisAssistantMessage(role="user", content="分析收入")
        ],
    )


def test_chat_time_policy_failure_is_non_blocking_for_other_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _mock_time_safe_chat_runtime(
        monkeypatch,
        [
            {"id": "q1", "title": "无界角度", "sql": "SELECT unsafe"},
            {"id": "q2", "title": "安全角度", "sql": "SELECT safe"},
        ],
    )
    execute_calls: list[str] = []

    def fake_prepare_time_safe_query_sql(**kwargs):
        if kwargs["raw_query"]["id"] == "q1":
            raise analysis_api.AnalysisTimeSqlError()
        return "SELECT bounded"

    def fake_execute(**kwargs):
        execute_calls.append(kwargs["sql"])
        return SimpleNamespace(
            result={"fields": ["amount"], "data": [{"amount": 10}]}
        )

    monkeypatch.setattr(
        analysis_api,
        "_prepare_time_safe_query_sql",
        fake_prepare_time_safe_query_sql,
    )
    monkeypatch.setattr(
        analysis_api,
        "execute_user_analysis_query_or_raise",
        fake_execute,
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))
    payload = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert '"type":"block"' in payload
    assert '"status":"failed"' in payload
    assert '"error_type":"time_policy_unresolved"' in payload
    assert '"type":"final"' in payload
    assert '"type":"finish"' in payload
    assert execute_calls == ["SELECT bounded"]


def test_chat_all_time_policy_failures_finish_without_executing_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _mock_time_safe_chat_runtime(
        monkeypatch,
        [
            {"id": "q1", "title": "角度一", "sql": "SELECT unsafe_one"},
            {"id": "q2", "title": "角度二", "sql": "SELECT unsafe_two"},
        ],
    )
    monkeypatch.setattr(
        analysis_api,
        "_prepare_time_safe_query_sql",
        lambda **_kwargs: (_ for _ in ()).throw(
            analysis_api.AnalysisTimeSqlError()
        ),
    )
    monkeypatch.setattr(
        analysis_api,
        "execute_user_analysis_query_or_raise",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("时间策略失败时不得调用 SQL 执行器")
        ),
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))
    payload = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert payload.count('"error_type":"time_policy_unresolved"') == 2
    assert '"type":"final"' in payload
    assert '"type":"finish"' in payload
    assert '"type":"error"' not in payload


@pytest.mark.parametrize("repair_trigger", ["database", "semantic"])
def test_chat_repaired_sql_is_time_enforced_before_retry_execution(
    monkeypatch: pytest.MonkeyPatch,
    repair_trigger: str,
) -> None:
    request = _mock_time_safe_chat_runtime(
        monkeypatch,
        [
            {
                "id": "q1",
                "title": "收入趋势",
                "sql": (
                    "SELECT amount FROM fact_orders "
                    "WHERE business_date >= DATE '2026-07-13' "
                    "AND business_date <= DATE '2026-07-26'"
                ),
                "time_fields": [
                    {"table": "fact_orders", "field": "business_date"}
                ],
            }
        ],
    )
    execute_calls: list[str] = []
    repair_calls: list[str] = []
    semantic_calls = 0

    monkeypatch.setattr(
        analysis_api,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"fact_orders"}),
    )

    def fake_repair(*_args, **_kwargs):
        repair_calls.append("repair")
        return "SELECT amount FROM fact_orders"

    def fake_execute(**kwargs):
        execute_calls.append(kwargs["sql"])
        if repair_trigger == "database" and len(execute_calls) == 1:
            raise RuntimeError("database error")
        return SimpleNamespace(
            result={"fields": ["amount"], "data": [{"amount": 10}]}
        )

    def fake_semantic_validation(*_args, **_kwargs):
        nonlocal semantic_calls
        semantic_calls += 1
        if repair_trigger == "semantic" and semantic_calls == 1:
            return "semantic mismatch"
        return None

    monkeypatch.setattr(analysis_api, "_repair_sql", fake_repair)
    monkeypatch.setattr(
        analysis_api,
        "execute_user_analysis_query_or_raise",
        fake_execute,
    )
    monkeypatch.setattr(
        analysis_api,
        "_semantic_validation_error",
        fake_semantic_validation,
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))
    payload = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert repair_calls == ["repair"]
    assert len(execute_calls) == 2
    assert all("2026-07-13" in sql and "2026-07-26" in sql for sql in execute_calls)
    assert '"status":"failed"' not in payload
    assert '"type":"finish"' in payload


def test_chat_second_plan_parse_failure_returns_safe_final_and_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_build_plan = analysis_api._build_plan
    request = _mock_time_safe_chat_runtime(monkeypatch, [])
    invalid_outputs = iter(
        ["sensitive first malformed output", "sensitive second malformed output"]
    )
    usage_calls: list[dict] = []
    monkeypatch.setattr(analysis_api, "_build_plan", real_build_plan)
    monkeypatch.setattr(
        analysis_api,
        "_llm_text",
        lambda *_args, **_kwargs: next(invalid_outputs),
    )
    monkeypatch.setattr(
        analysis_api,
        "record_tenant_usage_detached",
        lambda **kwargs: usage_calls.append(kwargs),
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))
    payload = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert "无法生成可执行分析计划" in payload
    assert "未形成有数据支撑的结论" in payload
    assert "sensitive" not in payload
    assert '"type":"final"' in payload
    assert '"type":"finish"' in payload
    assert '"type":"error"' not in payload
    assert usage_calls[-1]["success_count"] == 1
    assert usage_calls[-1]["failure_count"] == 0


def test_chat_all_invalid_queries_returns_safe_final_without_calling_final_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _mock_time_safe_chat_runtime(
        monkeypatch,
        ["invalid", 7, None],
    )
    usage_calls: list[dict] = []
    monkeypatch.setattr(
        analysis_api,
        "record_tenant_usage_detached",
        lambda **kwargs: usage_calls.append(kwargs),
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))
    payload = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert "无法生成可执行分析计划" in payload
    assert "未形成有数据支撑的结论" in payload
    assert '"type":"final","content":"已完成"' not in payload
    assert '"type":"block"' not in payload
    assert '"type":"final"' in payload
    assert '"type":"finish"' in payload
    assert '"type":"error"' not in payload
    assert usage_calls[-1]["success_count"] == 1
    assert usage_calls[-1]["failure_count"] == 0


def test_chat_mixed_queries_skips_invalid_items_and_executes_valid_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _mock_time_safe_chat_runtime(
        monkeypatch,
        [
            "invalid",
            {"id": "q2", "title": "安全角度", "sql": "SELECT safe"},
            None,
        ],
    )
    execute_calls: list[str] = []
    monkeypatch.setattr(
        analysis_api,
        "_prepare_time_safe_query_sql",
        lambda **_kwargs: "SELECT bounded",
    )
    monkeypatch.setattr(
        analysis_api,
        "execute_user_analysis_query_or_raise",
        lambda **kwargs: execute_calls.append(kwargs["sql"])
        or SimpleNamespace(
            result={"fields": ["amount"], "data": [{"amount": 10}]}
        ),
    )

    response = asyncio.run(analysis_api.chat(request, _user(), _FakeSession()))
    payload = b"".join(asyncio.run(_collect_stream_body(response))).decode()

    assert execute_calls == ["SELECT bounded"]
    assert payload.count('"type":"block"') == 1
    assert '"type":"final"' in payload
    assert '"type":"finish"' in payload
    assert '"type":"error"' not in payload


async def _collect_stream_body(response) -> list[bytes]:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, str):
            chunks.append(chunk.encode())
        else:
            chunks.append(chunk)
    return chunks
