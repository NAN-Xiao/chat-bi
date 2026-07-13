# 字段权限禁止列表与数字 JSON 键实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将字段权限保存改为禁止列表，受限字段稳定置顶，并支持数字 JSON 对象键。

**Architecture:** 前端纯函数负责压缩保存载荷和稳定排序；公共 JSON path 规范化负责数字键 canonical form；字段列表和运行时方言编译复用规范形式。后端权限判定语义不变。

**Tech Stack:** Vue 3、TypeScript、Node assert、FastAPI、sqlglot、pytest

## Global Constraints

- 只保存 `enable=false` 的字段权限。
- 未保存字段表示允许访问。
- 后端继续严格校验，不增加静默跳过。
- 不修改现有业务权限数据或运行数据库元数据。

---

### Task 1: 前端禁止列表与稳定置顶

**Files:**
- Modify: `frontend/src/views/system/permission/permissionFieldEntries.ts`
- Modify: `frontend/src/views/system/permission/index.vue`
- Test: `frontend/scripts/check-permission-json-subfields.mjs`

**Interfaces:**
- `permissionRulesToSaveEntries(entries)`：`column` 仅返回受限字段。
- `sortPermissionEntriesRestrictedFirst(entries)`：返回稳定排序副本，不修改输入。

- [x] 增加失败断言：允许字段不保存、受限字段保存、受限字段稳定置顶且不修改输入。
- [x] 运行 `npm run test:permission-json-fields`，确认因现有行为失败。
- [x] 实现两个纯函数并在 `tableColumnData` 中接入排序。
- [x] 重新运行前端专项测试并确认通过。

### Task 2: 数字 JSON 键统一规范化

**Files:**
- Modify: `backend/common/sql_json_paths.py`
- Modify: `backend/apps/system/crud/tracking_expression.py`
- Modify: `backend/apps/datasource/api/datasource.py`
- Test: `backend/tests/test_sql_json_paths.py`
- Test: `backend/tests/test_sql_engine_context.py`
- Test: `tests/test_datasource_permission_roles.py`

**Interfaces:**
- `normalize_json_path('$.1001') -> '$["1001"]'`
- `compile_tracking_json_expression(...)` 使用 canonical JSON path。
- `_tracking_json_path(...)` 向前端返回 canonical JSON path。

- [x] 增加失败测试：数字键规范化、三种方言表达式、数字键权限保存。
- [x] 运行对应 pytest，确认现有实现失败。
- [x] 扩展公共 path parser，并让字段列表与表达式编译复用规范形式。
- [x] 运行对应 pytest 并确认通过。

### Task 3: 全量验证

**Files:**
- Verify only

- [x] 运行 `npm run test:permission-json-fields`。
- [x] 运行 `npm run build`。
- [x] 运行 `pytest backend/tests/test_sql_json_paths.py tests/test_datasource_permission_roles.py backend/tests/test_sql_engine_context.py tests/test_chat_permission_boundaries.py tests/test_dashboard_service.py -q`。
- [x] 用真实 `flam` 字段列表在只读会话中构造保存载荷，确认仅 `personal.money` 进入禁止列表，数字键可单独通过规范化校验。
- [x] 请求独立代码审查并处理高优先级问题。
