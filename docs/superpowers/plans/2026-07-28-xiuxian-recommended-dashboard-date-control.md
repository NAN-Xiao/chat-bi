# 修仙推荐看板抽屉日期控件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为修仙空间推荐看板中可安全参数化的 SQL 抽屉提供默认“最近 30 天”的日期控件。

**Architecture:** 新增一个仅定位修仙租户、绑定数据源及 `default` 推荐树的迁移脚本。脚本仅把具有唯一、非实时、非成熟期分区日期窗口的 SQL 改造成平台已支持的日期参数，并同步写入图表日期表达式配置；写入使用完整画布 CAS、备份和读回校验。

**Tech Stack:** Python 3、psycopg、PostgreSQL、pytest、既有看板日期表达式协议。

## Global Constraints

- 默认命令只能预演，只有 `--apply` 可以写入系统数据库。
- 目标范围必须同时满足修仙租户、修仙数据源和 `core_dashboard_tree.scope = 'default'`。
- 仅普通 SQL 图表可启用；外部 MCP、实时表、多窗口、cohort/留存/LTV/成熟期和无 SQL 图表必须跳过。
- 默认表达式固定为 `{"version": 1, "mode": "preset", "preset": "past_30_days"}`。
- 不得引入任何按“修仙”名称判断的前端分支；复用既有 `DashboardDateExpressionPicker` 与执行接口。
- 备份文件写入 `.codex-runtime`，不得提交。

---

## 文件结构

- 新增 `tools/enable_xiuxian_recommended_dashboard_date_filters.py`：候选 SQL 识别与替换、画布迁移、备份、CAS 更新、读回验证、回滚 CLI。
- 新增 `backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py`：候选规则、配置保真、目标范围、CAS 和回滚前置条件测试。
- 复用 `tools/xiuxian_dashboard_snapshot.py`：修仙租户、数据源、推荐看板和目录抽屉数量门禁，不修改其备份格式。

### Task 1: 锁定候选 SQL 和日期表达式协议

**Files:**

- Create: `backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py`
- Create: `tools/enable_xiuxian_recommended_dashboard_date_filters.py`

**Interfaces:**

- Produces: `is_safe_candidate(sql: str) -> bool`、`replace_unique_partition_range(sql: str) -> str`、`configure_view(view: dict[str, Any]) -> dict[str, Any]`。

- [ ] **Step 1: 写入失败测试**

```python
def test_configure_view_replaces_one_dt_window_and_preserves_metadata():
    original = {
        "sql": _partition_sql(),
        "chart": {"title": "趋势", "xAxis": [{"value": "日期"}]},
        "sourceConfig": {"sql": {"keep": "value"}},
        "pivot": {"enabled": False, "keep": "value"},
    }
    migrated = migration.configure_view(original)
    assert original["sql"] == _partition_sql()
    assert migrated["sql"].count(migration.START_TOKEN) == 1
    assert migrated["sql"].count(migration.END_TOKEN) == 1
    assert migrated["sourceConfig"]["sql"]["keep"] == "value"
    assert migrated["pivot"]["keep"] == "value"
    assert migrated["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION

@pytest.mark.parametrize("sql", [
    "SELECT * FROM event_realtime WHERE dt BETWEEN 20260701 AND 20260702",
    _partition_sql() + " -- retention cohort d7",
    _partition_sql() + " AND e.dt BETWEEN 20260701 AND 20260702",
    "SELECT 1",
])
def test_is_safe_candidate_rejects_unsupported_sql(sql):
    assert migration.is_safe_candidate(sql) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py -q`

Expected: FAIL，提示缺少 `enable_xiuxian_recommended_dashboard_date_filters` 模块。

- [ ] **Step 3: 实现候选识别和配置**

```python
DEFAULT_EXPRESSION = {"version": 1, "mode": "preset", "preset": "past_30_days"}
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"

def configure_view(view: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    result["sql"] = replace_unique_partition_range(str(result.get("sql") or ""))
    time_field = _date_field(result)
    builder = result.setdefault("sourceConfig", {}).setdefault("sql", {}).setdefault("builder", {})
    builder.update({"dateExpressionPickerEnabled": True, "timeField": time_field,
                    "timeRange": "expression", "timeExpression": copy.deepcopy(DEFAULT_EXPRESSION)})
    pivot = result.setdefault("pivot", {})
    pivot.update({"time_field": time_field, "range_enabled": True,
                  "client_filter_only": False, "date_parameter_type": "yyyymmdd_number",
                  "date_expression": copy.deepcopy(DEFAULT_EXPRESSION)})
    return result
```

`is_safe_candidate` 必须要求恰好一个 `<alias>.dt BETWEEN ... AND ...` 窗口，拒绝已有日期参数、`event_realtime`、多于两个当前日期函数和测试列举的语义；`replace_unique_partition_range` 只替换该窗口并保留后续 SQL 的分隔空白。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py -q`

Expected: PASS。

- [ ] **Step 5: 提交候选规则**

```powershell
git add backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py tools/enable_xiuxian_recommended_dashboard_date_filters.py
git commit -m "功能：识别修仙看板日期筛选候选"
```

### Task 2: 实现画布迁移和保真验证

**Files:**

- Modify: `tools/enable_xiuxian_recommended_dashboard_date_filters.py`
- Modify: `backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py`

**Interfaces:**

- Consumes: Task 1 的 `is_safe_candidate` 与 `configure_view`。
- Produces: `migrate_canvas(canvas: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, str]]` 和 `verify_canvas(canvas: dict[str, Any], *, target_ids: list[str], unchanged: dict[str, str]) -> dict[str, Any]`。

- [ ] **Step 1: 写入失败的保真测试**

```python
def test_migrate_canvas_changes_only_safe_drawers():
    canvas = {
        "safe": _view(_partition_sql()),
        "realtime": _view("SELECT * FROM event_realtime WHERE dt BETWEEN 20260701 AND 20260702"),
        "cohort": _view(_partition_sql() + " -- retention d7"),
    }
    migrated, target_ids, unchanged = migration.migrate_canvas(canvas)
    assert target_ids == ["safe"]
    assert migrated["safe"]["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION
    assert migration.stable_json_hash(migrated["realtime"]) == unchanged["realtime"]
    assert migration.stable_json_hash(migrated["cohort"]) == unchanged["cohort"]
    assert migration.verify_canvas(migrated, target_ids=target_ids, unchanged=unchanged)["safe"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py -q`

Expected: FAIL，提示缺少 `migrate_canvas` 或 `verify_canvas`。

- [ ] **Step 3: 实现画布迁移和验证**

```python
def migrate_canvas(canvas: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    migrated = copy.deepcopy(canvas)
    target_ids = [chart_id for chart_id, view in canvas.items()
                  if isinstance(view, dict) and is_safe_candidate(str(view.get("sql") or ""))]
    unchanged = {chart_id: stable_json_hash(view) for chart_id, view in canvas.items()
                 if chart_id not in target_ids}
    for chart_id in target_ids:
        migrated[chart_id] = configure_view(migrated[chart_id])
    return migrated, target_ids, unchanged
```

`verify_canvas` 必须检查每个目标 SQL 恰有一对日期参数、构建器和 `pivot` 都保存 `DEFAULT_EXPRESSION`，并逐个比对所有非目标抽屉的稳定哈希；任一不符抛出中文 `RuntimeError`。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py -q`

Expected: PASS。

- [ ] **Step 5: 提交画布迁移**

```powershell
git add backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py tools/enable_xiuxian_recommended_dashboard_date_filters.py
git commit -m "功能：迁移修仙推荐看板日期控件"
```

### Task 3: 加入数据库预演、备份、CAS 写入、读回和回滚

**Files:**

- Modify: `tools/enable_xiuxian_recommended_dashboard_date_filters.py`
- Modify: `backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py`

**Interfaces:**

- Consumes: Task 2 的迁移函数、`core_system_db.core_system_db_config()`、`xiuxian_dashboard_snapshot.TENANT_ID`、`DATASOURCE_ID`、`EXPECTED_VIEW_IDS`。
- Produces: `_select_recommended_dashboards(cur: Any, *, lock: bool) -> list[dict[str, Any]]`、`_select_recommended_dashboard(cur: Any, dashboard_id: str, *, lock: bool) -> dict[str, Any]`、`migrate_recommended_dashboards(*, apply: bool) -> dict[str, Any]`、`verify_recommended_dashboards() -> dict[str, Any]`、`restore_dashboards(backup_path: Path) -> dict[str, Any]` 和 `--apply`、`--verify`、`--restore` CLI。

- [ ] **Step 1: 写入失败的范围和回滚测试**

```python
def test_select_recommended_dashboards_is_scoped_to_xiuxian_default_tree(fake_cursor):
    migration._select_recommended_dashboards(fake_cursor, lock=False)
    normalized = " ".join(fake_cursor.sql.split()).upper()
    assert "CORE_DASHBOARD_TREE" in normalized
    assert "T.SCOPE = 'DEFAULT'" in normalized
    assert fake_cursor.params == (migration.TENANT_ID, migration.DATASOURCE_ID)

def test_restore_refuses_when_current_canvas_does_not_match_migrated_hash(tmp_path, monkeypatch):
    backup = _backup_payload(tmp_path, old_canvas="{}", new_canvas="{\"changed\":true}")
    monkeypatch.setattr(migration, "_select_recommended_dashboard", lambda *args, **kwargs: {"canvas_view_info": "{}"})
    with pytest.raises(RuntimeError, match="回滚 CAS 哈希不匹配"):
        migration.restore_dashboards(backup)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py -q`

Expected: FAIL，提示缺少数据库范围或回滚函数。

- [ ] **Step 3: 实现安全迁移 CLI**

```python
def migrate_recommended_dashboards(*, apply: bool) -> dict[str, Any]:
    plans = _build_migration_plans(lock=apply)
    if not apply:
        return _preview_result(plans)
    backups = _write_backups(plans)
    _apply_all_with_canvas_cas(plans)
    return _readback_and_verify(plans, backups)
```

查询必须联结 `core_dashboard_tree` 并限制修仙租户、修仙数据源、`scope = 'default'`、叶子节点、推荐状态和未删除状态；只接收 `EXPECTED_VIEW_IDS` 中的抽屉。每个更新必须以原 `canvas_view_info` 作为 `WHERE` 条件并校验影响行数为 1。备份记录看板、租户、数据源、旧新画布 SHA-256 与完整原始行；读回失败必须报出可直接执行的 `--restore` 命令。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py tests/test_xiuxian_dashboard_snapshot.py -q`

Expected: PASS。

- [ ] **Step 5: 提交安全迁移接口**

```powershell
git add backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py tools/enable_xiuxian_recommended_dashboard_date_filters.py
git commit -m "功能：安全启用修仙推荐看板日期控件"
```

### Task 4: 执行现场预演、应用与最终验证

**Files:**

- Modify: `.codex-runtime/xiuxian-dashboard-date-expression-backups/*`（运行时备份，不提交）

**Interfaces:**

- Consumes: Task 3 的 CLI 和修仙系统数据库配置。
- Produces: 预演输出、备份路径、读回验证结果。

- [ ] **Step 1: 执行只读预演**

Run: `backend\\.venv\\Scripts\\python.exe tools/enable_xiuxian_recommended_dashboard_date_filters.py`

Expected: `applied` 为 `false`；输出仅含修仙推荐树范围内的候选看板、抽屉和预计日期参数数量；没有数据库写入。

- [ ] **Step 2: 复核预演范围与 SQL 语义**

每个候选必须在修仙推荐看板内、属于目录登记的 SQL 抽屉，且不含 `event_realtime`、多日期窗口或成熟期语义。若任一项不满足，停止，不执行 `--apply`，修正候选规则后从 Task 1 重新开始。

- [ ] **Step 3: 应用并读回验证**

Run: `backend\\.venv\\Scripts\\python.exe tools/enable_xiuxian_recommended_dashboard_date_filters.py --apply`

Expected: 每个更新返回备份路径；每张看板 CAS 更新恰好一行；读回验证所有目标图表的日期参数、`past_30_days` 配置和非目标抽屉哈希。

- [ ] **Step 4: 执行显式验证**

Run: `backend\\.venv\\Scripts\\python.exe tools/enable_xiuxian_recommended_dashboard_date_filters.py --verify`

Expected: 验证结果全部通过。

- [ ] **Step 5: 前端冒烟检查并提交**

在修仙空间打开推荐看板抽屉：已迁移 SQL 图表显示日期控件，初始值为“最近 30 天”；切换日期并点击“应用”后图表刷新；不支持图表不显示控件。随后仅暂存脚本与测试：

```powershell
git add backend/tests/test_enable_xiuxian_recommended_dashboard_date_filters.py tools/enable_xiuxian_recommended_dashboard_date_filters.py
git commit -m "功能：为修仙推荐看板添加日期控件"
```
