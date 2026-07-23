# ROI 工作空间管理员数据源权限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让工作空间 `owner/admin` 自动拥有该空间在 `core_roi_workspace_config` 中配置的 ROI 数据源访问权，无需额外写入 `core_datasource_user`。

**Architecture:** 保留现有 ROI 工作空间角色门控，在唯一权限入口 `list_roi_accessible_datasource_ids()` 中把当前空间有效 ROI 配置的数据源加入候选集合，再统一执行数据源状态过滤。配置响应、图表读取、SQL 执行和编辑写操作继续复用现有 `has_roi_datasource_access()`，前端无需改动。

**Tech Stack:** Python 3.11、FastAPI、SQLModel/SQLAlchemy、pytest、PostgreSQL（生产）/ SQLite（权限单测）

## Global Constraints

- 权限只对 `/dashboard/roi/*` ROI 能力生效，不扩展到 Smart Q&A、普通看板或数据源管理。
- 当前空间角色必须为 `owner` 或 `admin`；`member`、SaaS 全局管理员和其他空间管理员不得绕过。
- 只接受当前空间 `deleted=false` 的 ROI 配置。
- 数据源 `status` 必须大小写不敏感地等于 `success`。
- 不新增数据库迁移，不写入或删除 `core_datasource_user`。
- 不改变一个工作空间只能绑定一个主数据源的模型。

---

## File Map

- Modify: `backend/apps/roi_dashboard/permissions.py`
  - ROI 工作空间角色校验和数据源候选集合的唯一实现位置。
- Modify/Test: `backend/tests/test_roi_dashboard_permissions.py`
  - SQLite 权限夹具及工作空间管理员隐式 ROI 数据源授权回归测试。
- Modify/Test: `backend/tests/test_roi_dashboard_service.py`
  - 将“无账号级授权必须 403”的旧断言更新为工作空间管理员完整 ROI 权限。
- No change: `frontend/src/views/dashboard/roi/*`
  - 现有组件会根据后端 `can_execute/can_edit` 自动启用图表与抽屉。

### Task 1: 将当前空间 ROI 配置数据源纳入管理员可访问集合

**Files:**
- Modify: `backend/tests/test_roi_dashboard_permissions.py:28-232`
- Modify: `backend/tests/test_roi_dashboard_service.py:267-295,1000-1091,1523-1533`
- Modify: `backend/apps/roi_dashboard/permissions.py:3-69`

**Interfaces:**
- Consumes: `require_roi_workspace_admin(current_user) -> AccessContext`
- Consumes: `CoreRoiWorkspaceConfig.tenant_id`, `.datasource_id`, `.deleted`
- Produces: `list_roi_accessible_datasource_ids(session, current_user) -> set[int]`
- Produces: `has_roi_datasource_access(session, current_user, datasource_id) -> bool`

- [ ] **Step 1: 修正 SQLite 夹具，使失败来自缺失权限行为而不是测试表结构**

将 `core_datasource` 测试表补齐生产模型已有的 `tenant_id` 字段：

```python
connection.execute(
    text(
        "CREATE TABLE core_datasource ("
        "id BIGINT PRIMARY KEY, "
        "tenant_id BIGINT NOT NULL DEFAULT 1, "
        "status TEXT)"
    )
)
```

保留当前工作区中已经写好的目标回归用例：

```python
def test_workspace_admin_can_access_configured_roi_datasource_without_direct_grant(
    session: Session,
) -> None:
    from apps.roi_dashboard.permissions import (
        has_roi_datasource_access,
        list_roi_accessible_datasource_ids,
    )

    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 202)
    add_datasource(session, 303)
    configure_roi_datasource(session, tenant_id=11, datasource_id=202)
    configure_roi_datasource(session, tenant_id=22, datasource_id=303)
    session.commit()

    assert list_roi_accessible_datasource_ids(session, user) == {202}
    assert has_roi_datasource_access(session, user, 202) is True
    assert has_roi_datasource_access(session, user, 303) is False
```

- [ ] **Step 2: 运行目标测试，确认按预期失败**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_permissions.py::test_workspace_admin_can_access_configured_roi_datasource_without_direct_grant -q
```

Expected: `FAIL`，断言应显示实际集合为空、期望集合为 `{202}`；不得再出现 `no such column: core_datasource.tenant_id`。

- [ ] **Step 3: 添加已删除配置的拒绝用例**

在 `backend/tests/test_roi_dashboard_permissions.py` 增加：

```python
def test_deleted_roi_config_does_not_grant_datasource_access(
    session: Session,
) -> None:
    from apps.roi_dashboard.permissions import (
        has_roi_datasource_access,
        list_roi_accessible_datasource_ids,
    )

    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 202)
    configure_roi_datasource(
        session,
        tenant_id=11,
        datasource_id=202,
        deleted=True,
    )
    session.commit()

    assert list_roi_accessible_datasource_ids(session, user) == set()
    assert has_roi_datasource_access(session, user, 202) is False
```

- [ ] **Step 4: 实现最小权限集合改动**

在 `backend/apps/roi_dashboard/permissions.py` 导入 ROI 配置模型：

```python
from apps.roi_dashboard.models import CoreRoiWorkspaceConfig
```

在 `list_roi_accessible_datasource_ids()` 中读取当前管理空间的有效 ROI 配置，并加入候选集合：

```python
configured_ids = session.exec(
    select(CoreRoiWorkspaceConfig.datasource_id).where(
        CoreRoiWorkspaceConfig.tenant_id == context.management_tenant_id,
        CoreRoiWorkspaceConfig.deleted.is_(False),
    )
).all()
roi_config_ids = {int(value) for value in configured_ids if value is not None}

candidate_ids = workspace_ids | direct_ids | roi_config_ids
```

保留现有 `CoreDatasource.status` 过滤和 `has_roi_datasource_access()` 实现，不在 service/API 增加第二套角色例外。

- [ ] **Step 5: 更新服务层旧权限断言，使其符合管理员完整 ROI 权限**

在 `backend/tests/test_roi_dashboard_service.py` 中完成以下行为调整：

1. `test_create_dashboard_requires_executable_roi_datasource` 的参数只保留
   `missing` 和 `inactive`；新增独立用例，验证有效 ROI 配置存在时，管理员无需
   `core_datasource_user` 也能创建 ROI 看板。
2. `test_chart_list_checks_permission_before_cache_and_keeps_structure_visible` 在删除账号级授权后，
   仍应命中 ROI 缓存，图表 `can_execute/can_edit` 继续为 `True`，并保留查询结果。
3. 将 `test_chart_writes_are_rejected_without_datasource_access` 改为验证管理员无账号级授权时，
   仍可按顺序执行创建、更新、排序和删除；查询执行器使用 `successful_query()`。
4. 将 `test_reorder_permission_wins_over_duplicate_error` 改为验证管理员无账号级授权时，
   重复排序项返回 `400`，而不是权限 `403`。

示例核心断言：

```python
def test_workspace_admin_can_create_dashboard_without_direct_datasource_grant(
    session: Session,
) -> None:
    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 101)
    seed_roi_config(session, tenant_id=11, datasource_id=101)

    created = create_roi_dashboard(
        session,
        user,
        RoiDashboardCreate(name="管理员 ROI"),
    )

    assert created.tenant_id == 11
    assert created.name == "管理员 ROI"
```

```python
assert cache.get_keys == [expected_key]
assert authorized[0]["can_execute"] is True
assert authorized[0]["can_edit"] is True
assert authorized[0]["query_result"]["data"] == [{"value": 9}]
```

```python
assert_http_error(400, lambda: reorder_roi_charts(session, user, 301, request))
```

- [ ] **Step 6: 运行 ROI 权限测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_roi_dashboard_permissions.py -q
```

Expected: 全部 `PASS`。重点确认：

- 当前空间管理员无需直接授权可访问配置数据源；
- 其他空间配置不泄漏；
- 已删除配置不授权；
- 非 `success` 数据源不授权；
- `member` 和平台管理员仍返回 403。

- [ ] **Step 7: 运行 ROI 服务/API/执行器回归测试**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  backend/tests/test_roi_dashboard_permissions.py `
  backend/tests/test_roi_dashboard_service.py `
  backend/tests/test_roi_dashboard_api.py `
  backend/tests/test_roi_dashboard_query_executor.py `
  backend/tests/test_tenant_roi_datasource_binding.py -q
```

Expected: 全部 `PASS`，无新增失败。

- [ ] **Step 8: 重启本地完整栈并验证 pengtong 的真实接口结果**

按仓库本地运行规范重启前端 `5173`、API `8000`、MCP `8001` 和一个使用同一 `local-*` 队列的 Worker。随后在 `backend` 目录执行以下只读验证脚本：

```powershell
@'
from datetime import timedelta
import httpx
from sqlmodel import Session, select
from apps.system.crud.tenant import attach_tenant_context, resolve_current_tenant
from apps.system.models.user import UserModel
from apps.system.schemas.system_schema import BaseUserDTO
from common.core.config import settings
from common.core.db import engine
from common.core.security import create_access_token

account = "pengtong@elex-tech.com"
flam_tenant_id = 7477202383789887488
with Session(engine) as session:
    record = session.exec(select(UserModel).where(UserModel.account == account)).first()
    user = BaseUserDTO.model_validate(record.model_dump())
    tenant = resolve_current_tenant(session, user, requested_tenant_id=flam_tenant_id)
    user = attach_tenant_context(user, tenant)
    token = create_access_token(
        user.to_dict(),
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

headers = {
    settings.TOKEN_KEY: f"Bearer {token}",
    "X-SHUZHI-TENANT-ID": str(flam_tenant_id),
}
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
    config = client.get("/api/v1/dashboard/roi/config", headers=headers)
    dashboards = client.get("/api/v1/dashboard/roi/list", headers=headers)
    print(config.status_code, config.json())
    print(dashboards.status_code, dashboards.json())
'@ | .\.venv\Scripts\python.exe -
```

Expected:

- `/api/v1/dashboard/roi/config` 返回 `200`；
- `datasource_id` 为 `7`；
- `can_execute` 为 `true`；
- `can_edit` 为 `true`；
- `/api/v1/dashboard/roi/list` 返回包含 `ROI` 看板；
- 数据库中不新增 `pengtong@elex-tech.com` 对数据源 `7` 的 `core_datasource_user` 记录。

- [ ] **Step 9: 提交实现**

只暂存本任务文件，保留工作区其他未提交改动：

```powershell
git add -- backend/apps/roi_dashboard/permissions.py backend/tests/test_roi_dashboard_permissions.py backend/tests/test_roi_dashboard_service.py
git diff --cached --stat
git commit -m "允许工作空间管理员访问已配置的 ROI 数据源"
```

Expected: 提交仅包含权限实现和对应测试。
