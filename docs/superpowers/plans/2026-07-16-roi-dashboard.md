# ROI 专用看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增仅空间拥有者和管理员可见、工作空间共享、使用统一账号授权数据源、拥有专用图表表和独立 SQL 编辑器的 ROI 看板。

**Architecture:** 后端新增独立 `apps/roi_dashboard` 模块、三张数据表和 `/dashboard/roi` API；ROI 查询通过专用账号级数据源授权和只读执行入口，明确跳过普通看板的结果行数、平台表权限和平台字段权限。前端在现有资源树中聚合第三个虚拟分组，但 ROI 页面、状态、响应式网格和 SQL 编辑器均独立，不读写普通看板画布或 `DashboardSqlEditor.vue`。

**Tech Stack:** FastAPI、SQLModel、Alembic、PostgreSQL、pytest、Vue 3、Pinia、TypeScript、Element Plus、现有 SQView 图表渲染组件、Node 源码回归测试。

## Global Constraints

- 左侧树固定按“推荐看板、ROI 看板、我的看板”纵向排列。
- ROI 入口和全部 API 仅允许当前工作空间角色 `owner`、`admin`；`member` 返回 `403`。
- ROI 配置、下属看板和图表按 `tenant_id` 共享，不按创建人过滤。
- 每个工作空间只有一个 ROI 数据源配置，所有下属看板和图表继承该数据源。
- ROI 数据源候选来自当前账号有权使用的数据源，不受当前工作空间单绑定数据源限制。
- 其他管理员没有统一数据源权限时仍能看到结构，但不能执行、预览、添加、编辑或删除图表。
- 任一活动 ROI 图表存在时禁止更换统一数据源；空下属看板不阻止更换。
- ROI 不使用 `CoreDashboard`、`CoreDashboardTree`、`component_data`、`canvas_view_info` 或普通自由画布。
- ROI 使用专用 SQL 编辑器；不得导入或修改 `DashboardSqlEditor.vue`，不得读写普通看板 Pinia 状态。
- ROI 编辑器首期支持 SQL、预览、图表类型、字段映射、表格列、透视、洞察、标题和 `layout_span`，不支持 MCP 数据来源。
- ROI SQL 保留账号级数据源访问、单条只读 SQL 和超时校验；不应用结果行数限制、平台表权限、平台字段权限或行权限改写。
- 数据源连接账号自身数据库权限仍然生效。
- 普通看板继续保留原有工作空间绑定、结果行数、表权限、字段权限和编辑器行为。
- 所有新增代码注释、错误信息、提交信息使用中文。

---

## File Structure

### Backend

- Create `backend/apps/roi_dashboard/__init__.py`: ROI 模块包入口。
- Create `backend/apps/roi_dashboard/models.py`: 三张 ROI SQLModel 表。
- Create `backend/apps/roi_dashboard/schemas.py`: 配置、看板、图表和排序请求/响应 DTO。
- Create `backend/apps/roi_dashboard/permissions.py`: 工作空间角色和账号级数据源授权。
- Create `backend/apps/roi_dashboard/query_executor.py`: ROI 单条只读 SQL 执行和结果规范化。
- Create `backend/apps/roi_dashboard/service.py`: 配置、看板、图表 CRUD、共享范围、乐观锁和缓存失效。
- Create `backend/apps/roi_dashboard/api.py`: `/dashboard/roi` 路由。
- Create `backend/alembic/versions/145_roi_dashboard.py`: ROI 三表迁移。
- Modify `backend/apps/api.py`: 注册 ROI router。
- Test `backend/tests/test_roi_dashboard_migration.py`: 迁移结构和版本链。
- Test `backend/tests/test_roi_dashboard_permissions.py`: 角色、跨工作空间和账号级数据源授权。
- Test `backend/tests/test_roi_dashboard_service.py`: 配置、看板、图表、版本、软删除和排序。
- Test `backend/tests/test_roi_dashboard_query_executor.py`: 只读、超时以及跳过表/字段/行/结果限制。
- Test `backend/tests/test_roi_dashboard_api.py`: 路由、请求协议和依赖。

### Frontend

- Create `frontend/src/api/roiDashboard.ts`: 独立 ROI API 客户端。
- Create `frontend/src/stores/roiDashboard.ts`: 独立 ROI 配置、看板、图表和编辑状态。
- Create `frontend/src/views/dashboard/roi/types.ts`: ROI DTO 与编辑器类型。
- Create `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`: ROI 右侧主页面。
- Create `frontend/src/views/dashboard/roi/RoiDatasourceDialog.vue`: 统一数据源设置弹窗。
- Create `frontend/src/views/dashboard/roi/RoiChartGrid.vue`: 固定响应式网格。
- Create `frontend/src/views/dashboard/roi/RoiChartCard.vue`: 图表渲染与权限错误状态。
- Create `frontend/src/views/dashboard/roi/RoiSqlEditor.vue`: 独立 ROI SQL 编辑器。
- Create `frontend/src/views/dashboard/roi/roiChartConfig.ts`: ROI 图表配置序列化、反序列化和校验纯函数。
- Modify `frontend/src/views/dashboard/common/ResourceTree.vue`: 聚合 ROI 虚拟分组、专用菜单和路由。
- Modify `frontend/src/views/dashboard/preview/SQPreviewShow.vue`: `dashboardMode=roi` 时分流到 `RoiDashboardPanel`，并阻止普通画布加载。
- Modify `frontend/src/i18n/zh-CN.json`, `zh-TW.json`, `en.json`, `ko-KR.json`: ROI 文案。
- Test `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`: 可见性、顺序、路由和新建流程。
- Test `frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs`: 内容分流和普通画布隔离。
- Test `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`: 配置、新建和首次编辑流程。
- Test `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs`: 响应式跨度和排序。
- Test `frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs`: 独立编辑器边界。
- Test `frontend/src/views/dashboard/roi/roiChartConfig.test.mjs`: 图表配置往返与校验。

---

### Task 1: 建立 ROI 数据表与 DTO

**Files:**
- Create: `backend/apps/roi_dashboard/__init__.py`
- Create: `backend/apps/roi_dashboard/models.py`
- Create: `backend/apps/roi_dashboard/schemas.py`
- Create: `backend/alembic/versions/145_roi_dashboard.py`
- Test: `backend/tests/test_roi_dashboard_migration.py`

**Interfaces:**
- Produces: `CoreRoiWorkspaceConfig`, `CoreRoiDashboard`, `CoreRoiDashboardChart`。
- Produces: `RoiConfigUpdate`, `RoiDashboardCreate`, `RoiDashboardUpdate`, `RoiChartPreviewRequest`, `RoiChartCreate`, `RoiChartUpdate`, `RoiDashboardReorderRequest`, `RoiChartReorderRequest`。
- Uses 64 位 Snowflake ID；API DTO 将 ID 序列化为字符串，避免前端精度损失。

- [ ] **Step 1: 写迁移失败测试**

```python
def test_roi_dashboard_migration_definition() -> None:
    module = load_migration("145_roi_dashboard.py")
    assert module.revision == "145roidashboard"
    assert module.down_revision == "144dashboardname"
    assert set(module.TABLE_NAMES) == {
        "core_roi_workspace_config",
        "core_roi_dashboard",
        "core_roi_dashboard_chart",
    }
    assert module.ROI_LAYOUT_SPANS == ("full", "half", "third")
```

- [ ] **Step 2: 运行迁移测试并确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_migration.py -q`

Expected: FAIL，提示 `145_roi_dashboard.py` 不存在。

- [ ] **Step 3: 创建 SQLModel 表和 DTO**

`models.py` 使用以下精确字段合同：

```python
class CoreRoiWorkspaceConfig(SnowflakeBase, table=True):
    __tablename__ = "core_roi_workspace_config"
    tenant_id: int
    datasource_id: int
    version: int = 1
    create_by: int | None = None
    update_by: int | None = None
    create_time: int
    update_time: int
    deleted: bool = False

class CoreRoiDashboard(SnowflakeBase, table=True):
    __tablename__ = "core_roi_dashboard"
    tenant_id: int
    name: str
    sort: int = 0
    status: int = 1
    version: int = 1
    create_by: int | None = None
    update_by: int | None = None
    create_time: int
    update_time: int
    deleted: bool = False

class CoreRoiDashboardChart(SnowflakeBase, table=True):
    __tablename__ = "core_roi_dashboard_chart"
    tenant_id: int
    roi_dashboard_id: int
    title: str
    sql: str
    chart_type: str
    chart_config: dict
    layout_span: str = "full"
    sort: int = 0
    status: int = 1
    version: int = 1
    create_by: int | None = None
    update_by: int | None = None
    create_time: int
    update_time: int
    deleted: bool = False
```

迁移必须建立：活动配置 `tenant_id` 唯一索引、三个表的 `tenant_id` 索引、图表的 `(tenant_id, roi_dashboard_id, status, sort)` 索引、下属看板的 `(tenant_id, status, sort)` 索引，以及 `layout_span IN ('full','half','third')` 检查约束。

- [ ] **Step 4: 运行模型与迁移测试并确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_migration.py -q`

Expected: PASS。

- [ ] **Step 5: 校验 Alembic 单一 head**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from alembic.config import Config; from alembic.script import ScriptDirectory; c=Config(); c.set_main_option('script_location','alembic'); print(ScriptDirectory.from_config(c).get_heads())"
```

Expected: `['145roidashboard']`。

- [ ] **Step 6: 提交数据库任务**

```powershell
git add backend/apps/roi_dashboard/__init__.py backend/apps/roi_dashboard/models.py backend/apps/roi_dashboard/schemas.py backend/alembic/versions/145_roi_dashboard.py backend/tests/test_roi_dashboard_migration.py
git commit -m "功能：新增 ROI 看板数据模型"
```

### Task 2: 实现工作空间角色与账号级数据源授权

**Files:**
- Create: `backend/apps/roi_dashboard/permissions.py`
- Test: `backend/tests/test_roi_dashboard_permissions.py`

**Interfaces:**
- Produces: `require_roi_workspace_admin(current_user) -> AccessContext`。
- Produces: `list_account_datasource_ids_without_tenant_filter(session, user_id) -> set[int]`。
- Produces: `list_roi_accessible_datasource_ids(session, current_user) -> set[int]`。
- Produces: `has_roi_datasource_access(session, current_user, datasource_id) -> bool`。
- Consumes: `resolve_access_context`, `CoreDatasourceTenantBinding`, `CoreDatasourceUser`, `CoreDatasource`。

- [ ] **Step 1: 写角色和账号授权失败测试**

```python
def test_member_cannot_access_roi() -> None:
    user = make_user(tenant_id=11, tenant_role="member")
    with pytest.raises(HTTPException) as exc:
        require_roi_workspace_admin(user)
    assert exc.value.status_code == 403

def test_roi_datasources_union_workspace_and_direct_account_grants(session) -> None:
    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    bind_datasource(session, tenant_id=11, datasource_id=101)
    grant_datasource_user(session, user_id=7, datasource_id=202)
    assert list_roi_accessible_datasource_ids(session, user) == {101, 202}
```

- [ ] **Step 2: 运行权限测试并确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_permissions.py -q`

Expected: FAIL，提示 `apps.roi_dashboard.permissions` 不存在。

- [ ] **Step 3: 实现专用授权规则**

```python
def require_roi_workspace_admin(current_user: CurrentUser) -> AccessContext:
    context = resolve_access_context(current_user)
    if not context.has_workspace_context or context.tenant_role not in TENANT_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="仅空间拥有者和管理员可访问 ROI 看板")
    return context

def list_roi_accessible_datasource_ids(session: SessionDep, current_user: CurrentUser) -> set[int]:
    context = require_roi_workspace_admin(current_user)
    workspace_ids = set(list_bound_datasource_ids_for_tenant(session, context.management_tenant_id))
    direct_ids = set(list_account_datasource_ids_without_tenant_filter(session, int(current_user.id)))
    active_ids = set(session.exec(
        select(CoreDatasource.id).where(CoreDatasource.id.in_(workspace_ids | direct_ids))
    ).all())
    return {int(value) for value in active_ids}
```

`list_account_datasource_ids_without_tenant_filter` 必须只读取 `CoreDatasourceUser.user_id == current_user.id` 的直接授权，不把名称相似、历史工作空间或请求体 ID 当成授权。平台全局管理员不自动获得 ROI 工作空间入口。

- [ ] **Step 4: 运行权限测试并确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_permissions.py -q`

Expected: PASS。

- [ ] **Step 5: 提交权限任务**

```powershell
git add backend/apps/roi_dashboard/permissions.py backend/tests/test_roi_dashboard_permissions.py
git commit -m "功能：隔离 ROI 看板数据源授权"
```

### Task 3: 实现 ROI 配置和下属看板服务

**Files:**
- Create: `backend/apps/roi_dashboard/service.py`
- Test: `backend/tests/test_roi_dashboard_service.py`

**Interfaces:**
- Produces: `get_roi_config`, `set_roi_config`, `list_roi_dashboards`, `create_roi_dashboard`, `update_roi_dashboard`, `delete_roi_dashboard`, `reorder_roi_dashboards`。
- Consumes: Task 1 模型/DTO、Task 2 权限函数。
- All resource lookups require `tenant_id` from `require_roi_workspace_admin`.

- [ ] **Step 1: 写配置和共享范围失败测试**

```python
def test_roi_dashboards_are_shared_within_workspace(session) -> None:
    owner = make_user(id=1, tenant_id=11, tenant_role="owner")
    admin = make_user(id=2, tenant_id=11, tenant_role="admin")
    created = create_roi_dashboard(session, owner, RoiDashboardCreate(name="渠道 ROI"))
    assert [item.id for item in list_roi_dashboards(session, admin)] == [created.id]

def test_cannot_change_datasource_when_any_active_chart_exists(session) -> None:
    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301)
    with pytest.raises(HTTPException) as exc:
        set_roi_config(session, user, RoiConfigUpdate(datasource_id=202, version=1))
    assert exc.value.status_code == 409
```

- [ ] **Step 2: 运行服务测试并确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_service.py -q`

Expected: FAIL，提示服务函数不存在。

- [ ] **Step 3: 实现配置、共享 CRUD 和乐观锁**

关键查询必须使用以下约束：

```python
def _active_dashboard_statement(tenant_id: int):
    return select(CoreRoiDashboard).where(
        CoreRoiDashboard.tenant_id == tenant_id,
        CoreRoiDashboard.deleted.is_(False),
        CoreRoiDashboard.status == 1,
    )

def _load_dashboard_or_404(session, tenant_id: int, dashboard_id: int):
    record = session.exec(
        _active_dashboard_statement(tenant_id).where(CoreRoiDashboard.id == dashboard_id)
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="ROI 看板不存在")
    return record
```

`set_roi_config` 仅在数据源变化时统计当前 `tenant_id` 的活动图表；有图表返回 `409`。更新语句必须匹配请求 `version`，成功后 `version += 1`。删除下属看板在单事务内软删除看板和其活动图表。

- [ ] **Step 4: 运行服务测试并确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_service.py -q`

Expected: PASS。

- [ ] **Step 5: 提交配置与看板服务**

```powershell
git add backend/apps/roi_dashboard/service.py backend/tests/test_roi_dashboard_service.py
git commit -m "功能：实现 ROI 配置和共享看板服务"
```

### Task 4: 实现 ROI 独立只读执行与图表 CRUD

**Files:**
- Create: `backend/apps/roi_dashboard/query_executor.py`
- Modify: `backend/apps/roi_dashboard/service.py`
- Test: `backend/tests/test_roi_dashboard_query_executor.py`
- Test: `backend/tests/test_roi_dashboard_service.py`

**Interfaces:**
- Produces: `execute_roi_read_query(session, current_user, sql) -> RoiQueryResult`。
- Produces: `preview_roi_chart`, `list_roi_charts`, `create_roi_chart`, `update_roi_chart`, `delete_roi_chart`, `reorder_roi_charts`。
- Consumes: `has_roi_datasource_access`, `check_sql_read`, datasource query timeout, `_execute_after_validation` through one locally wrapped adapter.
- Does not call `execute_user_query` or `validate_user_query_sql_or_raise`, because both restore ordinary table/field permission behavior.

- [ ] **Step 1: 写执行边界失败测试**

```python
def test_roi_query_skips_platform_table_field_and_row_permissions(monkeypatch, session) -> None:
    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    seed_roi_config(session, tenant_id=11, datasource_id=202)
    monkeypatch.setattr(query_executor, "has_roi_datasource_access", lambda *_args: True)
    monkeypatch.setattr(query_executor, "check_sql_read", lambda *_args: (True, ""))
    monkeypatch.setattr(query_executor, "_run_validated_read", lambda **_kwargs: {"columns": ["secret"], "data": [[1]]})
    monkeypatch.setattr(query_executor, "validate_sql_scope", fail_if_called)
    monkeypatch.setattr(query_executor, "get_row_permission_filters", fail_if_called)
    result = execute_roi_read_query(session, user, "select secret from private_table")
    assert result.status == "success"
    assert result.data == [{"secret": 1}]

def test_roi_query_rejects_write_sql(session) -> None:
    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_admin(), "delete from orders")
    assert exc.value.status_code == 400
```

- [ ] **Step 2: 运行执行器测试并确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_query_executor.py -q`

Expected: FAIL，提示 `query_executor.py` 不存在。

- [ ] **Step 3: 实现专用执行器**

```python
def execute_roi_read_query(
    session: SessionDep,
    current_user: CurrentUser,
    sql: str,
) -> RoiQueryResult:
    context = require_roi_workspace_admin(current_user)
    config = load_active_roi_config(session, context.management_tenant_id)
    if not has_roi_datasource_access(session, current_user, config.datasource_id):
        raise HTTPException(status_code=403, detail="当前账号无此数据源权限")
    datasource = session.get(CoreDatasource, config.datasource_id)
    if datasource is None:
        raise HTTPException(status_code=409, detail="ROI 数据源不存在或已停用")
    is_safe, reason = check_sql_read(sql, datasource)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"ROI SQL 仅允许单条只读查询：{reason}")
    raw = _run_validated_read(
        datasource=datasource,
        sql=sql,
        query_timeout=settings.DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS,
    )
    return normalize_roi_query_result(raw)
```

`_run_validated_read` 只调用数据库执行层已经完成只读验证后的入口，不调用普通权限解析，不添加 `LIMIT`，不截断返回数据。记录 `tenant_id`、`user_id`、`datasource_id`、耗时、返回行数和响应体估算字节数，日志不记录凭据。

- [ ] **Step 4: 写图表 CRUD、版本和排序失败测试**

覆盖 `layout_span` 仅允许 `full|half|third`、预览成功后才能保存、更新版本冲突 `409`、跨工作空间图表 `404`、无数据源权限时结构可见但修改 `403`。

- [ ] **Step 5: 实现图表服务和独立缓存键**

缓存键函数使用精确合同：

```python
def roi_chart_cache_key(tenant_id, user_id, datasource_id, dashboard_id, chart_id, version, sql_hash):
    return user_redis_key(
        tenant_id,
        user_id,
        "roi-chart",
        datasource_id,
        dashboard_id,
        chart_id,
        version,
        sql_hash,
    )
```

图表新增、更新、删除、排序和 ROI 数据源配置变化后清理对应 `roi-chart` 命名空间。权限检查发生在缓存读取之前，权限失败不能命中旧缓存。

- [ ] **Step 6: 运行执行与服务测试并确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_query_executor.py tests/test_roi_dashboard_service.py -q`

Expected: PASS。

- [ ] **Step 7: 提交执行与图表任务**

```powershell
git add backend/apps/roi_dashboard/query_executor.py backend/apps/roi_dashboard/service.py backend/tests/test_roi_dashboard_query_executor.py backend/tests/test_roi_dashboard_service.py
git commit -m "功能：实现 ROI 图表和独立 SQL 执行"
```

### Task 5: 暴露独立 ROI API

**Files:**
- Create: `backend/apps/roi_dashboard/api.py`
- Modify: `backend/apps/api.py`
- Test: `backend/tests/test_roi_dashboard_api.py`

**Interfaces:**
- Produces the exact routes from the approved spec under `/dashboard/roi`.
- Router dependency: `require_chatbi_business_user`.
- Each service call still performs `owner|admin` and tenant checks; route registration alone is not authorization.

- [ ] **Step 1: 写路由失败测试**

```python
def test_roi_routes_are_registered_with_expected_methods() -> None:
    methods = route_method_map(roi_api.router)
    assert methods["/dashboard/roi/config"] == {"GET", "PUT"}
    assert methods["/dashboard/roi/list"] == {"GET"}
    assert methods["/dashboard/roi"] == {"POST"}
    assert methods["/dashboard/roi/{dashboard_id}/charts/preview"] == {"POST"}

def test_roi_chart_requests_do_not_accept_datasource_id() -> None:
    assert "datasource_id" not in RoiChartPreviewRequest.model_fields
    assert "datasource_id" not in RoiChartCreate.model_fields
    assert "datasource_id" not in RoiChartUpdate.model_fields
```

- [ ] **Step 2: 运行 API 测试并确认 RED**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_api.py -q`

Expected: FAIL，提示 router 不存在。

- [ ] **Step 3: 创建 router 并注册到 `backend/apps/api.py`**

```python
router = APIRouter(
    tags=["ROI Dashboard"],
    prefix="/dashboard/roi",
    dependencies=[Depends(require_chatbi_business_user)],
)

@router.get("/config", response_model=RoiConfigResponse)
def get_config_api(session: SessionDep, current_user: CurrentUser):
    return get_roi_config(session, current_user)

@router.post("/{dashboard_id}/charts/preview", response_model=RoiChartPreviewResponse)
def preview_chart_api(
    dashboard_id: int,
    request: RoiChartPreviewRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    return preview_roi_chart(session, current_user, dashboard_id, request)
```

端点映射固定为：`PUT /config → set_roi_config`、`GET /list → list_roi_dashboards`、`POST / → create_roi_dashboard`、`PATCH /{dashboard_id} → update_roi_dashboard`、`DELETE /{dashboard_id} → delete_roi_dashboard`、`POST /reorder → reorder_roi_dashboards`、`GET /{dashboard_id}/charts → list_roi_charts`、`POST /{dashboard_id}/charts → create_roi_chart`、`PUT /{dashboard_id}/charts/{chart_id} → update_roi_chart`、`DELETE /{dashboard_id}/charts/{chart_id} → delete_roi_chart`、`POST /{dashboard_id}/charts/reorder → reorder_roi_charts`。API 层不复制 tenant、角色或数据源判断。

- [ ] **Step 4: 运行 API 与服务测试并确认 GREEN**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_api.py tests/test_roi_dashboard_permissions.py tests/test_roi_dashboard_service.py tests/test_roi_dashboard_query_executor.py -q`

Expected: PASS。

- [ ] **Step 5: 提交 API 任务**

```powershell
git add backend/apps/roi_dashboard/api.py backend/apps/api.py backend/tests/test_roi_dashboard_api.py
git commit -m "功能：新增 ROI 看板接口"
```

### Task 6: 接入 ROI 树分组、路由和独立前端状态

**Files:**
- Create: `frontend/src/api/roiDashboard.ts`
- Create: `frontend/src/stores/roiDashboard.ts`
- Create: `frontend/src/views/dashboard/roi/types.ts`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue`
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`
- Test: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
- Test: `frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs`

**Interfaces:**
- Produces: `roiDashboardApi` with config/list/dashboard/chart methods.
- Produces: `useRoiDashboardStore` with `config`, `dashboards`, `charts`, `loading`, `permissionError`, `editorState`.
- Extends frontend `DashboardScope` to `'default' | 'roi' | 'my'` only in route/tree helpers; ROI data never enters ordinary dashboard store.

- [ ] **Step 1: 写树顺序、角色和内容分流失败测试**

```javascript
assert.match(source, /type DashboardScope = 'default' \| 'roi' \| 'my'/)
assert.match(source, /canManageCurrentWorkspace/)
assert.match(source, /buildCombinedTree\(defaultNodes, roiNodes, myNodes\)/)
assert.ok(source.indexOf('DEFAULT_GROUP_ID') < source.indexOf('ROI_GROUP_ID'))
assert.ok(source.indexOf('ROI_GROUP_ID') < source.indexOf('MY_GROUP_ID'))
assert.match(previewSource, /dashboardMode.*roi[\s\S]*RoiDashboardPanel/)
assert.match(previewSource, /if \(dashboardMode === ROI_SCOPE\)[\s\S]*return/)
```

- [ ] **Step 2: 运行前端接入测试并确认 RED**

Run:

```powershell
node frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs
```

Expected: 至少一个断言失败，提示 ROI scope/group/panel 不存在。

- [ ] **Step 3: 创建 API、类型和独立 store**

`roiDashboardApi` 不放入 `dashboardApi`：

```typescript
export const roiDashboardApi = {
  getConfig: () => request.get('/dashboard/roi/config'),
  updateConfig: (payload: RoiConfigUpdate) => request.put('/dashboard/roi/config', payload),
  list: () => request.get('/dashboard/roi/list'),
  create: (payload: RoiDashboardCreate) => request.post('/dashboard/roi', payload),
  update: (id: string, payload: RoiDashboardUpdate) => request.patch(`/dashboard/roi/${id}`, payload),
  remove: (id: string) => request.delete(`/dashboard/roi/${id}`),
  reorder: (payload: RoiDashboardReorderRequest) => request.post('/dashboard/roi/reorder', payload),
  listCharts: (id: string) => request.get(`/dashboard/roi/${id}/charts`),
  previewChart: (id: string, payload: RoiChartPreviewRequest) => request.post(`/dashboard/roi/${id}/charts/preview`, payload),
  createChart: (id: string, payload: RoiChartCreate) => request.post(`/dashboard/roi/${id}/charts`, payload),
  updateChart: (id: string, chartId: string, payload: RoiChartUpdate) => request.put(`/dashboard/roi/${id}/charts/${chartId}`, payload),
  removeChart: (id: string, chartId: string) => request.delete(`/dashboard/roi/${id}/charts/${chartId}`),
  reorderCharts: (id: string, payload: RoiChartReorderRequest) => request.post(`/dashboard/roi/${id}/charts/reorder`, payload),
}
```

- [ ] **Step 4: 在 ResourceTree 聚合虚拟 ROI 分组**

只有 `canManageWorkspaceRole(userStore.getTenantRole)` 为真时请求 `roiDashboardApi.list()`；不得使用包含平台委托兼容语义的 `isTenantAdminUser`。`buildCombinedTree` 始终保持 default → roi → my；普通成员传入空且不创建 ROI 虚拟组。ROI 节点使用 `dashboard_scope: 'roi'`、`raw_id` 和独立 key 前缀，点击后路由为 `/dashboard/index?resourceId={id}&dashboardMode=roi`。

ROI 根组菜单只提供“设置数据源”“新建下属看板”和排序；不提供文件夹、加入推荐或复制到我的看板。

- [ ] **Step 5: 在 SQPreviewShow 分流 ROI 内容**

`dashboardMode=roi` 时渲染 `RoiDashboardPanel`，并在普通 `loadCanvasData` 调用之前返回；离开 ROI 模式时清理 ROI store，进入 ROI 模式时不调用 `dashboardApi.load_resource/default_load`。

- [ ] **Step 6: 运行接入测试并确认 GREEN**

Run:

```powershell
node frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs
node frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs
node frontend/src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs
```

Expected: 全部退出码为 `0`。

- [ ] **Step 7: 提交树与状态任务**

```powershell
git add frontend/src/api/roiDashboard.ts frontend/src/stores/roiDashboard.ts frontend/src/views/dashboard/roi/types.ts frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs
git commit -m "功能：接入 ROI 看板导航和状态"
```

### Task 7: 实现 ROI 专用页面与响应式网格

**Files:**
- Create: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`
- Create: `frontend/src/views/dashboard/roi/RoiDatasourceDialog.vue`
- Create: `frontend/src/views/dashboard/roi/RoiChartGrid.vue`
- Create: `frontend/src/views/dashboard/roi/RoiChartCard.vue`
- Test: `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`
- Test: `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs`

**Interfaces:**
- `RoiDashboardPanel` props: `{ dashboardId: string }`.
- `RoiDatasourceDialog` emits: `saved(config)` and `cancelled`.
- `RoiChartGrid` props: `{ charts: RoiChart[]; canEdit: boolean }`; emits `edit`, `remove`, `reorder`, `span-change`.
- `RoiChartCard` renders existing SQView-compatible chart config without importing canvas state.

- [ ] **Step 1: 写新建流程和网格失败测试**

```javascript
assert.match(panel, /ensureRoiDatasourceBeforeCreate/)
assert.match(panel, /openCreateDashboardNameDialog/)
assert.match(panel, /openFirstChartEditor/)
assert.match(panel, /editorState\.mode\s*=\s*'create'/)
assert.match(grid, /grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)/)
assert.match(grid, /layout_span.*full.*half.*third/s)
assert.doesNotMatch(grid, /canvasData|component_data|canvas_view_info/)
```

- [ ] **Step 2: 运行页面测试并确认 RED**

Run:

```powershell
node frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs
node frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs
```

Expected: FAIL，提示 ROI 页面文件不存在或缺少流程函数。

- [ ] **Step 3: 实现数据源设置与首次编辑流程**

未配置数据源时，“新建下属看板”先打开 `RoiDatasourceDialog`；保存成功后继续名称弹窗。创建成功立即把新 ID 写入路由和 store，再设置：

```typescript
editorState.value = {
  visible: true,
  mode: 'create',
  dashboardId: created.id,
  chartId: null,
  initialValue: null,
  firstChart: true,
}
```

取消首次编辑只关闭编辑器，不删除空看板。

- [ ] **Step 4: 实现六列固定网格**

桌面映射为 `full=span 6`、`half=span 3`、`third=span 2`；窄屏通过媒体查询降为单列或双列。拖动只更新数组顺序并提交 `sort`，不生成 X/Y 坐标。标题、加载、权限错误使用稳定最小高度，禁止改变网格列宽。

- [ ] **Step 5: 实现无数据源权限状态**

后端图表列表返回 `can_execute`、`can_edit` 和受控错误信息。`RoiChartCard` 在 `can_execute=false` 时不挂载图表执行，只显示“当前账号无此数据源权限”；添加、编辑、删除和宽度控制全部禁用。

- [ ] **Step 6: 运行页面测试并确认 GREEN**

Run:

```powershell
node frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs
node frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs
```

Expected: 全部退出码为 `0`。

- [ ] **Step 7: 提交页面与网格任务**

```powershell
git add frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiDatasourceDialog.vue frontend/src/views/dashboard/roi/RoiChartGrid.vue frontend/src/views/dashboard/roi/RoiChartCard.vue frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs
git commit -m "功能：实现 ROI 专用看板页面"
```

### Task 8: 实现完全隔离的 ROI SQL 编辑器

**Files:**
- Create: `frontend/src/views/dashboard/roi/RoiSqlEditor.vue`
- Create: `frontend/src/views/dashboard/roi/roiChartConfig.ts`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`
- Test: `frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs`
- Test: `frontend/src/views/dashboard/roi/roiChartConfig.test.mjs`

**Interfaces:**
- Props: `modelValue`, `dashboardId`, `chart`, `canEdit`.
- Emits: `update:modelValue`, `saved`, `cancelled`.
- `serializeRoiChartForm(form) -> RoiChartCreate | RoiChartUpdate`.
- `hydrateRoiChartForm(chart) -> RoiChartForm`.
- Editor calls only `roiDashboardApi.previewChart/createChart/updateChart`.

- [ ] **Step 1: 写隔离和配置往返失败测试**

```javascript
assert.doesNotMatch(source, /DashboardSqlEditor\.vue/)
assert.doesNotMatch(source, /useDashboardStore|canvasData|canvasViewInfo/)
assert.doesNotMatch(source, /external_mcp|mcpServerId|mcpTool/)
assert.match(source, /roiDashboardApi\.previewChart/)
assert.match(source, /roiDashboardApi\.createChart/)
assert.match(source, /roiDashboardApi\.updateChart/)
assert.match(source, /pivotEnabled/)
assert.match(source, /insightEnabled/)
assert.match(source, /layoutSpan/)
```

`roiChartConfig.test.mjs` 使用一个同时包含 x/y/series/columns、pivot、insight 和 `layoutSpan='half'` 的完整 fixture，断言 `hydrate → serialize` 保持业务字段相等且不生成 `datasource_id`。

- [ ] **Step 2: 运行编辑器测试并确认 RED**

Run:

```powershell
node frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs
node frontend/src/views/dashboard/roi/roiChartConfig.test.mjs
```

Expected: FAIL，提示编辑器和配置模块不存在。

- [ ] **Step 3: 创建独立编辑器状态合同**

```typescript
export interface RoiChartForm {
  sql: string
  title: string
  chartType: ChartTypes
  columns: string[]
  x: string
  y: string[]
  series: string
  pivotEnabled: boolean
  pivot: RoiPivotConfig
  insightEnabled: boolean
  insight: RoiInsightConfig
  layoutSpan: 'full' | 'half' | 'third'
  version?: number
}
```

编辑器内部独立创建 `reactive<RoiChartForm>`、预览结果、字段元数据和验证签名。数据源名称只读展示，表单和 API payload 都不含 `datasource_id`。

- [ ] **Step 4: 实现完整 SQL 和图表配置流程**

编辑器包含“图表配置”和“SQL 明细”两个页签、预览按钮、图表类型、轴字段、表格列、透视、洞察和宽度控件。任意 SQL 或配置变化使 `lastPreviewSignature` 失效；只有当前签名预览成功后允许保存。修改模式携带服务端 `version`，冲突时保留当前表单。

复用图表类型、透视和洞察纯类型/纯函数时只能从不读取普通 dashboard store 的模块导入；不得为复用而修改 `DashboardSqlEditor.vue`。

- [ ] **Step 5: 接入页面保存事件**

保存成功后关闭编辑器、重新加载当前下属看板图表，并保持 `dashboardMode=roi` 和当前 `resourceId`。取消首次编辑保留空看板；取消普通新增或修改不写入服务端。

- [ ] **Step 6: 运行编辑器测试并确认 GREEN**

Run:

```powershell
node frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs
node frontend/src/views/dashboard/roi/roiChartConfig.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
```

Expected: 全部退出码为 `0`。

- [ ] **Step 7: 提交独立编辑器任务**

```powershell
git add frontend/src/views/dashboard/roi/RoiSqlEditor.vue frontend/src/views/dashboard/roi/roiChartConfig.ts frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs frontend/src/views/dashboard/roi/roiChartConfig.test.mjs
git commit -m "功能：新增 ROI 专用 SQL 编辑器"
```

### Task 9: 完成端到端回归与文档对照

**Files:**
- Modify only files required by failures found in this task.
- Verify: `docs/superpowers/specs/2026-07-16-roi-dashboard-design.md`.

**Interfaces:**
- No new public interfaces.
- Confirms all prior task interfaces compose without compatibility fallbacks.

- [ ] **Step 1: 运行完整 ROI 后端测试**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_migration.py tests/test_roi_dashboard_permissions.py tests/test_roi_dashboard_service.py tests/test_roi_dashboard_query_executor.py tests/test_roi_dashboard_api.py -q
```

Expected: PASS，无 warning/error。

- [ ] **Step 2: 运行现有看板后端回归**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest ..\tests\test_dashboard_service.py ..\tests\test_dashboard_default_copy_independence.py tests/test_dashboard_platform_template_snapshot.py tests/test_dashboard_permission_cache.py tests/test_dashboard_recommended_name_unique_migration.py -q
```

Expected: PASS；普通看板结果限制、表/字段权限和推荐独立复制测试保持通过。

- [ ] **Step 3: 运行全部 ROI 与现有关键前端脚本**

Run:

```powershell
node frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
node frontend/src/views/dashboard/preview/SQPreviewShow.roi.test.mjs
node frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs
node frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs
node frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs
node frontend/src/views/dashboard/roi/roiChartConfig.test.mjs
node frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs
node frontend/src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
```

Expected: 全部退出码为 `0`。

- [ ] **Step 4: 运行前端生产构建**

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b && vite build` 成功，退出码 `0`。

- [ ] **Step 5: 验证 Alembic head 与变更范围**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from alembic.config import Config; from alembic.script import ScriptDirectory; c=Config(); c.set_main_option('script_location','alembic'); print(ScriptDirectory.from_config(c).get_heads())"
cd ..
git diff --check
git status --short
```

Expected: Alembic 只有 `145roidashboard` 一个 head；无空白错误；未暂存用户原有文档、Excel 或输出目录。

- [ ] **Step 6: 对照设计逐项验收**

逐项确认设计文档 10 条验收标准都有自动化测试或构建证据，尤其确认：普通成员 API `403`、工作空间共享、统一数据源、首次自动打开编辑器、专用表和网格、编辑器隔离、无数据源权限状态、禁止带图换源、跳过行数/表/字段限制、普通看板无回归。

- [ ] **Step 7: 提交最终回归修正**

只有本任务产生代码修正时执行：

```powershell
git add backend/apps/roi_dashboard backend/apps/api.py backend/alembic/versions/145_roi_dashboard.py backend/tests/test_roi_dashboard_migration.py backend/tests/test_roi_dashboard_permissions.py backend/tests/test_roi_dashboard_service.py backend/tests/test_roi_dashboard_query_executor.py backend/tests/test_roi_dashboard_api.py frontend/src/api/roiDashboard.ts frontend/src/stores/roiDashboard.ts frontend/src/views/dashboard/roi frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json
git commit -m "测试：完善 ROI 看板端到端回归"
```

若没有产生修正，不创建空提交。
