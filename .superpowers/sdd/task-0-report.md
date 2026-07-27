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
- `_insert_dashboard_permission_fixture()` 保留租户 1 到数据源 1 的 ROI 配置测试数据，以满足默认租户 1 的图表执行数据源解析。
- `test_dashboard_preview_builds_pivot_sql` 仅在自身作用域 monkeypatch `_configured_chart_execution_datasources()` 为 `[(1, "bound")]`。这使该测试在保留默认租户解析夹具的同时，明确验证普通绑定数据源的真实行权限注入路径，不会影响其他 ROI 配置相关测试。
- 未修改生产代码、数据库、迁移或看板 SQL；未暂存或覆盖 `frontend/auto-imports.d.ts`。

## GREEN 命令及结果

直接覆盖缺表夹具的测试：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py::test_dashboard_preview_ignores_disabled_pivot -q
```

结果：`1 passed`（存在项目既有弃用警告）。

完整筛选基线复跑：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py -k "pivot or cache_key or payload" -q
```

结果：`11 passed, 73 deselected`（存在项目既有弃用警告）。

## 提交 SHA

夹具修复提交：`590c31d3`（`修复看板服务测试夹具`）。

## 复审修复补充

### RED

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py::test_dashboard_preview_builds_pivot_sql -q
```

结果：`1 failed`。生成 SQL 的 `pivot_src` 未出现 `FROM (SELECT * FROM orders WHERE ...)` 或 `region <> 'EU'` 行权限谓词。原因是该测试既需要默认租户 1 的 ROI 配置来通过执行数据源解析，又需要验证普通绑定数据源的行权限路径；直接使用配置解析结果会将数据源 1 归类为 ROI。

### GREEN

在该单测内局部固定数据源角色为 `bound` 后：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py::test_dashboard_preview_builds_pivot_sql -q
```

结果：`1 passed`，原断言确认生成 SQL 恢复包含 `FROM (SELECT * FROM orders WHERE ...)` 与 `region <> 'EU'` 行权限谓词。

随后重新执行完整筛选基线：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_service.py backend/tests/test_dashboard_permission_cache.py -k "pivot or cache_key or payload" -q
```

结果：`11 passed, 73 deselected`（存在项目既有弃用警告）。

## 遗留问题

无。本任务范围内的基线筛选已全部通过。
