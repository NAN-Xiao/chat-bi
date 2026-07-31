# 普通看板 ROI 数据源权限范围修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 修复普通看板使用 ROI 数据源时跳过当前用户表禁止和字段禁止的问题。

**Architecture:** 将 datasource_access_checked 限定为数据源可见性已由上游确认，不再让它控制用户 SQL 权限范围。预校验和实际执行都继续调用统一的 prepare_query_sql，并始终启用当前用户权限。

**Tech Stack:** Python、FastAPI、SQLModel/SQLAlchemy、pytest、SQLGlot

## Global Constraints

- ROI 数据源仍不要求用户额外获得通用数据源授权。
- 普通看板的表禁止、字段禁止和 deny_on_overlap 行权限策略必须继续生效。
- 不改变 ROI 专用看板执行器、权限规则数据、缓存键或数据源候选集。
- 不添加静默兼容回退。

---

### Task 1: 分离数据源授权与用户 SQL 权限

**Files:**
- Modify: backend/tests/test_dashboard_execution_datasource.py
- Modify: backend/apps/datasource/crud/sql_engine_executor.py
- Test: backend/tests/test_dashboard_permission_cache.py
- Test: backend/tests/test_sql_engine_context.py
- Test: backend/tests/test_roi_dashboard_query_executor.py

**Interfaces:**
- Consumes: validate_user_query_sql_or_raise(..., datasource_access_checked: bool)、execute_user_query_or_raise(..., datasource_access_checked: bool)。
- Produces: datasource_access_checked=True 只跳过 has_datasource_access，传给 prepare_query_sql 的 apply_user_permission_scope 恒为 True。

- [x] **Step 1: 修改契约测试并增加实际执行覆盖**

将原有跳过权限范围的断言改为 apply_user_permission_scope=True。增加实际执行入口测试，替换数据库执行函数并断言 prepare_query_sql 收到 apply_user_permission_scope=True，同时确认 has_datasource_access 不会阻断已由工作空间确认的 ROI 数据源。

- [x] **Step 2: 运行测试确认 RED**

Run: cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_execution_datasource.py -q

Expected: FAIL，两个入口实际收到的 apply_user_permission_scope 为 False。

- [x] **Step 3: 实现最小修复**

在 validate_user_query_sql_or_raise 和 execute_user_query_or_raise 调用 prepare_query_sql 时设置 apply_user_permission_scope=True，保留数据源访问判断不变。

- [x] **Step 4: 运行专项测试确认 GREEN**

Run: cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_execution_datasource.py -q

Expected: PASS。

- [x] **Step 5: 运行权限与 ROI 回归测试**

Run: cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_permission_cache.py tests/test_sql_engine_context.py tests/test_roi_dashboard_query_executor.py tests/test_roi_table_permission_management.py -q

Expected: PASS，普通看板缓存权限、普通 SQL 权限和 ROI 专用执行行为均无回归。

- [x] **Step 6: 检查差异**

Run: git diff --check

Expected: 无输出且退出码为 0；差异只包含本任务测试、执行器和已确认文档。
