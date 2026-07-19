# ROI 看板工作空间隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用自动化回归测试固化 ROI 看板、图表和查询数据源的工作空间隔离，同时明确多个工作空间可以合法配置同一个 ROI 数据源。

**Architecture:** 保持现有 `tenant_id` 隔离和 `core_roi_workspace_config` 单一权威配置，不增加数据迁移或数据源唯一占用规则。后端测试覆盖共享数据源与不同数据源两类工作空间组合，前端测试覆盖工作空间切换后的状态清理和迟到响应失效；仅当测试暴露缺口时修改对应生产路径。

**Tech Stack:** Python 3、FastAPI、SQLModel、pytest、Vue 3、Pinia、Node.js `assert`、esbuild

## Global Constraints

- ROI 看板和图表必须按认证工作空间 `tenant_id` 隔离。
- SaaS 工作空间表单的 `roi_datasource_id` 是 ROI 数据源唯一权威配置。
- 同一个 ROI 数据源可以被多个工作空间配置，不增加 `datasource_id` 唯一约束。
- ROI 图表执行不得使用客户端 `datasource_id`、普通绑定数据源或前端当前数据源作为回退。
- 不删除、迁移或自动纠正现有 ROI 配置、看板和图表。
- 生产代码不得硬编码数据源名称、工作空间名称或 ROI 业务字段。

---

## File Structure

- `backend/tests/test_roi_dashboard_service.py`：覆盖 ROI 看板和图表资产的工作空间隔离，包括共享同一 ROI 数据源的场景。
- `backend/tests/test_roi_dashboard_query_executor.py`：覆盖查询执行器按当前工作空间配置选择 ROI 数据源。
- `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`：约束工作空间切换时重置 ROI 树状态，并校验列表请求工作空间身份。
- `frontend/src/stores/roiRequestCoordinator.test.mjs`：约束切换后旧代次请求不能发布状态。
- `backend/apps/roi_dashboard/service.py`、`backend/apps/roi_dashboard/query_executor.py`、`frontend/src/views/dashboard/common/ResourceTree.vue`、`frontend/src/stores/roiRequestCoordinator.ts`：仅在对应新增测试失败并证明生产实现存在缺口时修改。

### Task 1: 固化共享 ROI 数据源下的看板资产隔离

**Files:**
- Modify: `backend/tests/test_roi_dashboard_service.py:233`
- Verify: `backend/apps/roi_dashboard/service.py:397-505`

**Interfaces:**
- Consumes: `create_roi_dashboard(session, current_user, request) -> CoreRoiDashboard`
- Consumes: `list_roi_dashboards(session, current_user) -> list[CoreRoiDashboard]`
- Produces: 回归契约“同一 datasource_id 可供多个 tenant 使用，但列表只返回当前 tenant 的看板”

- [ ] **Step 1: 增加双工作空间共享数据源回归测试**

在 `test_roi_dashboards_are_shared_within_workspace` 后加入：

```python
def test_shared_roi_datasource_does_not_share_dashboards_between_workspaces(
    session: Session,
) -> None:
    workspace_a = make_user(id=1, tenant_id=11, tenant_role="owner")
    workspace_b = make_user(id=2, tenant_id=22, tenant_role="owner")
    add_datasource(session, 101)
    grant_datasource(session, user_id=1, datasource_id=101)
    grant_datasource(session, user_id=2, datasource_id=101)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    seed_roi_config(session, tenant_id=22, datasource_id=101)

    dashboard_a = create_roi_dashboard(
        session, workspace_a, RoiDashboardCreate(name="空间 A ROI")
    )
    dashboard_b = create_roi_dashboard(
        session, workspace_b, RoiDashboardCreate(name="空间 B ROI")
    )

    assert [item.id for item in list_roi_dashboards(session, workspace_a)] == [dashboard_a.id]
    assert [item.id for item in list_roi_dashboards(session, workspace_b)] == [dashboard_b.id]
```

- [ ] **Step 2: 运行聚焦测试并判断是否存在生产缺口**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_service.py -k "shared_roi_datasource or dashboards_are_shared_within_workspace or cross_tenant_dashboard" -q
```

Expected: 新测试和相邻隔离测试全部通过。若新测试失败，失败必须来自列表或创建链路未带 `tenant_id`；此时只修复 `service.py` 对应查询，不改变共享数据源规则。

- [ ] **Step 3: 提交后端资产隔离测试**

```powershell
git add backend/tests/test_roi_dashboard_service.py backend/apps/roi_dashboard/service.py
git diff --cached --check
git commit -m "测试：固化 ROI 看板工作空间隔离"
```

### Task 2: 固化查询执行按工作空间 ROI 配置选源

**Files:**
- Modify: `backend/tests/test_roi_dashboard_query_executor.py:52-71`
- Verify: `backend/apps/roi_dashboard/query_executor.py:272-350`

**Interfaces:**
- Consumes: `execute_roi_read_query(session, current_user, sql, ...) -> RoiQueryResult`
- Produces: 回归契约“查询执行器只读取 current_user.tenant_id 对应的配置”

- [ ] **Step 1: 让测试配置辅助函数支持同一会话多个工作空间**

将 `seed_roi_config` 中固定 ID 改为工作空间派生 ID：

```python
        CoreRoiWorkspaceConfig(
            id=1000 + tenant_id,
```

- [ ] **Step 2: 增加两个工作空间分别选择数据源的测试**

在 `_prepare_authorized_query` 后加入：

```python
def test_query_executor_uses_current_workspace_roi_datasource(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_roi_config(session, tenant_id=11, datasource_id=202)
    seed_roi_config(session, tenant_id=22, datasource_id=303)
    datasources = {
        202: SimpleNamespace(id=202, type="pg", configuration="{}"),
        303: SimpleNamespace(id=303, type="pg", configuration="{}"),
    }
    selected: list[int] = []
    monkeypatch.setattr(query_executor, "has_roi_datasource_access", lambda *_args: True)
    monkeypatch.setattr(session, "get", lambda _model, datasource_id: datasources[datasource_id])

    def run_validated_read(*, datasource, **_kwargs):
        selected.append(int(datasource.id))
        return {"columns": ["value"], "data": [[datasource.id]]}

    monkeypatch.setattr(query_executor, "_run_validated_read", run_validated_read)

    result_a = execute_roi_read_query(session, make_user(tenant_id=11), "SELECT 1")
    result_b = execute_roi_read_query(session, make_user(tenant_id=22), "SELECT 1")

    assert selected == [202, 303]
    assert result_a.data == [{"value": 202}]
    assert result_b.data == [{"value": 303}]
```

- [ ] **Step 3: 运行查询执行器测试**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_query_executor.py -q
```

Expected: 全部通过。若新增测试失败，只修复 `_load_active_roi_config` 或 `execute_roi_read_query` 的工作空间配置读取，不接受请求参数数据源。

- [ ] **Step 4: 提交查询选源回归测试**

```powershell
git add backend/tests/test_roi_dashboard_query_executor.py backend/apps/roi_dashboard/query_executor.py
git diff --cached --check
git commit -m "测试：固化 ROI 查询按工作空间选源"
```

### Task 3: 固化前端工作空间切换和迟到响应防护

**Files:**
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs:34-38`
- Modify: `frontend/src/stores/roiRequestCoordinator.test.mjs:52-58`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.vue:404-415,561-566,1088-1101`
- Verify: `frontend/src/stores/roiRequestCoordinator.ts:38-63,87-92`

**Interfaces:**
- Consumes: `resetTreeState() -> void`
- Consumes: `resetRoiRequests(state) -> void`
- Produces: 回归契约“切换空间后旧树请求和旧 Pinia 请求均不能发布”

- [ ] **Step 1: 加强资源树源代码契约测试**

在现有 `resetTreeState` 断言后加入：

```javascript
const workspaceSwitchHandler = source.match(
  /name: WORKSPACE_CONTEXT_CHANGE_EVENT,[\s\S]*?callback: \(event\?: any\) => \{([\s\S]*?)\n  \},\n\}\)/
)
assert.ok(workspaceSwitchHandler, '必须监听工作空间切换事件')
assert.match(workspaceSwitchHandler[1], /resetTreeState\(\)/)
assert.ok(
  workspaceSwitchHandler[1].indexOf('resetTreeState()') <
    workspaceSwitchHandler[1].indexOf("event?.phase === 'changing'"),
  '切换开始时必须先清空旧 ROI 树状态'
)
assert.match(source, /const requestTenantId = userStore\.getTenantId \|\| 'default'/)
assert.match(source, /\(userStore\.getTenantId \|\| 'default'\) === requestTenantId/)
```

- [ ] **Step 2: 加强请求代次测试**

在现有 `resetRoiRequests(state)` 场景中加入一个新代次请求，证明旧响应不能覆盖新空间：

```javascript
const nextWorkspaceRequest = beginRoiRequest(state, 'dashboards')
assert.equal(isLatestRoiRequest(state, oldRequest), false)
assert.equal(isLatestRoiRequest(state, nextWorkspaceRequest), true)
finishRoiRequest(state, nextWorkspaceRequest)
```

- [ ] **Step 3: 运行前端聚焦测试**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
node src/stores/roiRequestCoordinator.test.mjs
```

Expected:

```text
ROI request coordinator tests passed
```

两个命令退出码均为 `0`。若资源树测试失败，只修复工作空间切换重置顺序或请求工作空间身份校验。

- [ ] **Step 4: 提交前端切换隔离测试**

```powershell
git add frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs frontend/src/stores/roiRequestCoordinator.test.mjs frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/stores/roiRequestCoordinator.ts
git diff --cached --check
git commit -m "测试：固化 ROI 工作空间切换隔离"
```

### Task 4: 全量验证与交付检查

**Files:**
- Verify: `backend/apps/roi_dashboard/`
- Verify: `backend/tests/test_roi_dashboard_service.py`
- Verify: `backend/tests/test_roi_dashboard_query_executor.py`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.vue`
- Verify: `frontend/src/stores/roiRequestCoordinator.ts`

**Interfaces:**
- Consumes: Tasks 1-3 的全部回归契约
- Produces: 可交付的验证证据和无意外业务数据变更的确认

- [ ] **Step 1: 运行 ROI 后端回归套件**

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_service.py tests/test_roi_dashboard_query_executor.py tests/test_roi_dashboard_api.py tests/test_roi_dashboard_permissions.py -q
```

Expected: 全部通过，`0 failed`。

- [ ] **Step 2: 运行 ROI 前端回归套件**

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
node src/stores/roiRequestCoordinator.test.mjs
node src/views/dashboard/roi/RoiDashboardPanel.test.mjs
```

Expected: 三个命令退出码均为 `0`。

- [ ] **Step 3: 检查差异和数据库无写入**

```powershell
Set-Location ..
git diff --check
git status --short
git diff --stat HEAD~3..HEAD
```

Expected: 只包含计划内测试文件及测试暴露缺口后必要的生产文件；不包含迁移、种子或业务数据写入脚本。

- [ ] **Step 4: 汇总交付结果**

报告以下证据：

```text
- 同一 ROI 数据源可被两个工作空间配置
- 两个工作空间只能读取各自 ROI 看板和图表
- 查询执行按当前工作空间 ROI 配置选择数据源
- 切换工作空间后旧请求不能发布
- 未删除或迁移现有 ROI 业务数据
```
