# 推荐看板独立复制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“我的看板”加入推荐看板改为创建完全独立的推荐副本，并在工作空间内原子地禁止规范化同名推荐看板。

**Architecture:** 保留现有 `/dashboard/default/set` 接口，由服务层在 `is_default=true` 时深拷贝源看板并只写入推荐树；`is_default=false` 时删除独立推荐副本，同时兼容历史双树记录。服务层先做可读的重名校验，PostgreSQL 部分唯一索引负责多实例并发兜底。

**Tech Stack:** Python 3、FastAPI、SQLModel/SQLAlchemy、Alembic、PostgreSQL、pytest、Vue 3、Node.js 静态回归测试。

## Global Constraints

- 每次成功加入推荐看板都创建全新 UUID 和独立记录，不修改源看板。
- 推荐副本只写入 `scope=default` 的树位置，不写入 `scope=my`。
- 推荐名称按去除首尾空白并忽略英文大小写后，在同一 `tenant_id` 内唯一。
- 重名时明确拒绝，不覆盖、不刷新、不自动改名。
- 移出独立推荐副本时只软删除副本；历史双树记录继续保留在我的看板。
- 画布克隆必须继续通过 `_clone_dashboard_canvas_payload(...)` 重建组件和视图 ID。
- 不修改当前工作区中与本功能无关的 Excel 和修仙设计文档改动。

## File Map

- Modify: `backend/apps/dashboard/crud/dashboard_service.py`：独立克隆、重名校验、事务冲突转换和移出逻辑。
- Modify: `tests/test_dashboard_default_copy_independence.py`：服务层行为回归测试。
- Create: `backend/alembic/versions/144_recommended_dashboard_name_unique.py`：推荐名称部分唯一索引及冲突预检。
- Create: `backend/tests/test_dashboard_recommended_name_unique_migration.py`：迁移定义回归测试。
- Create: `frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs`：确认加入成功后只刷新树并保持源节点选中。

---

### Task 1: 创建独立推荐副本

**Files:**
- Modify: `tests/test_dashboard_default_copy_independence.py`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:3784-3837`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:4142-4211`

**Interfaces:**
- Consumes: `_clone_dashboard_canvas_payload(component_data, canvas_style_data, canvas_view_info) -> tuple[str, str, str]`、`_dashboard_tree_upsert_position(...) -> CoreDashboardTree`。
- Produces: `_clone_dashboard_record(session, user, source, *, sort=0, is_default=False, require_datasource=True) -> CoreDashboard`；`set_default_resource(...)` 在加入时返回新副本响应。

- [ ] **Step 1: 写入独立复制失败测试**

在测试文件中导入 `json` 与 `DashboardDefaultRequest`，新增：

```python
def test_set_default_resource_creates_independent_recommended_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        source = CoreDashboard(
            id="my-dashboard",
            tenant_id=1,
            name="付费",
            pid="root",
            datasource=2,
            node_type="leaf",
            type="dashboard",
            create_by="2",
            create_time=100,
            update_time=101,
            delete_flag=0,
            is_default=0,
            mobile_layout=1,
            component_data='[{"id":"chart-1","_dragId":"chart-1","component":"SQView"}]',
            canvas_style_data='{"width":1920}',
            canvas_view_info='{"chart-1":{"id":"chart-1","chart":{"id":"chart-1"},"datasource":2,"sql":"select 1"}}',
        )
        session.add(source)
        session.add(CoreDashboardTree(
            id="tree-my",
            tenant_id=1,
            scope="my",
            dashboard_id=source.id,
            parent_id="root",
            sort=1,
        ))
        session.commit()

        response = dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id=source.id, is_default=True),
        )
        source_after = session.get(CoreDashboard, source.id)
        copied = session.get(CoreDashboard, response.id)
        copied_positions = session.exec(
            select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == response.id)
        ).all()

    assert response.id != source.id
    assert source_after is not None
    assert source_after.is_default == 0
    assert source_after.update_time == 101
    assert copied is not None
    assert copied.is_default == 1
    assert copied.name == "付费"
    assert copied.datasource == 2
    assert copied.mobile_layout == 1
    assert json.loads(copied.canvas_style_data) == {"width": 1920}
    assert "chart-1" not in copied.component_data
    assert "chart-1" not in copied.canvas_view_info
    assert [(row.scope, row.parent_id) for row in copied_positions] == [("default", "root")]
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py::test_set_default_resource_creates_independent_recommended_dashboard -q`

Expected: FAIL，返回 ID 仍为 `my-dashboard` 或源记录被设置为 `is_default=1`。

- [ ] **Step 3: 提取通用克隆函数并改造加入分支**

在服务中把现有 `_clone_default_dashboard_record` 的主体提取为：

```python
def _clone_dashboard_record(
        session: SessionDep,
        user: CurrentUser,
        source: CoreDashboard,
        *,
        sort: int | None = 0,
        is_default: bool = False,
        require_datasource: bool = True,
) -> CoreDashboard:
    datasource_id = _effective_dashboard_datasource(source)
    if _is_external_mcp_dashboard(source):
        if not _external_mcp_dashboard_bound_to_current_tenant(session, user, source):
            raise HTTPException(status_code=403, detail="External MCP datasource is not bound to current workspace")
    elif datasource_id is None:
        if require_datasource:
            raise HTTPException(status_code=400, detail="Default dashboard datasource is required")
    else:
        if not datasource_bound_to_tenant(session, int(datasource_id), _current_tenant_id(user)):
            raise HTTPException(status_code=403, detail="Dashboard datasource is not in current workspace")
        _ensure_datasource_access(session, user, datasource_id, required=True)

    now = _now()
    component_data, canvas_style_data, canvas_view_info = _clone_dashboard_canvas_payload(
        source.component_data,
        source.canvas_style_data,
        source.canvas_view_info,
    )
    operator_id = _asset_operator_id(session, user)
    record = CoreDashboard(
        id=uuid.uuid4().hex,
        tenant_id=_current_tenant_id(user),
        name=(source.name or "").strip(),
        pid="root",
        datasource=datasource_id,
        external_mcp_server_id=source.external_mcp_server_id,
        org_id=source.org_id or "",
        level=source.level or 1,
        node_type="leaf",
        type=source.type or "dashboard",
        canvas_style_data=canvas_style_data,
        component_data=component_data,
        canvas_view_info=canvas_view_info,
        mobile_layout=source.mobile_layout or 0,
        status=DASHBOARD_STATUS_ACTIVE,
        self_watermark_status=source.self_watermark_status or 0,
        is_default=_smallint_flag(is_default),
        sort=int(sort or 0),
        create_by=operator_id,
        update_by=operator_id,
        create_time=now,
        update_time=now,
        remark=source.remark,
        source=DASHBOARD_SOURCE_EXTERNAL_MCP if _is_external_mcp_dashboard(source) else None,
        delete_flag=0,
        version=source.version or 3,
        content_id="0",
        check_version=source.check_version or "1",
    )
    session.add(record)
    session.flush()
    return record
```

保留 `_clone_default_dashboard_record(...)` 作为调用 `_clone_dashboard_record(..., is_default=False)` 的兼容包装。`set_default_resource` 的加入分支替换为：

```python
if request.is_default:
    max_sort_row = session.exec(
        select(func.max(func.coalesce(CoreDashboardTree.sort, 0))).where(
            and_(
                CoreDashboardTree.tenant_id == _current_tenant_id(user),
                CoreDashboardTree.scope == "default",
            )
        )
    ).first()
    sort_value = int(_first_scalar_value(max_sort_row) or 0) + 1
    copied = _clone_dashboard_record(
        session,
        user,
        record,
        sort=sort_value,
        is_default=True,
        require_datasource=False,
    )
    _dashboard_tree_upsert_position(
        session,
        user,
        "default",
        copied.id,
        "root",
        sort_value,
        operator_id,
        now,
    )
    session.commit()
    session.refresh(copied)
    return _dashboard_base_response(session, user, copied, effective_datasource)
```

该分支不得修改源记录。

- [ ] **Step 4: 运行独立复制测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py::test_set_default_resource_creates_independent_recommended_dashboard -q`

Expected: PASS。

- [ ] **Step 5: 运行既有推荐复制回归**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py -q`

Expected: 全部 PASS，现有“推荐复制到我的看板”和历史修复行为不变。

- [ ] **Step 6: 提交**

```powershell
git add backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_default_copy_independence.py
git commit -m "功能：推荐看板创建独立副本"
```

### Task 2: 拒绝规范化同名推荐看板

**Files:**
- Modify: `tests/test_dashboard_default_copy_independence.py`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`

**Interfaces:**
- Consumes: `_active_dashboard_filter()`、`_current_tenant_id(user) -> int`。
- Produces: `_normalize_recommended_dashboard_name(name) -> str`、`_recommended_dashboard_name_exists(session, user, name) -> bool`、`RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE`。

- [ ] **Step 1: 写入同工作空间重名失败测试**

```python
def test_set_default_resource_rejects_trimmed_case_insensitive_duplicate_name(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(CoreDashboard(
            id="existing-default", tenant_id=1, name="Pay Dashboard", pid="root",
            datasource=2, node_type="leaf", type="dashboard", is_default=1,
            status=1, delete_flag=0, component_data="[]", canvas_style_data="{}",
            canvas_view_info="{}",
        ))
        session.add(CoreDashboard(
            id="source", tenant_id=1, name="  pay dashboard  ", pid="root",
            datasource=2, node_type="leaf", type="dashboard", is_default=0,
            status=1, delete_flag=0, component_data="[]", canvas_style_data="{}",
            canvas_view_info="{}",
        ))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.set_default_resource(
                session, current_user, DashboardDefaultRequest(dashboard_id="source", is_default=True)
            )
        records = session.exec(select(CoreDashboard)).all()

    assert exc.value.status_code == 409
    assert exc.value.detail == dashboard_service.RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE
    assert {record.id for record in records} == {"existing-default", "source"}
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py::test_set_default_resource_rejects_trimmed_case_insensitive_duplicate_name -q`

Expected: FAIL，当前实现仍创建副本。

- [ ] **Step 3: 实现服务层规范化与租户内重名检查**

```python
RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE = "推荐看板中已存在同名看板"


def _normalize_recommended_dashboard_name(name: str | None) -> str:
    return (name or "").strip().lower()


def _recommended_dashboard_name_exists(
        session: SessionDep,
        user: CurrentUser,
        name: str | None,
) -> bool:
    normalized_name = _normalize_recommended_dashboard_name(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Dashboard name is required")
    duplicate = session.exec(
        select(CoreDashboard.id).where(
            and_(
                _active_dashboard_filter(),
                CoreDashboard.tenant_id == _current_tenant_id(user),
                CoreDashboard.node_type == "leaf",
                CoreDashboard.is_default == 1,
                func.lower(func.trim(CoreDashboard.name)) == normalized_name,
            )
        ).limit(1)
    ).first()
    return duplicate is not None
```

在创建副本前调用该函数；命中时抛出 `HTTPException(status_code=409, detail=RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE)`。

- [ ] **Step 4: 写入跨工作空间同名成功测试**

```python
def test_set_default_resource_allows_same_name_in_another_workspace(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(CoreDashboard(
            id="tenant-2-default", tenant_id=2, name="Pay Dashboard", pid="root",
            datasource=2, node_type="leaf", type="dashboard", is_default=1,
            status=1, delete_flag=0, component_data="[]", canvas_style_data="{}",
            canvas_view_info="{}",
        ))
        session.add(CoreDashboard(
            id="tenant-1-source", tenant_id=1, name="pay dashboard", pid="root",
            datasource=2, node_type="leaf", type="dashboard", is_default=0,
            status=1, delete_flag=0, component_data="[]", canvas_style_data="{}",
            canvas_view_info="{}",
        ))
        session.commit()

        response = dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id="tenant-1-source", is_default=True),
        )
        copied = session.get(CoreDashboard, response.id)

    assert copied is not None
    assert copied.tenant_id == 1
    assert copied.name == "pay dashboard"
```

- [ ] **Step 5: 运行重名测试集**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py -q`

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_default_copy_independence.py
git commit -m "修复：阻止推荐看板同名副本"
```

### Task 3: 移出时删除独立副本并兼容历史记录

**Files:**
- Modify: `tests/test_dashboard_default_copy_independence.py`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:4193-4211`

**Interfaces:**
- Consumes: `_dashboard_has_tree_position(session, user, scope, dashboard_id) -> bool`。
- Produces: `set_default_resource(..., is_default=False)` 对推荐独立副本执行软删除，对历史双树记录只清除推荐状态。

- [ ] **Step 1: 写入独立副本移出失败测试**

```python
def test_remove_independent_recommended_dashboard_soft_deletes_only_copy(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(CoreDashboard(
            id="source", tenant_id=1, name="付费", pid="root", datasource=2,
            node_type="leaf", type="dashboard", is_default=0, status=1, delete_flag=0,
        ))
        session.add(CoreDashboard(
            id="recommended-copy", tenant_id=1, name="付费", pid="root", datasource=2,
            node_type="leaf", type="dashboard", is_default=1, status=1, delete_flag=0,
        ))
        session.add(CoreDashboardTree(
            id="tree-my", tenant_id=1, scope="my", dashboard_id="source",
            parent_id="root", sort=1,
        ))
        session.add(CoreDashboardTree(
            id="tree-default", tenant_id=1, scope="default", dashboard_id="recommended-copy",
            parent_id="root", sort=1,
        ))
        session.commit()

        dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id="recommended-copy", is_default=False),
        )
        source = session.get(CoreDashboard, "source")
        copied = session.get(CoreDashboard, "recommended-copy")
        positions = session.exec(select(CoreDashboardTree)).all()

    assert source is not None and source.delete_flag == 0
    assert copied is not None and copied.delete_flag == 1 and copied.is_default == 0
    assert [(row.scope, row.dashboard_id) for row in positions] == [("my", "source")]
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py::test_remove_independent_recommended_dashboard_soft_deletes_only_copy -q`

Expected: FAIL，当前代码只清除 `is_default`，没有软删除独立副本。

- [ ] **Step 3: 实现分支化移出逻辑**

删除推荐树位置后执行：

```python
has_my_position = _dashboard_has_tree_position(session, user, "my", record.id)
record.is_default = 0
record.update_by = operator_id
record.update_time = now
if not has_my_position:
    record.delete_flag = 1
    record.delete_by = operator_id
    record.delete_time = now
session.add(record)
session.commit()
session.refresh(record)
```

不得删除或修改任何其他 `dashboard_id`。

- [ ] **Step 4: 写入历史双树兼容测试**

```python
def test_remove_legacy_dual_tree_dashboard_keeps_my_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(CoreDashboard(
            id="legacy", tenant_id=1, name="历史看板", pid="root", datasource=2,
            node_type="leaf", type="dashboard", is_default=1, status=1, delete_flag=0,
        ))
        session.add(CoreDashboardTree(
            id="legacy-my", tenant_id=1, scope="my", dashboard_id="legacy",
            parent_id="root", sort=1,
        ))
        session.add(CoreDashboardTree(
            id="legacy-default", tenant_id=1, scope="default", dashboard_id="legacy",
            parent_id="root", sort=1,
        ))
        session.commit()

        dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id="legacy", is_default=False),
        )
        record = session.get(CoreDashboard, "legacy")
        positions = session.exec(
            select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == "legacy")
        ).all()

    assert record is not None and record.delete_flag == 0 and record.is_default == 0
    assert [(row.scope, row.dashboard_id) for row in positions] == [("my", "legacy")]
```

- [ ] **Step 5: 运行移出与完整文件测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py -q`

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_default_copy_independence.py
git commit -m "修复：移出推荐时仅删除独立副本"
```

### Task 4: 增加数据库并发唯一约束

**Files:**
- Create: `backend/alembic/versions/144_recommended_dashboard_name_unique.py`
- Create: `backend/tests/test_dashboard_recommended_name_unique_migration.py`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`
- Modify: `tests/test_dashboard_default_copy_independence.py`

**Interfaces:**
- Produces: 索引 `uq_core_dashboard_recommended_name`；迁移 revision `144dashboardname`，down revision `143trackingcollectside`；`_is_recommended_name_integrity_error(exc) -> bool`。

- [ ] **Step 1: 写入迁移定义失败测试**

```python
import importlib.util
from pathlib import Path


def test_recommended_dashboard_name_unique_migration_definition():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "144_recommended_dashboard_name_unique.py"
    )
    spec = importlib.util.spec_from_file_location("recommended_dashboard_name_unique", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "144dashboardname"
    assert module.down_revision == "143trackingcollectside"
    sql = str(module.CREATE_UNIQUE_INDEX_SQL).lower()
    assert "uq_core_dashboard_recommended_name" in sql
    assert "tenant_id" in sql
    assert "lower(btrim(name))" in sql
    assert "is_default" in sql
    assert "node_type = 'leaf'" in sql
    assert "delete_flag" in sql
    assert "status" in sql
```

- [ ] **Step 2: 运行迁移测试并确认红灯**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_recommended_name_unique_migration.py -q`

Expected: FAIL，迁移模块不存在。

- [ ] **Step 3: 创建迁移并显式拒绝历史冲突**

迁移定义以下 SQL 常量：

```python
DUPLICATE_RECOMMENDED_NAMES_SQL = sa.text("""
SELECT tenant_id, lower(btrim(name)) AS normalized_name, count(*) AS duplicate_count
FROM core_dashboard
WHERE COALESCE(delete_flag, 0) = 0
  AND COALESCE(status, 1) NOT IN (2, 3)
  AND node_type = 'leaf'
  AND COALESCE(is_default, 0) = 1
GROUP BY tenant_id, lower(btrim(name))
HAVING count(*) > 1
LIMIT 1
""")

CREATE_UNIQUE_INDEX_SQL = sa.text("""
CREATE UNIQUE INDEX uq_core_dashboard_recommended_name
ON core_dashboard (tenant_id, lower(btrim(name)))
WHERE COALESCE(delete_flag, 0) = 0
  AND COALESCE(status, 1) NOT IN (2, 3)
  AND node_type = 'leaf'
  AND COALESCE(is_default, 0) = 1
""")
```

`upgrade()` 先检查表和索引是否存在，再执行冲突查询；命中时抛出包含 `tenant_id`、规范化名称和数量的 `RuntimeError`，不得自动改名或删除。无冲突时创建索引。`downgrade()` 仅删除该索引。

- [ ] **Step 4: 写入数据库冲突转换失败测试**

测试文件导入 `IntegrityError`，新增：

```python
def test_recommended_name_integrity_error_is_converted_to_conflict(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_recommended_dashboard_name_exists", lambda *_args, **_kwargs: False)

    with Session(engine) as session:
        session.add(CoreDashboard(
            id="source", tenant_id=1, name="付费", pid="root", datasource=2,
            node_type="leaf", type="dashboard", is_default=0, status=1, delete_flag=0,
            component_data="[]", canvas_style_data="{}", canvas_view_info="{}",
        ))
        session.commit()
        original_commit = session.commit
        commit_calls = 0

        def conflicting_commit():
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls == 1:
                raise IntegrityError(
                    "insert",
                    {},
                    RuntimeError('duplicate key violates unique constraint "uq_core_dashboard_recommended_name"'),
                )
            return original_commit()

        monkeypatch.setattr(session, "commit", conflicting_commit)
        with pytest.raises(HTTPException) as exc:
            dashboard_service.set_default_resource(
                session,
                current_user,
                DashboardDefaultRequest(dashboard_id="source", is_default=True),
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == dashboard_service.RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE
```

- [ ] **Step 5: 实现提交异常转换**

导入 `IntegrityError`，新增：

```python
RECOMMENDED_DASHBOARD_NAME_UNIQUE_INDEX = "uq_core_dashboard_recommended_name"


def _is_recommended_name_integrity_error(exc: IntegrityError) -> bool:
    return RECOMMENDED_DASHBOARD_NAME_UNIQUE_INDEX in str(exc.orig or exc)
```

推荐副本提交使用 `try/except IntegrityError`：总是先 `session.rollback()`；仅索引命中时转换为统一的 409 业务错误，其余完整重新抛出。

- [ ] **Step 6: 运行迁移与服务测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_recommended_name_unique_migration.py tests/test_dashboard_default_copy_independence.py -q`

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```powershell
git add backend/alembic/versions/144_recommended_dashboard_name_unique.py backend/tests/test_dashboard_recommended_name_unique_migration.py backend/apps/dashboard/crud/dashboard_service.py tests/test_dashboard_default_copy_independence.py
git commit -m "数据库：约束推荐看板名称唯一"
```

### Task 5: 前端回归保护与完整验证

**Files:**
- Create: `frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs`

**Interfaces:**
- Consumes: `ResourceTree.vue` 的 `setDefault` 分支。
- Produces: 静态回归测试，保证成功后刷新树但不把选中节点切换到返回的推荐副本。

- [ ] **Step 1: 添加前端行为回归测试**

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')
const branch = source.match(
  /} else if \(opt === 'setDefault' \|\| opt === 'removeDefault'\) \{[\s\S]*?\n  } else if \(opt === 'copyDefault'\)/
)

assert.ok(branch, '需要保留加入或移出推荐看板的处理分支')
assert.match(branch[0], /dashboardApi\s*\.default_set\(/, '加入推荐看板必须调用后端复制接口')
assert.match(branch[0], /getTree\(\)/, '复制成功后必须刷新看板树')
assert.doesNotMatch(
  branch[0],
  /selectedNodeKey\.value\s*=/,
  '加入推荐看板后必须保持源看板选中，不能切换到推荐副本'
)
```

- [ ] **Step 2: 运行前端回归测试**

Run: `node frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs`

Expected: 无输出且退出码为 0。

- [ ] **Step 3: 运行看板后端相关测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_default_copy_independence.py tests/test_dashboard_service.py backend/tests/test_dashboard_platform_template_snapshot.py backend/tests/test_dashboard_permission_cache.py backend/tests/test_dashboard_recommended_name_unique_migration.py -q`

Expected: 全部 PASS。

- [ ] **Step 4: 运行前端类型检查与构建**

Run: `npm run build`

Workdir: `frontend`

Expected: `vue-tsc -b` 与 `vite build` 均退出码为 0。

- [ ] **Step 5: 检查迁移单头状态和变更范围**

Run: `backend\.venv\Scripts\python.exe -m alembic heads`

Workdir: `backend`

Expected: 仅输出 `144dashboardname (head)`。

Run: `git diff --check 0a537bb9..HEAD`

Expected: 退出码为 0；不包含用户现有的 Excel 和修仙设计文档改动。

- [ ] **Step 6: 提交前端回归测试**

```powershell
git add frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs
git commit -m "测试：保护推荐看板独立复制交互"
```
