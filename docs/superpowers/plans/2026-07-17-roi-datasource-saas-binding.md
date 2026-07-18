# ROI 数据源 SaaS 后台绑定实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SaaS 工作空间表单中增加可选的“ROI数据源”，复用 `core_roi_workspace_config` 保存，并彻底关闭 ROI 看板内部修改入口。

**Architecture:** 后端抽取不自行提交事务的工作空间 ROI 配置领域函数，由工作空间新增/编辑接口与普通数据源、第三方 MCP 绑定一起提交。工作空间 DTO 通过批量关联查询返回 ROI 数据源 ID 和名称；ROI 模块仅保留只读配置接口，前端删除数据源设置弹窗与相关状态。

**Tech Stack:** FastAPI、SQLModel、SQLAlchemy、Pytest、Vue 3、Pinia、TypeScript、Element Plus Secondary、Node.js 源码行为测试。

## Global Constraints

- `ROI数据源` 为可选单选字段，禁止使用普通绑定数据源或首个数据源作为静默回退。
- 配置唯一数据源为 `core_roi_workspace_config`，不得在 `core_tenant` 新增重复字段。
- 只有 SaaS 平台管理员可新增、修改或清除 ROI 数据源。
- 已存在活动 ROI 图表时，禁止更换或清除 ROI 数据源。
- ROI 看板内部不得保留可修改配置的 UI 或 HTTP 接口。
- 配置 ROI 数据源不得自动授予用户数据源权限；图表执行继续校验实际权限。
- 不触碰工作树中已有的 `sql_engine_executor.py`、`db.py`、`query_executor.py` 和对应测试修改。
- 未经用户明确授权，不执行 `git commit`、`git push` 或创建 PR。

---

## 文件结构

- `backend/apps/roi_dashboard/service.py`：提供 ROI 配置批量读取、平台管理绑定和活动图表保护。
- `backend/apps/roi_dashboard/api.py`：仅暴露 ROI 配置只读接口，移除数据源候选和修改路由。
- `backend/apps/roi_dashboard/schemas.py`：移除仅供 ROI 内部设置使用的请求和候选 DTO。
- `backend/apps/datasource/crud/binding.py`：为工作空间统一保存提供 `commit=False` 模式，默认行为保持不变。
- `backend/apps/external_mcp/crud.py`：为工作空间统一保存提供 `commit=False` 模式，默认行为保持不变。
- `backend/apps/system/schemas/tenant_schema.py`：增加 ROI 数据源请求与响应字段。
- `backend/apps/system/api/tenant.py`：批量组装 ROI 绑定并在工作空间事务中写入配置。
- `backend/tests/test_roi_dashboard_service.py`：覆盖平台绑定、清除、幂等与图表保护。
- `backend/tests/test_roi_dashboard_api.py`：确认 ROI 修改接口已移除。
- `backend/tests/test_tenant_roi_datasource_binding.py`：覆盖工作空间 schema、DTO 和事务编排。
- `frontend/src/api/tenant.ts`：增加工作空间 ROI 数据源类型。
- `frontend/src/views/system/tenant/Tenant.vue`：增加 SaaS 表单字段及保存回填逻辑。
- `frontend/src/i18n/{zh-CN,zh-TW,en,ko-KR}.json`：增加字段文案。
- `frontend/src/views/system/tenant/Tenant.roi.test.mjs`：验证字段位置、可选语义和请求字段。
- `frontend/src/api/roiDashboard.ts`：移除 ROI 配置写接口和数据源候选接口。
- `frontend/src/stores/roiDashboard.ts`：移除数据源设置弹窗状态和动作。
- `frontend/src/views/dashboard/common/ResourceTree.vue`：移除 ROI 根菜单的数据源设置操作。
- `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`：移除设置按钮和弹窗，增加未配置提示。
- `frontend/src/views/dashboard/roi/roiDashboardPanelBehavior.ts`：未配置时中止新建流程并通知用户。
- `frontend/src/views/dashboard/roi/types.ts`：移除配置写请求、候选项和弹窗状态类型。
- 删除 `frontend/src/views/dashboard/roi/RoiDatasourceDialog.vue`、`RoiDatasourceDialog.test.mjs`、`roiDatasourceDialogBehavior.ts`。

---

### Task 1: 抽取平台可用的 ROI 配置领域服务

**Files:**
- Modify: `backend/apps/roi_dashboard/service.py:196`
- Test: `backend/tests/test_roi_dashboard_service.py:380`

**Interfaces:**
- Produces: `list_roi_workspace_config_rows(session, tenant_ids) -> list[tuple[int, int, str | None]]`
- Produces: `set_roi_datasource_for_tenant(session, *, tenant_id, datasource_id, operator_id, commit, cache_adapter=None) -> CoreRoiWorkspaceConfig | None`
- Consumes: `CoreRoiWorkspaceConfig`、`CoreRoiDashboardChart`、`CoreDatasource`

- [ ] **Step 1: 写失败测试，覆盖新增、幂等、清除和图表保护**

先把该文件 SQLite fixture 中的 `core_datasource` DDL 和插入函数补齐状态字段：

```python
"CREATE TABLE core_datasource ("
"id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL, status TEXT)"
```

```python
def add_datasource(session: Session, datasource_id: int, name: str | None = None) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource (id, tenant_id, name, status) "
            "VALUES (:id, 1, :name, 'success')"
        ),
        params={"id": datasource_id, "name": name or f"数据源 {datasource_id}"},
    )
```

然后增加：

```python
def test_platform_admin_can_create_and_read_roi_datasource_binding(session: Session) -> None:
    add_datasource(session, 101, "ROI 数据源")

    created = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=1,
        commit=True,
    )

    assert created is not None
    assert (created.tenant_id, created.datasource_id, created.version) == (11, 101, 1)
    assert service.list_roi_workspace_config_rows(session, [11]) == [
        (11, 101, "ROI 数据源")
    ]


def test_platform_admin_roi_datasource_binding_is_idempotent(session: Session) -> None:
    add_datasource(session, 101)
    original = seed_roi_config(session, tenant_id=11, datasource_id=101, version=3)

    updated = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=9,
        commit=True,
    )

    assert updated is not None
    assert updated.id == original.id
    assert updated.version == 3


def test_platform_admin_can_clear_roi_datasource_without_active_charts(session: Session) -> None:
    add_datasource(session, 101)
    seed_roi_config(session, tenant_id=11, datasource_id=101)

    cleared = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=None,
        operator_id=1,
        commit=True,
    )

    assert cleared is None
    assert service.list_roi_workspace_config_rows(session, [11]) == []


@pytest.mark.parametrize("target_datasource_id", [None, 202])
def test_platform_admin_cannot_change_or_clear_roi_datasource_with_active_charts(
    session: Session,
    target_datasource_id: int | None,
) -> None:
    add_datasource(session, 101)
    add_datasource(session, 202)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    seed_dashboard(session, tenant_id=11, dashboard_id=301)
    seed_chart(session, tenant_id=11, dashboard_id=301, chart_id=401)

    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=target_datasource_id,
            operator_id=1,
            commit=True,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "已有 ROI 图表时不能更换或清除数据源"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_service.py -k "platform_admin" -q`

Expected: FAIL，提示 `set_roi_datasource_for_tenant` 或 `list_roi_workspace_config_rows` 不存在。

- [ ] **Step 3: 实现批量读取与平台绑定函数**

在 `backend/apps/roi_dashboard/service.py` 增加以下核心实现：

```python
def list_roi_workspace_config_rows(
    session: SessionDep,
    tenant_ids: list[int],
) -> list[tuple[int, int, str | None]]:
    ids = sorted({int(tenant_id) for tenant_id in tenant_ids if tenant_id is not None})
    if not ids:
        return []
    rows = session.exec(
        select(
            CoreRoiWorkspaceConfig.tenant_id,
            CoreRoiWorkspaceConfig.datasource_id,
            CoreDatasource.name,
        )
        .join(CoreDatasource, CoreDatasource.id == CoreRoiWorkspaceConfig.datasource_id)
        .where(
            CoreRoiWorkspaceConfig.tenant_id.in_(ids),
            CoreRoiWorkspaceConfig.deleted.is_(False),
        )
        .order_by(CoreRoiWorkspaceConfig.tenant_id)
    ).all()
    return [(int(tenant_id), int(datasource_id), datasource_name) for tenant_id, datasource_id, datasource_name in rows]


def set_roi_datasource_for_tenant(
    session: SessionDep,
    *,
    tenant_id: int,
    datasource_id: int | None,
    operator_id: int | None,
    commit: bool,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> CoreRoiWorkspaceConfig | None:
    target_tenant_id = int(tenant_id)
    target_datasource_id = int(datasource_id) if datasource_id not in (None, "", 0) else None
    datasource_row = (
        session.exec(
            select(CoreDatasource.id, CoreDatasource.status).where(
                CoreDatasource.id == target_datasource_id
            )
        ).first()
        if target_datasource_id is not None
        else None
    )
    if target_datasource_id is not None and datasource_row is None:
        raise HTTPException(status_code=404, detail="ROI 数据源不存在")
    if datasource_row is not None and str(datasource_row[1] or "success").lower() != "success":
        raise HTTPException(status_code=400, detail="ROI 数据源不可用")

    record = lock_active_roi_config(session, target_tenant_id)
    if record is not None and target_datasource_id == int(record.datasource_id):
        return record

    if record is not None:
        active_chart_count = session.exec(
            select(func.count(CoreRoiDashboardChart.id)).where(
                CoreRoiDashboardChart.tenant_id == target_tenant_id,
                CoreRoiDashboardChart.deleted.is_(False),
                CoreRoiDashboardChart.status == 1,
            )
        ).one()
        if active_chart_count:
            raise HTTPException(
                status_code=409,
                detail="已有 ROI 图表时不能更换或清除数据源",
            )

    now = _now()
    if target_datasource_id is None:
        if record is None:
            return None
        record.deleted = True
        record.version += 1
        record.update_by = operator_id
        record.update_time = now
        session.add(record)
        result = None
    elif record is None:
        result = session.exec(
            select(CoreRoiWorkspaceConfig)
            .where(
                CoreRoiWorkspaceConfig.tenant_id == target_tenant_id,
                CoreRoiWorkspaceConfig.deleted.is_(True),
            )
            .order_by(CoreRoiWorkspaceConfig.update_time.desc())
            .with_for_update()
        ).first()
        if result is None:
            result = CoreRoiWorkspaceConfig(
                tenant_id=target_tenant_id,
                datasource_id=target_datasource_id,
                version=1,
                create_by=operator_id,
                update_by=operator_id,
                create_time=now,
                update_time=now,
                deleted=False,
            )
        else:
            result.datasource_id = target_datasource_id
            result.version += 1
            result.update_by = operator_id
            result.update_time = now
            result.deleted = False
        session.add(result)
    else:
        record.datasource_id = target_datasource_id
        record.version += 1
        record.update_by = operator_id
        record.update_time = now
        session.add(record)
        result = record

    session.flush()
    if commit:
        session.commit()
        if result is not None:
            session.refresh(result)
    _invalidate_roi_chart_cache(cache_adapter, target_tenant_id)
    return result
```

保留现有读取、图表和缓存逻辑；将旧 `set_roi_config` 中可复用的活动图表保护收敛到新函数。

- [ ] **Step 4: 运行 ROI 服务测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_service.py -q`

Expected: PASS。

- [ ] **Step 5: 检查任务差异**

Run: `git diff --check -- backend/apps/roi_dashboard/service.py backend/tests/test_roi_dashboard_service.py`

Expected: 无输出。

---

### Task 2: 为工作空间保存提供统一事务模式

**Files:**
- Modify: `backend/apps/datasource/crud/binding.py:214`
- Modify: `backend/apps/external_mcp/crud.py:654`
- Create: `backend/tests/test_tenant_binding_transactions.py`

**Interfaces:**
- Produces: `bind_tenant_to_datasource(..., commit: bool = True)`
- Produces: `bind_datasource_to_tenant(..., commit: bool = True)`
- Produces: `bind_tenant_to_external_mcp(..., commit: bool = True)`
- Default `commit=True` 保证其他调用方行为不变。

- [ ] **Step 1: 写失败测试验证 `commit=False` 不提前提交**

创建 `backend/tests/test_tenant_binding_transactions.py`，SQLite fixture 明确建立 `core_tenant`、`core_datasource`、`core_datasource_tenant_binding`、`core_external_mcp_server` 和 `core_external_mcp_tenant_binding`，并插入工作空间 `11`、数据源 `101`、第三方 MCP `201`。测试主体如下：

```python
def test_datasource_binding_can_defer_commit(session: Session, user: SimpleNamespace) -> None:
    commit = Mock(wraps=session.commit)
    session.commit = commit

    bind_tenant_to_datasource(session, user, 11, 101, commit=False)

    commit.assert_not_called()
    assert get_bound_datasource_id_for_tenant(session, 11) == 101


def test_external_mcp_binding_can_defer_commit(session: Session, user: SimpleNamespace) -> None:
    commit = Mock(wraps=session.commit)
    session.commit = commit

    bind_tenant_to_external_mcp(session, user, 11, 201, commit=False)

    commit.assert_not_called()
    assert get_bound_external_mcp_id_for_tenant(session, 11) == 201
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_tenant_binding_transactions.py -q`

Expected: FAIL，提示函数不接受 `commit` 参数或仍调用 `session.commit()`。

- [ ] **Step 3: 实现可延迟提交的绑定收尾函数**

在两个绑定模块分别加入相同语义的私有函数：

```python
def _finish_binding(session: SessionDep, record, *, commit: bool) -> None:
    if commit:
        session.commit()
        if record is not None:
            session.refresh(record)
        return
    session.flush()
```

为 `bind_datasource_to_tenant`、`bind_tenant_to_datasource` 和 `bind_tenant_to_external_mcp` 增加 `commit: bool = True`，把函数内部所有 `session.commit()` / `session.refresh()` 改为 `_finish_binding(...)`。`bind_tenant_to_datasource` 调用 `bind_datasource_to_tenant` 时必须继续传递 `commit=commit`。

- [ ] **Step 4: 运行事务测试和现有 ROI 测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_tenant_binding_transactions.py tests/test_roi_dashboard_service.py -q`

Expected: PASS。

- [ ] **Step 5: 检查任务差异**

Run: `git diff --check -- backend/apps/datasource/crud/binding.py backend/apps/external_mcp/crud.py backend/tests/test_tenant_binding_transactions.py`

Expected: 无输出。

---

### Task 3: 将 ROI 配置接入工作空间接口与 DTO

**Files:**
- Modify: `backend/apps/system/schemas/tenant_schema.py:9`
- Modify: `backend/apps/system/api/tenant.py:18`
- Create: `backend/tests/test_tenant_roi_datasource_binding.py`

**Interfaces:**
- Consumes: `list_roi_workspace_config_rows(...)`
- Consumes: `set_roi_datasource_for_tenant(..., commit=False)`
- Produces: `TenantDTO.roi_datasource_id`、`TenantDTO.roi_datasource_name`
- Produces: `TenantCreator.roi_datasource_id`、`TenantEditor.roi_datasource_id`

- [ ] **Step 1: 写 schema、DTO 和事务编排失败测试**

在 `backend/tests/test_tenant_roi_datasource_binding.py` 增加：

```python
def test_tenant_schemas_accept_optional_roi_datasource() -> None:
    assert TenantCreator(name="测试").roi_datasource_id is None
    assert TenantEditor(name="测试").roi_datasource_id is None
    assert TenantCreator(name="测试", roi_datasource_id=101).roi_datasource_id == 101


def test_tenant_dto_contains_roi_datasource() -> None:
    dto = tenant_api._tenant_dto(
        make_tenant(),
        roi_datasource={
            "roi_datasource_id": 101,
            "roi_datasource_name": "ROI 数据源",
        },
        include_operations=True,
    )
    assert dto.roi_datasource_id == 101
    assert dto.roi_datasource_name == "ROI 数据源"


def make_tenant() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        public_id="WS11",
        name="测试",
        plan="default",
        status=1,
        subscription_status="active",
        billing_mode="manual",
        trial_end_time=None,
        current_period_end_time=None,
        contract_no=None,
        billing_contact=None,
        billing_email=None,
        subscription_note=None,
        create_time=0,
        update_time=0,
    )


class FakeTenantSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    def get(self, _model, _record_id):
        return make_tenant()

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_edit_tenant_saves_all_bindings_in_one_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeTenantSession()
    user = make_platform_admin()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(tenant_api, "update_tenant", lambda *args, **kwargs: make_tenant())
    monkeypatch.setattr(
        tenant_api,
        "bind_tenant_to_datasource",
        lambda *args, **kwargs: calls.append(("datasource", kwargs["commit"])),
    )
    monkeypatch.setattr(
        tenant_api,
        "bind_tenant_to_external_mcp",
        lambda *args, **kwargs: calls.append(("mcp", kwargs["commit"])),
    )
    monkeypatch.setattr(
        tenant_api,
        "set_roi_datasource_for_tenant",
        lambda *args, **kwargs: calls.append(("roi", kwargs["commit"])),
    )
    monkeypatch.setattr(tenant_api, "_write_tenant_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(tenant_api, "_tenant_admin_dto", lambda *args, **kwargs: TenantDTO(id=11, public_id="WS11", name="测试"))

    await tenant_api.edit_tenant(
        session,
        user,
        11,
        TenantEditor(
            name="测试",
            datasource_id=101,
            external_mcp_server_id=201,
            roi_datasource_id=301,
        ),
    )

    assert calls == [("datasource", False), ("mcp", False), ("roi", False)]
    assert session.commit_count == 1
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_tenant_roi_datasource_binding.py -q`

Expected: FAIL，提示 ROI 字段、DTO 参数或平台绑定调用不存在。

- [ ] **Step 3: 扩展 schema 和 DTO 组装**

在 `TenantDTO` 增加：

```python
roi_datasource_id: Optional[int] = None
roi_datasource_name: Optional[str] = None
```

在 `TenantCreator`、`TenantEditor` 增加：

```python
roi_datasource_id: Optional[int] = None
```

在 `backend/apps/system/api/tenant.py` 增加 `_tenant_roi_datasource_map`：

```python
def _tenant_roi_datasource_map(session: SessionDep, tenant_ids: list[int]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for tenant_id, datasource_id, datasource_name in list_roi_workspace_config_rows(session, tenant_ids):
        result[int(tenant_id)] = {
            "roi_datasource_id": int(datasource_id),
            "roi_datasource_name": datasource_name,
        }
    return result
```

为 `_tenant_dto` 增加 `roi_datasource: dict | None = None`，并写入两个响应字段；在 `_tenant_dto_list`、`_tenant_admin_dto`、`current_tenant`、`add_tenant` 返回路径中传入对应映射。

- [ ] **Step 4: 将新增和编辑接口改为一次提交**

新增接口使用 `creator`，编辑接口使用 `editor`。三类绑定都传入 `commit=False`，示例编辑逻辑如下：

```python
bind_tenant_to_datasource(
    session,
    current_user,
    int(tenant.id),
    editor.datasource_id,
    commit=False,
)
bind_tenant_to_external_mcp(
    session,
    current_user,
    int(tenant.id),
    editor.external_mcp_server_id,
    commit=False,
)
set_roi_datasource_for_tenant(
    session,
    tenant_id=int(tenant.id),
    datasource_id=editor.roi_datasource_id,
    operator_id=getattr(current_user, "id", None),
    commit=False,
)
session.commit()
```

新增接口仅在字段非空时创建三类绑定；编辑接口继续使用 `_model_fields_set` 区分“未提交”与“显式清空”。异常处理必须执行 `session.rollback()`：

```python
except ValueError as exc:
    session.rollback()
    raise HTTPException(status_code=400, detail=str(exc)) from exc
except Exception:
    session.rollback()
    raise
```

审计备注增加 `roi_datasource_id=<id|none|unchanged>`。

- [ ] **Step 5: 运行工作空间和 ROI 后端测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_tenant_roi_datasource_binding.py tests/test_tenant_binding_transactions.py tests/test_roi_dashboard_service.py -q`

Expected: PASS。

- [ ] **Step 6: 检查任务差异**

Run: `git diff --check -- backend/apps/system/schemas/tenant_schema.py backend/apps/system/api/tenant.py backend/tests/test_tenant_roi_datasource_binding.py`

Expected: 无输出。

---

### Task 4: 在 SaaS 工作空间表单增加 ROI 数据源

**Files:**
- Modify: `frontend/src/api/tenant.ts:3`
- Modify: `frontend/src/views/system/tenant/Tenant.vue:305`
- Modify: `frontend/src/i18n/zh-CN.json:20`
- Modify: `frontend/src/i18n/zh-TW.json:20`
- Modify: `frontend/src/i18n/en.json:20`
- Modify: `frontend/src/i18n/ko-KR.json:20`
- Create: `frontend/src/views/system/tenant/Tenant.roi.test.mjs`

**Interfaces:**
- Consumes: `TenantInfo.roi_datasource_id`、`TenantInfo.roi_datasource_name`
- Produces: 工作空间新增/编辑请求中的 `roi_datasource_id`

- [ ] **Step 1: 写失败的源码行为测试**

创建 `frontend/src/views/system/tenant/Tenant.roi.test.mjs`：

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const tenantView = readFileSync(join(currentDir, 'Tenant.vue'), 'utf8')
const tenantApi = readFileSync(join(currentDir, '../../../api/tenant.ts'), 'utf8')
const zhCN = JSON.parse(readFileSync(join(currentDir, '../../../i18n/zh-CN.json'), 'utf8'))

assert.equal(zhCN.tenant.roi_datasource, 'ROI数据源')
assert.match(tenantApi, /roi_datasource_id\?: number \| string \| null/)
assert.match(tenantApi, /roi_datasource_name\?: string \| null/)
assert.match(tenantView, /v-model="form\.roi_datasource_id"/)
assert.match(tenantView, /roi_datasource_id: form\.roi_datasource_id \|\| null/)
assert.ok(
  tenantView.indexOf("t('tenant.bound_datasource')") <
    tenantView.indexOf("t('tenant.roi_datasource')") &&
    tenantView.indexOf("t('tenant.roi_datasource')") <
      tenantView.indexOf("t('tenant.bound_external_mcp')"),
  'ROI 数据源必须位于普通数据源和第三方 MCP 之间'
)
assert.doesNotMatch(tenantView, /prop="roi_datasource_id"/)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `node frontend/src/views/system/tenant/Tenant.roi.test.mjs`

Expected: FAIL，提示文案、类型或表单字段不存在。

- [ ] **Step 3: 扩展 API 类型和表单状态**

在 `TenantInfo`、`tenantApi.add`、`tenantApi.edit` 增加：

```typescript
roi_datasource_id?: number | string | null
roi_datasource_name?: string | null
```

在 `defaultForm` 增加：

```typescript
roi_datasource_id: '' as number | string,
```

增加回填函数：

```typescript
const normalizeRoiDatasourceId = (tenant?: TenantInfo | null) => tenant?.roi_datasource_id || ''
```

- [ ] **Step 4: 增加表单项和保存字段**

在普通数据源与第三方 MCP 之间插入：

```vue
<el-form-item :label="t('tenant.roi_datasource')">
  <el-select
    v-model="form.roi_datasource_id"
    clearable
    filterable
    :disabled="isDefaultTenantForm"
    :loading="datasourceLoading"
    style="width: 100%"
    :placeholder="t('tenant.select_roi_datasource')"
  >
    <el-option
      v-for="datasource in datasourceOptions"
      :key="datasource.id"
      :label="datasource.name"
      :value="datasource.id"
    >
      <div class="datasource-option">
        <span class="datasource-name ellipsis">{{ datasource.name }}</span>
        <span class="datasource-type ellipsis">
          {{ datasource.type_name || datasource.type }}
        </span>
      </div>
    </el-option>
  </el-select>
</el-form-item>
```

打开编辑抽屉时写入 `normalizeRoiDatasourceId(tenant)`；保存 payload 中写入：

```typescript
roi_datasource_id: form.roi_datasource_id || null,
```

四种语言增加 `roi_datasource` 和 `select_roi_datasource`，中文分别为“ROI数据源”和“选择 ROI 看板数据源”。

- [ ] **Step 5: 运行前端字段测试和类型检查**

Run: `node frontend/src/views/system/tenant/Tenant.roi.test.mjs`

Expected: PASS。

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b` 和 Vite build 均成功。

- [ ] **Step 6: 检查任务差异**

Run: `git diff --check -- frontend/src/api/tenant.ts frontend/src/views/system/tenant/Tenant.vue frontend/src/i18n frontend/src/views/system/tenant/Tenant.roi.test.mjs`

Expected: 无输出。

---

### Task 5: 移除 ROI 看板内部数据源修改能力

**Files:**
- Modify: `backend/apps/roi_dashboard/api.py:45`
- Modify: `backend/apps/roi_dashboard/schemas.py:15`
- Modify: `backend/tests/test_roi_dashboard_api.py:60`
- Modify: `frontend/src/api/roiDashboard.ts:1`
- Modify: `frontend/src/stores/roiDashboard.ts:15`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:1160`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs:35`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue:1`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs:1`
- Modify: `frontend/src/views/dashboard/roi/roiDashboardPanelBehavior.ts:10`
- Modify: `frontend/src/views/dashboard/roi/types.ts:1`
- Delete: `frontend/src/views/dashboard/roi/RoiDatasourceDialog.vue`
- Delete: `frontend/src/views/dashboard/roi/RoiDatasourceDialog.test.mjs`
- Delete: `frontend/src/views/dashboard/roi/roiDatasourceDialogBehavior.ts`

**Interfaces:**
- Retains: `GET /dashboard/roi/config`
- Removes: `GET /dashboard/roi/datasources`
- Removes: `PUT /dashboard/roi/config`
- Produces: `runRoiDashboardCreateFlow(..., onMissingConfig)`

- [ ] **Step 1: 修改后端 API 测试，先形成失败断言**

在 `backend/tests/test_roi_dashboard_api.py` 将路由断言改为：

```python
def test_roi_config_is_read_only() -> None:
    methods = {
        route.path: set(route.methods or set())
        for route in roi_api.router.routes
    }
    assert methods["/dashboard/roi/config"] == {"GET"}
    assert "/dashboard/roi/datasources" not in methods
```

并删除 `RoiConfigUpdate`、`RoiDatasourceOption` 的接口 DTO 测试。

- [ ] **Step 2: 修改前端行为测试，禁止设置入口**

在 `ResourceTree.roi.test.mjs` 将 ROI 菜单断言改为：

```javascript
assert.doesNotMatch(roiMenu[1], /setRoiDatasource|openDatasourceSettings/)
assert.match(roiMenu[1], /newRoiDashboard/)
```

在 `RoiDashboardPanel.test.mjs` 增加：

```javascript
assert.doesNotMatch(panel, /RoiDatasourceDialog|openDatasourceSettings|设置数据源/)
assert.match(panel, /请联系 SaaS 管理员配置 ROI 数据源/)
```

将创建流程测试改为未配置时通知并中止：

```javascript
{
  const calls = []
  const created = await runRoiDashboardCreateFlow({
    ensureConfigLoaded: async () => calls.push('config'),
    getConfig: () => null,
    onMissingConfig: () => calls.push('missing'),
    requestName: async () => calls.push('name'),
    createDashboard: async () => calls.push('create'),
    publishDashboard: () => calls.push('publish'),
    navigate: async () => calls.push('navigate'),
    openEditor: () => calls.push('editor'),
  })
  assert.equal(created, null)
  assert.deepEqual(calls, ['config', 'missing'])
}
```

- [ ] **Step 3: 运行后端和前端测试并确认失败**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_api.py -q`

Expected: FAIL，现有 PUT 和 datasources 路由仍存在。

Run: `node frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs; node frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Expected: FAIL，现有设置入口和弹窗仍存在。

- [ ] **Step 4: 删除后端配置写入口**

从 `backend/apps/roi_dashboard/api.py` 删除 `/datasources` 和 `PUT /config` 路由及无用导入；从 `schemas.py` 删除 `RoiConfigUpdate`、`RoiDatasourceOption`。保留 `GET /config` 与 `RoiConfigResponse`。

删除不再被调用的 `set_roi_config`，测试统一使用 Task 1 的 `set_roi_datasource_for_tenant`。

- [ ] **Step 5: 删除前端写 API、弹窗状态和组件**

从 `roiDashboardApi` 删除 `listDatasources`、`updateConfig`；从 `RoiEditorState` 和 store 删除 `datasourceDialogOpen`、`openDatasourceSettings`、`publishConfig`。

从 `ResourceTree.vue` 删除 `setRoiDatasource` 菜单项及其处理逻辑。

从 `RoiDashboardPanel.vue` 删除 `Setting`、`RoiDatasourceDialog`、`datasourceResolution`、弹窗监听和保存/取消回调。模板增加：

```vue
<div v-else-if="!config" class="roi-dashboard-panel__state is-permission">
  请联系 SaaS 管理员配置 ROI 数据源
</div>
```

新建流程改为：

```typescript
const created = await runRoiDashboardCreateFlow({
  ensureConfigLoaded,
  getConfig: () => config.value,
  onMissingConfig: () => ElMessage.warning('请联系 SaaS 管理员配置 ROI 数据源'),
  requestName: openCreateDashboardNameDialog,
  createDashboard: (name) => roiDashboardApi.create({ name }, roiCustomErrorRequestConfig),
  publishDashboard: (created) => {
    roiDashboardStore.publishDashboard(created)
    roiDashboardStore.publishCharts(String(created.id), [])
  },
  navigate: (target) => router.push(target),
  openEditor: openFirstChartEditor,
})
```

`runRoiDashboardCreateFlow` 的配置判断改为：

```typescript
await dependencies.ensureConfigLoaded()
if (!dependencies.getConfig()) {
  dependencies.onMissingConfig()
  return null
}
```

删除三个数据源弹窗文件。

- [ ] **Step 6: 运行 ROI 前后端测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_roi_dashboard_api.py tests/test_roi_dashboard_service.py tests/test_roi_dashboard_permissions.py -q`

Expected: PASS。

Run: `node frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs; node frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs; node frontend/src/stores/roiDashboard.behavior.test.mjs`

Expected: PASS。

- [ ] **Step 7: 检查任务差异**

Run: `git diff --check -- backend/apps/roi_dashboard frontend/src/api/roiDashboard.ts frontend/src/stores/roiDashboard.ts frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/roi`

Expected: 无输出。

---

### Task 6: 完整验证与手工验收

**Files:**
- Verify only: 所有本计划涉及文件

**Interfaces:**
- Verifies: SaaS 后台为唯一 ROI 数据源配置入口。
- Verifies: 未配置、无权限、有图表三类保护状态。

- [ ] **Step 1: 运行后端专项测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_tenant_binding_transactions.py tests/test_tenant_roi_datasource_binding.py tests/test_roi_dashboard_api.py tests/test_roi_dashboard_permissions.py tests/test_roi_dashboard_service.py tests/test_roi_dashboard_query_executor.py -q`

Expected: PASS。若现有未提交的查询执行器修改导致失败，只记录与本需求无关的失败，不修改其代码。

- [ ] **Step 2: 运行前端专项测试**

Run:

```powershell
node frontend/src/views/system/tenant/Tenant.roi.test.mjs
node frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
node frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs
node frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs
node frontend/src/stores/roiDashboard.behavior.test.mjs
```

Expected: 全部 PASS。

- [ ] **Step 3: 运行前端构建**

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b` 与 Vite build 成功。

- [ ] **Step 4: 手工验证 SaaS 工作空间表单**

按本地运行手册启动四个服务，平台管理员进入“工作空间管理”：

1. 新建工作空间，不选择 ROI 数据源，保存成功。
2. 编辑该工作空间，确认“ROI数据源”位于“绑定数据源”和“绑定第三方 MCP”之间。
3. 选择数据源并保存，再次打开能够正确回填。
4. 清空 ROI 数据源并保存，在没有 ROI 图表时成功。

- [ ] **Step 5: 手工验证 ROI 看板只读配置**

1. 未配置 ROI 数据源时进入 ROI 看板，显示“请联系 SaaS 管理员配置 ROI 数据源”。
2. ROI 根菜单和看板页均不存在“设置数据源”入口。
3. 未配置时无法新建 ROI 看板或图表。
4. SaaS 后台配置后，拥有数据源权限的管理员可以创建和执行图表。
5. 无数据源权限的管理员仍看到结构，但图表不执行。
6. 已存在活动图表时，SaaS 后台更换或清除数据源返回明确冲突提示。

- [ ] **Step 6: 最终差异检查**

Run: `git diff --check`

Expected: 无输出。

Run: `git status --short`

Expected: 只包含本计划文件、实现文件，以及开始实施前已经存在的四个未提交文件。
