# Dashboard Independent Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 推荐看板复制到我的看板后必须成为独立看板，删除复制件不能删除推荐源看板。

**Architecture:** 后端继续作为复制语义的唯一可信边界：复制接口创建新的 `core_dashboard` 实体并写入 `core_dashboard_tree(scope='my')`；删除接口拒绝删除同时挂在推荐树的看板实体；历史脏数据通过显式迁移函数把我的树中误挂推荐源 id 的节点转换为独立副本。前端保持调用 `/dashboard/default/copy`，后端测试覆盖防误删与迁移行为。

**Tech Stack:** Python, FastAPI service layer, SQLModel/SQLAlchemy, pytest, Vue 3 resource tree.

## Global Constraints

- 代码注释和说明使用中文。
- 不引入业务域硬编码，修复仅围绕通用看板复制、树关系和删除语义。
- 不添加静默兼容兜底；遇到推荐源被当作我的看板删除时，必须显式拒绝或通过迁移函数显式修复。
- 新生产行为必须先写失败测试，再写最小实现。

---

### Task 1: 删除推荐源防误删

**Files:**
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`

**Interfaces:**
- Consumes: `delete_resource(session, current_user, resource_id)`
- Produces: 删除接口在目标看板仍属于推荐树或 `is_default=1` 时抛出 `HTTPException(400, ...)`

- [ ] **Step 1: Write the failing test**

```python
def test_delete_resource_rejects_default_dashboard_shared_with_my_tree(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        session.add(CoreDashboard(id="default-dashboard", name="推荐看板", pid="root", datasource=2, node_type="leaf", type="dashboard", create_by="2", create_time=100, delete_flag=0, is_default=1))
        session.add(CoreDashboardTree(id="tree-default", tenant_id=1, scope="default", dashboard_id="default-dashboard", parent_id="root", sort=1))
        session.add(CoreDashboardTree(id="tree-my", tenant_id=1, scope="my", dashboard_id="default-dashboard", parent_id="root", sort=1))
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.delete_resource(session, current_user, "default-dashboard")
        source = session.get(CoreDashboard, "default-dashboard")
        tree_rows = session.exec(select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == "default-dashboard")).all()

    assert exc.value.status_code == 400
    assert source is not None
    assert {row.scope for row in tree_rows} == {"default", "my"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_default_copy_independence.py::test_delete_resource_rejects_default_dashboard_shared_with_my_tree -q`
Expected: FAIL because `delete_resource` currently deletes the source entity.

- [ ] **Step 3: Write minimal implementation**

Add a small helper to detect default tree membership and call it from `delete_resource` before deleting rows.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_default_copy_independence.py::test_delete_resource_rejects_default_dashboard_shared_with_my_tree -q`
Expected: PASS.

### Task 2: 历史脏数据显式迁移

**Files:**
- Modify: `backend/apps/dashboard/crud/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`

**Interfaces:**
- Produces: `repair_my_tree_default_dashboard_copies(session, user) -> list[CoreDashboard]`
- Behavior: 将 `scope='my'` 中误指向推荐看板的叶子节点复制为新实体，并把对应树节点改指向新 id。

- [ ] **Step 1: Write the failing test**

```python
def test_repair_my_tree_default_dashboard_copies_repoints_my_tree(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(CoreDashboard(id="default-dashboard", name="推荐看板", pid="root", datasource=2, node_type="leaf", type="dashboard", create_by="1", create_time=100, delete_flag=0, is_default=1, component_data="[]", canvas_style_data="{}", canvas_view_info="{}"))
        session.add(CoreDashboardTree(id="tree-default", tenant_id=1, scope="default", dashboard_id="default-dashboard", parent_id="root", sort=1))
        session.add(CoreDashboardTree(id="tree-my", tenant_id=1, scope="my", dashboard_id="default-dashboard", parent_id="root", sort=2))
        session.commit()

        repaired = dashboard_service.repair_my_tree_default_dashboard_copies(session, current_user)
        source = session.get(CoreDashboard, "default-dashboard")
        my_row = session.exec(select(CoreDashboardTree).where(CoreDashboardTree.id == "tree-my")).one()
        copied = session.get(CoreDashboard, my_row.dashboard_id)

    assert len(repaired) == 1
    assert source is not None
    assert my_row.dashboard_id != "default-dashboard"
    assert copied is not None
    assert copied.is_default == 0
    assert copied.name == "推荐看板"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_default_copy_independence.py::test_repair_my_tree_default_dashboard_copies_repoints_my_tree -q`
Expected: FAIL because the repair function does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement the repair function by reusing the same clone logic as `copy_default_resource`, preserving my-tree parent and sort.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_dashboard_default_copy_independence.py -q`
Expected: PASS.

### Task 3: 回归验证

**Files:**
- Test: `tests/test_dashboard_service.py`

**Interfaces:**
- Verifies: existing copy behavior still creates independent component ids.

- [ ] **Step 1: Run relevant dashboard service tests**

Run: `pytest tests/test_dashboard_default_copy_independence.py -q`
Expected: PASS.
