# Task 0：看板服务测试基线夹具修复报告

## 根因

`tests/test_dashboard_service.py` 的 `_engine_with_dashboard_permission_tables()` 使用 SQLite 手写构造看板权限相关表，但未随 ROI 工作空间配置查询链路补建 `core_roi_workspace_config`。`preview_sql()` 解析图表执行数据源时会调用 `get_roi_datasource_id_for_tenant()`，随后由 `list_roi_workspace_config_rows()` 查询该表，因此 9 个透视相关测试在到达业务断言前均因 SQLite 缺表失败。

## RED 命令及结果

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py -k "pivot or cache_key or payload" -q
```

结果：`9 failed, 2 passed, 73 deselected`。首个失败为 `sqlite3.OperationalError: no such table: core_roi_workspace_config`，调用链与任务简述一致。

## 修改内容

- 仅在 `_engine_with_dashboard_permission_tables()` 增加 SQLite 的 `core_roi_workspace_config` 测试表，列为当前查询所需的 `tenant_id`、`datasource_id`、`deleted`。
- 仅在 `_insert_dashboard_permission_fixture()` 增加租户 1 到数据源 1 的未删除 ROI 配置，使现有预览测试具备有效的图表执行数据源上下文。
- 未修改生产代码、数据库、迁移、看板 SQL 或测试数据；未暂存或覆盖 `frontend/auto-imports.d.ts`。

## GREEN 命令及结果

直接覆盖修改夹具的测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py::test_dashboard_preview_ignores_disabled_pivot -q
```

结果：`1 passed`（存在项目既有弃用警告）。

完整筛选基线复跑：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py -k "pivot or cache_key or payload" -q
```

结果：`1 failed, 10 passed, 73 deselected`。原先 9 个 `core_roi_workspace_config` 缺表失败均已消失。

## 提交 SHA

夹具修复提交：`590c31d3`（`修复看板服务测试夹具`）。

## 遗留问题

完整筛选基线剩余 `test_dashboard_preview_builds_pivot_sql`：该断言期望旧 SQL 形态 `FROM (SELECT * FROM orders WHERE ...)`，当前加载的后端实现生成 CTE `WITH "pivot_src" AS (...)`，故断言失败。该失败不再涉及测试夹具、SQLite 表或数据源上下文；按本任务“只修复测试夹具、不得改生产 SQL”的限制未处理。
