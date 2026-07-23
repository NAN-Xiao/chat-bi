# ROI 看板单入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将每个工作空间的 ROI 功能改为一个不可展开的固定入口，并把历史多看板图表完整归并到唯一内部看板记录。

**Architecture:** 保留 `CoreRoiDashboard` 作为 ROI 图表的内部聚合根，通过部分唯一索引和幂等 `current/ensure` 服务形成工作空间单例。前端不再把内部记录映射为树节点或路由参数，而是在 ROI 页面内解析唯一记录并继续复用现有按看板 ID 的图表 API。

**Tech Stack:** FastAPI、SQLModel/SQLAlchemy、Alembic、PostgreSQL、Vue 3、Pinia、TypeScript、Element Plus、Node `assert`/esbuild、pytest。

## Global Constraints

- 左侧只显示一个名称固定为“ROI 看板”的不可展开节点，不显示 ROI 子项。
- 每个工作空间最多存在一条 `deleted = false AND status = 1` 的 ROI 看板记录。
- 历史图表按原看板 `sort/create_time/id` 和图表 `sort/create_time/id` 的稳定顺序归并。
- 不修改 ROI 数据源绑定、权限、SQL 执行、只读校验和数据库方言规则。
- 不影响普通推荐看板和“我的看板”的树结构、路由或编辑能力。
- 旧多看板写接口必须明确拒绝，不能静默创建、替换或删除固定看板。
- 代码注释、提交信息和新增文档使用中文。

---

## 文件结构

- `backend/alembic/versions/148_roi_dashboard_singleton.py`：归并历史 ROI 看板并建立活动记录唯一索引。
- `backend/apps/roi_dashboard/models.py`：声明与迁移一致的 SQLAlchemy 部分唯一索引。
- `backend/apps/roi_dashboard/service.py`：提供单例读取、幂等确保和旧多看板操作拒绝逻辑。
- `backend/apps/roi_dashboard/api.py`：暴露 `GET /current`、`POST /ensure`，保留旧路由但返回明确错误。
- `backend/tests/test_roi_dashboard_singleton_migration.py`：验证迁移版本、SQL 顺序、稳定归并和索引定义。
- `backend/tests/test_roi_dashboard_service.py`：验证单例、并发冲突恢复、权限和图表 ID 边界。
- `backend/tests/test_roi_dashboard_api.py`：验证新接口契约及旧接口禁用状态。
- `frontend/src/api/roiDashboard.ts`：提供单例读取/确保 API，移除 UI 对多看板写 API 的依赖。
- `frontend/src/stores/roiDashboard.ts`：将 `dashboards` 数组收敛为 `dashboard` 单例状态。
- `frontend/src/views/dashboard/roi/roiDashboardPanelBehavior.ts`：定义单例页面加载和首次新增图表流程。
- `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`：不再接收路由看板 ID，不再弹出新建子看板名称框。
- `frontend/src/views/dashboard/common/ResourceTree.vue`：构造固定 ROI 虚拟叶子入口并移除子树管理行为。
- `frontend/src/views/dashboard/roi/roiNavigationBehavior.ts`：简化固定入口点击与 ROI 空路由行为。
- `frontend/src/views/dashboard/preview/SQPreviewShow.vue`：ROI 页面不再把 `resourceId` 传给 Panel。
- 现有 ROI 前端测试：同步覆盖固定入口、单例状态和无 `resourceId` 路由。

---

### Task 1: 历史归并迁移与数据库单例约束

**Files:**
- Create: `backend/alembic/versions/148_roi_dashboard_singleton.py`
- Modify: `backend/apps/roi_dashboard/models.py`
- Create: `backend/tests/test_roi_dashboard_singleton_migration.py`
- Modify: `backend/tests/test_roi_dashboard_migration.py`

**Interfaces:**
- Consumes: `core_roi_dashboard`、`core_roi_dashboard_chart` 现有列和迁移头 `147refreshsqlgroupingskill`。
- Produces: 唯一索引 `uq_core_roi_dashboard_active_tenant`；常量 `ROI_DASHBOARD_NAME = "ROI 看板"`；迁移 revision `148roisingleton`。

- [ ] **Step 1: 写迁移失败测试**

新增测试加载 `148_roi_dashboard_singleton.py`，断言：

```python
def test_roi_singleton_migration_contract() -> None:
    module = load_migration("148_roi_dashboard_singleton.py")
    assert module.revision == "148roisingleton"
    assert module.down_revision == "147refreshsqlgroupingskill"
    assert module.ROI_DASHBOARD_NAME == "ROI 看板"
    assert module.ACTIVE_UNIQUE_INDEX == "uq_core_roi_dashboard_active_tenant"
```

通过 monkeypatch 捕获 `op.execute` 和 `op.create_index`，断言归并执行顺序为：选择主记录并固定名称、重挂图表并连续排序、停用冗余看板、最后创建部分唯一索引；索引条件必须是 `deleted = false AND status = 1`。

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_singleton_migration.py -q`

Expected: FAIL，提示 `148_roi_dashboard_singleton.py` 不存在。

- [ ] **Step 3: 实现归并迁移**

迁移使用 PostgreSQL CTE 和窗口函数，核心排序表达式固定为：

```sql
ROW_NUMBER() OVER (
  PARTITION BY d.tenant_id
  ORDER BY d.sort, d.create_time, d.id
)
```

有效图表重排固定为：

```sql
ROW_NUMBER() OVER (
  PARTITION BY d.tenant_id
  ORDER BY d.sort, d.create_time, d.id,
           c.sort, c.create_time, c.id
) - 1
```

按以下顺序执行：更新主记录名称和 `sort=0`；把活动图表重挂主记录并连续排序；把其余图表同步重挂主记录但保留删除/停用状态；将冗余看板设置 `deleted=true,status=0`；创建唯一索引。`downgrade()` 仅删除索引，不尝试拆分已经归并的数据，并在迁移注释中明确该数据归并不可逆。

在 `CoreRoiDashboard.__table_args__` 中声明同名索引：

```python
Index(
    "uq_core_roi_dashboard_active_tenant",
    "tenant_id",
    unique=True,
    postgresql_where=text("deleted = false AND status = 1"),
)
```

- [ ] **Step 4: 运行迁移与模型测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_singleton_migration.py backend/tests/test_roi_dashboard_migration.py -q`

Expected: PASS；迁移版本、SQL 顺序和模型索引全部匹配。

- [ ] **Step 5: 提交数据库单例约束**

```powershell
git add backend/alembic/versions/148_roi_dashboard_singleton.py backend/apps/roi_dashboard/models.py backend/tests/test_roi_dashboard_singleton_migration.py backend/tests/test_roi_dashboard_migration.py
git commit -m "迁移：归并 ROI 看板并增加单例约束"
```

---

### Task 2: 后端单例服务与接口契约

**Files:**
- Modify: `backend/apps/roi_dashboard/service.py`
- Modify: `backend/apps/roi_dashboard/api.py`
- Modify: `backend/tests/test_roi_dashboard_service.py`
- Modify: `backend/tests/test_roi_dashboard_api.py`

**Interfaces:**
- Consumes: `uq_core_roi_dashboard_active_tenant`、现有 `_active_dashboard_statement()`、`_require_roi_mutation_access()`、`RoiDashboardResponse`。
- Produces: `get_current_roi_dashboard(session, current_user) -> CoreRoiDashboard | None`；`ensure_current_roi_dashboard(session, current_user) -> CoreRoiDashboard`；`GET /dashboard/roi/current`；`POST /dashboard/roi/ensure`。

- [ ] **Step 1: 写单例服务失败测试**

在 `test_roi_dashboard_service.py` 增加以下行为测试：

```python
def test_get_current_roi_dashboard_returns_none_for_empty_workspace(session, owner):
    assert get_current_roi_dashboard(session, owner) is None

def test_ensure_current_roi_dashboard_is_idempotent(session, owner, roi_config):
    first = ensure_current_roi_dashboard(session, owner)
    second = ensure_current_roi_dashboard(session, owner)
    assert first.id == second.id
    assert first.name == "ROI 看板"
```

再覆盖：没有 ROI 配置返回 `409`；无管理员权限返回 `403`；模拟 `IntegrityError` 后回滚并重新读取并发创建结果；旧 create/update/delete/reorder 服务返回 `405`；图表接口传入同租户非当前活动 ID 返回 `404`。

- [ ] **Step 2: 写 API 契约失败测试**

在 `test_roi_dashboard_api.py` 断言路由：

```python
assert methods["/dashboard/roi/current"] == {"GET"}
assert methods["/dashboard/roi/ensure"] == {"POST"}
```

测试 `current` 允许返回 `null`，`ensure` 返回 `RoiDashboardResponse`，旧 `POST /dashboard/roi`、`PATCH/DELETE /{dashboard_id}` 和 `POST /reorder` 返回 `405` 及固定中文错误信息“ROI 看板为固定单例，不支持该操作”。

- [ ] **Step 3: 运行后端测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_service.py backend/tests/test_roi_dashboard_api.py -q`

Expected: FAIL，提示单例函数和路由尚未定义。

- [ ] **Step 4: 实现单例服务**

在 `service.py` 增加：

```python
ROI_DASHBOARD_NAME = "ROI 看板"
ROI_SINGLETON_OPERATION_MESSAGE = "ROI 看板为固定单例，不支持该操作"

def get_current_roi_dashboard(session, current_user):
    tenant_id = _tenant_id(current_user)
    return session.exec(
        _active_dashboard_statement(tenant_id).order_by(CoreRoiDashboard.id.asc())
    ).first()
```

`ensure_current_roi_dashboard()` 必须先校验管理权限和 ROI 数据源配置，再读取已有记录；不存在时创建固定名称记录并提交。捕获唯一索引引起的 `IntegrityError` 后执行 `rollback()`，重新读取同一工作空间的当前记录；仅在仍不存在时重新抛出异常。

`list_roi_dashboards()` 返回 `[]` 或 `[current]`。旧四个多看板写服务入口统一抛出 `HTTPException(status_code=405, detail=ROI_SINGLETON_OPERATION_MESSAGE)`。所有图表读写继续通过 `_load_dashboard_or_404()` 验证当前唯一活动记录，不自动替换错误 ID。

- [ ] **Step 5: 暴露 current/ensure API**

在参数化 `/{dashboard_id}` 路由之前增加：

```python
@router.get("/current", response_model=RoiDashboardResponse | None)
def get_current_roi_dashboard_api(...):
    return get_current_roi_dashboard(session, current_user)

@router.post("/ensure", response_model=RoiDashboardResponse)
def ensure_current_roi_dashboard_api(...):
    return ensure_current_roi_dashboard(session, current_user)
```

保留旧路由以返回明确 `405`，避免客户端得到含糊的路由缺失结果。

- [ ] **Step 6: 运行后端 ROI 回归测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_service.py backend/tests/test_roi_dashboard_api.py backend/tests/test_roi_dashboard_permissions.py backend/tests/test_roi_dashboard_query_executor.py -q`

Expected: PASS；单例、权限、图表读写和 SQL 执行测试全部通过。

- [ ] **Step 7: 提交后端单例接口**

```powershell
git add backend/apps/roi_dashboard/service.py backend/apps/roi_dashboard/api.py backend/tests/test_roi_dashboard_service.py backend/tests/test_roi_dashboard_api.py
git commit -m "功能：提供 ROI 看板单例接口"
```

---

### Task 3: 前端单例状态与首次图表流程

**Files:**
- Modify: `frontend/src/api/roiDashboard.ts`
- Modify: `frontend/src/stores/roiDashboard.ts`
- Modify: `frontend/src/stores/roiDashboard.behavior.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/roiDashboardPanelBehavior.ts`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

**Interfaces:**
- Consumes: `GET /dashboard/roi/current`、`POST /dashboard/roi/ensure`、现有按内部看板 ID 的图表 API。
- Produces: `roiDashboardApi.getCurrent()`、`roiDashboardApi.ensure()`、store action `loadDashboard()`、`ensureDashboard()`；`runRoiEnsureChartFlow(dependencies) -> Promise<RoiDashboard | null>`；Panel 自主解析内部单例 ID。

- [ ] **Step 1: 写 API/store 失败测试**

更新 store 测试桩并断言：`loadDashboard()` 将 `null` 或唯一对象写入 `store.dashboard`；过期请求不能覆盖新工作空间状态；`ensureDashboard()` 发布返回记录；`reset()` 清空单例和图表缓存。删除对 `dashboards` 数组和 `createDashboardRequestId` 的断言。

- [ ] **Step 2: 写页面行为失败测试**

将加载计划改为不接收路由看板 ID：

```typescript
assert.deepEqual(
  buildRoiPanelLoadPlan({ reason: 'mounted', routeMode: 'roi' }),
  ['config', 'dashboard']
)
```

新增 `runRoiEnsureChartFlow()` 测试：配置缺失或无编辑权限时不调用 ensure；已有单例时直接打开新增图表编辑器；无单例时调用 ensure、发布单例、以返回 ID 打开首图编辑器；整个流程不请求名称、不修改路由。

- [ ] **Step 3: 运行前端状态和 Panel 测试确认失败**

Run: `node src/stores/roiDashboard.behavior.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Workdir: `frontend`

Expected: FAIL，提示 `getCurrent/ensure` 和新行为函数不存在。

- [ ] **Step 4: 实现 API 和 Pinia 单例状态**

将前端 API 收敛为：

```typescript
getCurrent: (config) => request.get<RoiDashboard | null>('/dashboard/roi/current', config),
ensure: (config) => request.post<RoiDashboard>('/dashboard/roi/ensure', undefined, config),
```

保留图表 API，移除 UI 使用的 `create/update/remove/reorder` 多看板方法。store 使用 `dashboard: RoiDashboard | null`，实现 `loadDashboard()` 和 `ensureDashboard()`，并继续使用请求代次协调器防止工作空间切换后的旧响应回写。

- [ ] **Step 5: 改造 Panel 加载与新增图表**

移除 `dashboardId` prop、名称输入框、`createDashboard()` 和树刷新事件。页面加载顺序为配置与当前单例并行读取，单例存在时再加载图表；`currentCharts` 使用 `dashboard.value?.id` 取缓存。

“添加图表”按钮调用 `runRoiEnsureChartFlow()`：先确保配置可编辑，再复用已有单例或调用 `store.ensureDashboard()`，最后用内部 ID 创建 `RoiChartEditorState`。编辑、删除、刷新和排序均从 `dashboard.value.id` 获取内部 ID，空单例时保持禁用或由新增流程创建。

- [ ] **Step 6: 运行前端单例状态测试**

Run: `node src/stores/roiDashboard.behavior.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Workdir: `frontend`

Expected: PASS；无名称弹窗、无路由变更、首次确保和现有图表操作均通过。

- [ ] **Step 7: 提交前端单例页面状态**

```powershell
git add frontend/src/api/roiDashboard.ts frontend/src/stores/roiDashboard.ts frontend/src/stores/roiDashboard.behavior.test.mjs frontend/src/views/dashboard/roi/roiDashboardPanelBehavior.ts frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs
git commit -m "重构：ROI 页面改用固定单例状态"
```

---

### Task 4: 固定导航入口与无 ID 路由

**Files:**
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/roiNavigationBehavior.ts`
- Modify: `frontend/src/views/dashboard/roi/roiNavigationBehavior.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs`

**Interfaces:**
- Consumes: `RoiDashboardPanel` 无 ID props、固定路由 `/dashboard/index?dashboardMode=roi`。
- Produces: 固定虚拟叶子 `ROI_GROUP_ID`，名称“ROI 看板”，`dashboard_scope='roi'`，无 `children`、无节点菜单。

- [ ] **Step 1: 写固定入口失败测试**

更新 `ResourceTree.roi.test.mjs`，断言组合树直接追加如下结构，不再调用 `normalizeRoiDashboardNodes()`：

```typescript
{
  id: ROI_GROUP_ID,
  pid: DEFAULT_GROUP_ID,
  name: t('dashboard.roi_dashboard'),
  leaf: true,
  node_type: 'leaf',
  virtual: true,
  dashboard_scope: ROI_SCOPE,
  children: [],
}
```

断言 `hasNodeMenu()` 对该节点返回 `false`，源码不再包含 `newRoiDashboard`、`renameRoiDashboard`、`deleteRoiDashboard`、`normalizeRoiDashboardNodes` 或 ROI 看板列表请求；专用展开图标规则必须隐藏箭头，而不是保留可见箭头。

- [ ] **Step 2: 写无 ID 路由失败测试**

在导航行为与预览测试中断言：点击固定 ROI 入口只生成 `dashboardMode=roi`；删除 `resourceId/dashboardId`；不再自动选择第一条 ROI 子看板；`SQPreviewShow` 渲染 `<RoiDashboardPanel>` 时不传 `dashboard-id`。

- [ ] **Step 3: 运行导航测试确认失败**

Run: `node src/views/dashboard/common/ResourceTree.roi.test.mjs`

Run: `node src/views/dashboard/roi/roiNavigationBehavior.test.mjs`

Run: `node src/views/dashboard/preview/SQPreviewShow.roi.test.mjs`

Workdir: `frontend`

Expected: FAIL，当前实现仍构造 ROI 子树并依赖 `resourceId`。

- [ ] **Step 4: 实现固定虚拟叶子节点**

在 `ResourceTree.vue` 用 `createRoiDashboardEntry()` 代替 ROI 分组和真实子节点映射。点击该节点时清理普通看板选择、设置固定节点为当前选中项，并调用 `syncEmptyRoiRoute()`；不发出需要真实资源 ID 的普通节点事件。

删除 ROI 子看板查找、首次子项选择、树刷新事件、上下文菜单和操作分支。ROI 节点排除拖放，Element Plus 展开图标通过仅命中固定入口的样式隐藏且不破坏与普通叶子节点的文字对齐。

- [ ] **Step 5: 简化预览路由**

删除 ROI 空路由“等待子分支/选择第一子看板”的逻辑。`SQPreviewShow.vue` 在授权且 `dashboardMode=roi` 时直接渲染无 props 的 `RoiDashboardPanel`；路由监听不得把 ROI 无 `resourceId` 状态回退到普通看板。

- [ ] **Step 6: 运行导航和页面测试**

Run: `node src/views/dashboard/common/ResourceTree.roi.test.mjs`

Run: `node src/views/dashboard/roi/roiNavigationBehavior.test.mjs`

Run: `node src/views/dashboard/preview/SQPreviewShow.roi.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Workdir: `frontend`

Expected: PASS；固定节点无子项、无菜单、无路由 ID，普通看板断言保持通过。

- [ ] **Step 7: 提交固定导航入口**

```powershell
git add frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs frontend/src/views/dashboard/roi/roiNavigationBehavior.ts frontend/src/views/dashboard/roi/roiNavigationBehavior.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs
git commit -m "功能：ROI 看板改为固定单入口"
```

---

### Task 5: 全量回归与浏览器验收

**Files:**
- Modify only if verification exposes a defect in the files already listed above.

**Interfaces:**
- Consumes: Tasks 1-4 的迁移、API、store、Panel 和固定导航入口。
- Produces: 后端 ROI 测试、前端 ROI 测试、生产构建及桌面/移动视口验收证据。

- [ ] **Step 1: 运行后端 ROI 完整测试集**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_migration.py backend/tests/test_roi_dashboard_singleton_migration.py backend/tests/test_roi_dashboard_service.py backend/tests/test_roi_dashboard_api.py backend/tests/test_roi_dashboard_permissions.py backend/tests/test_roi_dashboard_query_executor.py backend/tests/test_repair_flam_roi_dashboard.py -q`

Expected: PASS，无失败或未处理警告。

- [ ] **Step 2: 运行前端 ROI 完整测试集**

Run: `Get-ChildItem src -Recurse -Filter '*roi*.test.mjs' | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }`

Run: `node src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs`

Run: `node src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs`

Workdir: `frontend`

Expected: PASS，ROI 和相邻普通树行为均无回归。

- [ ] **Step 3: 运行生产构建**

Run: `npm run build`

Workdir: `frontend`

Expected: exit code 0；TypeScript、Vue 模板和打包通过。

- [ ] **Step 4: 验证迁移链但不修改共享数据库**

Run: `backend\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini heads`

Expected: 唯一 head 为 `148roisingleton`。本步骤不对 `10.1.5.28` 执行 `upgrade`；实际部署前按仓库备份流程备份并由发布流程应用迁移。

- [ ] **Step 5: 重启本地四服务并检查运行态**

按 `starting-chat-bi-local` Skill 执行本地重启，确认前端 `5173`、API `8000`、MCP `8001` 和一个隔离队列 Worker；核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

Expected: 前端返回 `200`，API 登录方法返回 `200` 或 `401`，三个端口监听，Worker 使用同一 `local-*` 队列。

- [ ] **Step 6: 浏览器验收**

使用 `browser:control-in-app-browser` 在桌面和移动视口验证：左侧仅有一个“ROI 看板”节点且没有展开箭头；点击后 URL 只有 `dashboardMode=roi`；历史图表正常展示；新增图表不弹出看板名称；普通推荐看板和“我的看板”仍可正常切换。

Expected: 页面无重叠、无空白渲染、控制台无新增错误；截图记录固定入口和 ROI 页面。

- [ ] **Step 7: 检查最终差异**

Run: `git diff --check`

Run: `git status --short`

Expected: 无空白错误；只包含本计划文件和 ROI 单入口相关源文件/测试，不包含日志、运行时文件或用户无关改动。

- [ ] **Step 8: 提交验证阶段修复（仅在确有修复时）**

```powershell
git add backend/alembic/versions/148_roi_dashboard_singleton.py backend/apps/roi_dashboard/models.py backend/apps/roi_dashboard/service.py backend/apps/roi_dashboard/api.py backend/tests/test_roi_dashboard_singleton_migration.py backend/tests/test_roi_dashboard_migration.py backend/tests/test_roi_dashboard_service.py backend/tests/test_roi_dashboard_api.py frontend/src/api/roiDashboard.ts frontend/src/stores/roiDashboard.ts frontend/src/stores/roiDashboard.behavior.test.mjs frontend/src/views/dashboard/roi/roiDashboardPanelBehavior.ts frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs frontend/src/views/dashboard/roi/roiNavigationBehavior.ts frontend/src/views/dashboard/roi/roiNavigationBehavior.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs
git commit -m "修复：完善 ROI 单入口回归问题"
```

若验证未产生新改动，则不创建空提交。
