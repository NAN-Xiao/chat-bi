# 图表抽屉数据源权限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复报表解读把 ROI 图表抽屉数据源误判为无权限的问题。

**Architecture:** 保持 `resolve_chart_execution_datasource` 为普通绑定数据源与 ROI 执行数据源的唯一受控解析入口。修改 `validate_dashboard_report_target`：先验证组件属于看板，再从服务端保存的图表配置解析每张图表的执行数据源；显式抽屉值优先，缺失时回退看板有效数据源。客户端传入的 `datasource_id` 仅为接口兼容保留，不参与授权。

**Tech Stack:** Python 3、FastAPI、SQLModel、pytest。

## Global Constraints

- 不得把看板默认数据源的权限当作图表抽屉数据源的权限。
- 不修改工作空间数据源绑定、已有看板记录、前端接口负载或图表 SQL。
- 图表加载与刷新已有抽屉数据源支持，本次只运行回归测试锁定该行为。
- 新增测试说明、代码注释和提交信息均使用中文。

---

### Task 1: 为解读目标的数据源选择建立红灯测试

**Files:**
- Modify: `backend/tests/test_dashboard_execution_datasource.py`

**Interfaces:**
- Consumes: `dashboard_service.validate_dashboard_report_target(session, current_user, dashboard_id, datasource_id, component_ids)`。
- Produces: 证明授权来源为服务端保存的图表抽屉数据源的两个测试。

- [ ] **Step 1: 添加看板夹具和显式 ROI 数据源优先测试**

```python
def _report_target_dashboard(*, view_datasource: int | None) -> SimpleNamespace:
    return SimpleNamespace(
        id="dashboard-1", tenant_id=2001, datasource=11,
        component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
        canvas_view_info=json.dumps({"chart-1": {"datasource": view_datasource}}),
    )

def test_report_target_uses_saved_roi_drawer_datasource(monkeypatch: pytest.MonkeyPatch) -> None:
    resolved_ids: list[int | None] = []
    record = _report_target_dashboard(view_datasource=22)
    monkeypatch.setattr(dashboard_service, "_load_dashboard_or_404", lambda *_args: record)
    monkeypatch.setattr(dashboard_service, "_can_view_dashboard_resource", lambda *_args: True)
    monkeypatch.setattr(
        dashboard_service, "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_ids.append(datasource_id) or 22,
    )
    dashboard_service.validate_dashboard_report_target(_Session(), _user(), "dashboard-1", 11, ["chart-1"])
    assert resolved_ids == [22]
```

- [ ] **Step 2: 添加无抽屉值时回退看板数据源测试**

```python
def test_report_target_falls_back_to_dashboard_datasource_without_drawer_value(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_ids: list[int | None] = []
    record = _report_target_dashboard(view_datasource=None)
    monkeypatch.setattr(dashboard_service, "_load_dashboard_or_404", lambda *_args: record)
    monkeypatch.setattr(dashboard_service, "_can_view_dashboard_resource", lambda *_args: True)
    monkeypatch.setattr(
        dashboard_service, "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_ids.append(datasource_id) or 11,
    )
    dashboard_service.validate_dashboard_report_target(_Session(), _user(), "dashboard-1", 22, ["chart-1"])
    assert resolved_ids == [11]
```

- [ ] **Step 3: 运行测试并确认红灯原因正确**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_dashboard_execution_datasource.py -k "report_target" -q`

Expected: 2 failed。当前代码使用客户端数据源并要求它与看板数据源一致，因此不会调用抽屉的 `22`，也不会在空抽屉值时回退到 `11`。

- [ ] **Step 4: 提交红灯测试**

Run: `git add -- backend/tests/test_dashboard_execution_datasource.py`

Run: `git commit -m "测试：覆盖报表解读抽屉数据源校验"`

### Task 2: 按图表抽屉配置校验报表解读目标

**Files:**
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:1079`
- Test: `backend/tests/test_dashboard_execution_datasource.py`

**Interfaces:**
- Consumes: `_load_dashboard_or_404`、`_can_view_dashboard_resource`、`_collect_canvas_view_component_ids`、`_parse_canvas_view_info`、`_chart_datasource`、`_effective_dashboard_datasource`、`resolve_chart_execution_datasource`。
- Produces: 保持现有函数签名的 `validate_dashboard_report_target`，但改为逐图表校验服务端保存的执行数据源。

- [ ] **Step 1: 删除客户端数据源与看板数据源相等的检查**

删除以下逻辑，保留 `datasource_id` 参数并在函数体内标记为接口兼容入参：

```python
requested_datasource = _normalize_datasource_id(datasource_id)
dashboard_datasource = _normalize_datasource_id(record.datasource)
if requested_datasource is None or (
    dashboard_datasource is not None and requested_datasource != dashboard_datasource
):
    raise HTTPException(status_code=403, detail=DASHBOARD_CHART_NO_PERMISSION_MESSAGE)
_ensure_datasource_access(session, current_user, requested_datasource, required=True)
```

- [ ] **Step 2: 替换组件循环的权限比较**

```python
canvas_view_info = _parse_canvas_view_info(record.canvas_view_info)
fallback_datasource = _effective_dashboard_datasource(record)
for component_id in requested_component_ids:
    view_info = canvas_view_info.get(component_id)
    if not isinstance(view_info, dict):
        raise HTTPException(status_code=403, detail=DASHBOARD_CHART_NO_PERMISSION_MESSAGE)
    try:
        chart_datasource = _chart_datasource(record, view_info, fallback_datasource)
        resolve_chart_execution_datasource(session, current_user, chart_datasource)
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            raise HTTPException(status_code=403, detail=DASHBOARD_CHART_NO_PERMISSION_MESSAGE) from exc
        raise
```

- [ ] **Step 3: 运行红灯测试并确认转绿**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_dashboard_execution_datasource.py -k "report_target" -q`

Expected: 2 passed。

- [ ] **Step 4: 验证图表加载和刷新未回退**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_dashboard_execution_datasource.py -q`

Expected: 0 failures，包含 `test_dashboard_refresh_uses_saved_roi_chart_datasource`。

- [ ] **Step 5: 提交最小实现**

Run: `git add -- backend/apps/dashboard/crud/dashboard_service.py backend/tests/test_dashboard_execution_datasource.py`

Run: `git commit -m "修复：报表解读使用图表抽屉数据源校验"`

### Task 3: 固定分析助手入口与最终验证

**Files:**
- Modify: `backend/tests/test_analysis_assistant_permissions.py`
- Verify: `backend/tests/test_dashboard_execution_datasource.py`
- Verify: `backend/tests/test_dashboard_permission_cache.py`

**Interfaces:**
- Consumes: `analysis_api._report_interpretation_preflight` 和服务层 `validate_dashboard_report_target`。
- Produces: 目标校验失败时入口仍只返回 `permission_denied` 流，且全量相关测试通过。

- [ ] **Step 1: 添加统一权限失败流测试**

```python
def test_report_interpretation_preflight_maps_target_validation_failure_to_permission_denied(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_api, "validate_dashboard_report_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPException(status_code=403)),
    )
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=11,
        context="旧图表数据：收入 12.5",
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="解读这个图")],
        report_target=analysis_api.ReportInterpretationTarget(
            dashboard_id="dashboard-1", component_ids=["chart-1"],
            has_visible_data=True, has_permission_denied=False,
        ),
    )
    response = analysis_api._report_interpretation_preflight(request, _user(), _FakeSession())
    body = b"".join(asyncio.run(_collect_stream_body(response))).decode()
    assert "permission_denied" in body
    assert "没有查看权限" in body
```

- [ ] **Step 2: 运行入口测试与分析助手权限测试集**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_analysis_assistant_permissions.py -k "preflight_maps_target_validation_failure" -q`

Expected: 1 passed。

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_analysis_assistant_permissions.py -q`

Expected: 0 failures。

- [ ] **Step 3: 提交入口回归测试**

Run: `git add -- backend/tests/test_analysis_assistant_permissions.py`

Run: `git commit -m "测试：固定报表解读权限失败语义"`

- [ ] **Step 4: 运行最终相关测试组合**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_dashboard_execution_datasource.py backend/tests/test_analysis_assistant_permissions.py backend/tests/test_dashboard_permission_cache.py -q`

Expected: 0 failures。

- [ ] **Step 5: 检查静态变更和工作区状态**

Run: `git diff f6275f6d..HEAD --check`

Expected: 无输出，退出码 0。

Run: `git status --short; git log --oneline -5`

Expected: 不存在未提交的业务代码或测试文件；提交历史包含红灯测试、最小实现和入口回归测试。
