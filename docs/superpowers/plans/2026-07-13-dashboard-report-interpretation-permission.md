# 看板报表解读权限判定实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让有权查看看板且当前存在可见数据的普通用户能够使用报表解读，同时继续拒绝无权资源、权限失败图表和旧客户端快照。

**Architecture:** 前端为实时看板解读请求附带结构化目标信息，包括看板 ID、当前包含的图表组件 ID、是否存在可见数据和是否存在权限失败结果。后端复用看板服务的资源、租户、数据源和组件归属校验；只有目标通过校验且有可见数据时，才允许现有可见上下文进入报表解读模型。

**Tech Stack:** Vue 3、TypeScript、FastAPI、Pydantic、SQLModel、pytest、Node.js 测试脚本。

## Global Constraints

- 只调整实时看板和图表解读入口，不放宽分析助手历史、导出和通用上下文权限策略。
- AI 只接收当前可见字段、当前可见行、当前筛选分组和当前激活页签数据。
- 资源无权、数据源不匹配、组件不属于看板或图表权限失败时统一返回“没有查看权限”。
- 合法目标没有可见数据时返回“当前没有可解读的数据”，不调用 AI。
- 不自动替换数据源、看板、图表或字段。

---

### Task 1: 后端实时解读目标鉴权

**Files:**
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py`
- Test: `backend/tests/test_analysis_assistant_permissions.py`

**Interfaces:**
- Consumes: `CoreDashboard.component_data`、`_can_view_dashboard_resource(...)`、`has_datasource_access(...)`。
- Produces: `validate_dashboard_report_target(session, current_user, dashboard_id, datasource_id, component_ids) -> None`、`ReportInterpretationTarget`、`AnalysisAssistantRequest.report_target`。

- [ ] **Step 1: 为允许实时可见数据补充失败测试**

在 `backend/tests/test_analysis_assistant_permissions.py` 中构造带 `report_target` 的请求，模拟普通用户命中数据权限但看板、数据源和组件校验通过，并把 `_create_llm` 替换为可观察桩；断言请求不会走 `_permission_denied_stream_response`。

- [ ] **Step 2: 为权限失败、空数据和目标不匹配补充失败测试**

分别断言：`has_permission_denied=True` 返回 `permission_denied`；`has_visible_data=False` 返回“当前没有可解读的数据”且不创建 LLM；看板或组件校验失败返回 `permission_denied`。

- [ ] **Step 3: 运行新增测试并确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_assistant_permissions.py -q`

Expected: 新增实时目标用例失败，因为请求模型和校验函数尚不存在。

- [ ] **Step 4: 在看板服务实现目标资源校验**

实现 `validate_dashboard_report_target(...)`：加载看板，调用 `_can_view_dashboard_resource`，核对看板数据源与请求数据源，调用 `_ensure_datasource_access`，递归收集 `SQView` 组件 ID，并要求提交的组件 ID 非空且全部属于当前看板；任何不匹配统一抛出 403。

- [ ] **Step 5: 在报表解读接口实现三态判定**

新增结构化 `ReportInterpretationTarget`，并在 `report_interpretation(...)` 中依次处理权限失败、资源校验、空数据和可见数据。带合法结构化目标时不再因 `has_applicable_permissions=True` 被整体拒绝；未带结构化目标的旧调用继续沿用原有保守拦截。

- [ ] **Step 6: 运行后端权限测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_assistant_permissions.py backend/tests/test_dashboard_permission_cache.py -q`

Expected: 全部通过，历史、导出和旧上下文测试没有回归。

### Task 2: 前端构建实时解读目标状态

**Files:**
- Create: `frontend/src/views/dashboard/preview/reportInterpretationTarget.ts`
- Create: `frontend/src/views/dashboard/preview/reportInterpretationTarget.test.mjs`
- Modify: `frontend/src/api/analysisAssistant.ts`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewHead.vue`

**Interfaces:**
- Consumes: 当前报表条目的 `component.id`、`viewInfo.status`、`viewInfo.error_type`、运行时快照 `data` 和持久化结果 `viewInfo.data.data`。
- Produces: `buildReportInterpretationTarget(dashboardId, entries, snapshots) -> ReportInterpretationTarget`，并通过 `analysisAssistantApi.reportInterpretation(..., reportTarget, controller)` 提交。

- [ ] **Step 1: 编写目标状态构建器测试**

测试以下输入：当前快照有行时 `has_visible_data=True`；当前快照为空时不能回退旧行；任一条目为 `permission_denied` 时 `has_permission_denied=True`；组件 ID 去重且空 ID 被忽略。

- [ ] **Step 2: 运行前端目标测试并确认失败**

Run: `cd frontend; node src/views/dashboard/preview/reportInterpretationTarget.test.mjs`

Expected: 失败，因为 `reportInterpretationTarget.ts` 尚不存在。

- [ ] **Step 3: 实现目标状态构建器**

构建器优先读取运行时快照；只要快照包含 `data` 数组，即使为空也不得回退 `viewInfo.data.data`。权限失败状态优先于旧成功数据，输出看板 ID、组件 ID、可见数据状态和权限失败状态。

- [ ] **Step 4: 扩展前端 API 类型与请求体**

新增 `ReportInterpretationTarget` 类型，并让 `reportInterpretation` 把 `report_target` 放入请求体。保持其他分析助手 API 参数不变。

- [ ] **Step 5: 接入单图表、Tab 和整张看板解读**

两个预览组件都使用当前已收集的条目和运行时快照生成目标状态；把 `dashboardInfo.id` 和实际包含的 `SQView` 组件 ID 传给后端。上下文仍由现有 `buildReportContext` / `buildDashboardReportContext` 生成。

- [ ] **Step 6: 运行前端单元测试和类型检查**

Run: `cd frontend; node src/views/dashboard/preview/reportInterpretationTarget.test.mjs; node src/views/dashboard/preview/reportPromptHistory.test.mjs; npx vue-tsc -b`

Expected: 两个 Node 测试脚本输出通过，`vue-tsc` 退出码为 0。

### Task 3: 回归验证

**Files:**
- Verify: `backend/apps/analysis_assistant/api/analysis_assistant.py`
- Verify: `backend/apps/dashboard/crud/dashboard_service.py`
- Verify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`
- Verify: `frontend/src/views/dashboard/preview/SQPreviewHead.vue`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的完整请求契约。
- Produces: 可交付的权限判定修复及验证证据。

- [ ] **Step 1: 运行后端相关测试集**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_assistant_permissions.py backend/tests/test_dashboard_permission_cache.py backend/tests/test_dashboard_service.py -q`

Expected: 全部通过。

- [ ] **Step 2: 运行前端构建**

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b` 与 Vite 构建均成功。

- [ ] **Step 3: 检查变更范围**

Run: `git diff --check` 和 `git status --short`

Expected: 没有空白错误；只包含本计划涉及文件以及用户原有未提交改动。
