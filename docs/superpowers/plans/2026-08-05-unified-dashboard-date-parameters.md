# 统一看板日期参数规则 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让看板日期参数统一支持仅开始、仅结束和完整区间，并移除 `event_realtime` 的日期范围特殊限制。

**Architecture:** 前端配置归一化与后端日期准备使用相同的 token 集合契约。后端只根据参数类型、SQL 中实际 token 和日期表达式渲染 SQL，不再根据物理表名改变能力状态；普通看板和聊天执行继续复用共享日期准备服务。

**Tech Stack:** Vue 3、TypeScript、Node.js contract tests、Python 3.11、FastAPI/SQLModel、pytest。

## Global Constraints

- 合法 token 集合必须是 `{start}`、`{end}` 或 `{start, end}`。
- 不允许混合不同日期参数家族。
- 不根据 `event_realtime` 表名限制日期范围，也不回退到其他物理表。
- 保留现有日期表达式、权限、只读 SQL、缓存和并发控制边界。
- 所有代码和测试修改必须位于独立 worktree `D:\AIWork3\chat-bi\.worktrees\codex-unified-dashboard-date-parameters`。

---

### Task 1: 统一前端日期 token 配置校验

**Files:**
- Modify: `frontend/src/views/dashboard/utils/dashboardChartConfig.ts:30-37`
- Test: `frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs:13-16`

**Interfaces:**
- Consumes: `scanDashboardDateParameterTokens(sql: string): string[]` 和 `dashboardDateParameterTokens[parameterType]`。
- Produces: `hasMatchingTokens(sql, parameterType)` 对三种合法 token 集合返回 `true`。

- [ ] **Step 1: 写仅开始参数的失败测试**

在现有 `endOnlySql` 旁增加：

```javascript
const startOnlySql = 'select * from orders where stat_date >= {{dashboard_start_date}}'
```

并增加 V2 配置归一化断言：

```javascript
const startOnly = normalizeDashboardChartConfig({
  sql: startOnlySql,
  configVersion: 2,
  dateFilter: {
    enabled: true,
    parameterType: 'date',
    expression,
  },
  pivot: { enabled: false },
})
assert.equal(startOnly.dateFilter.parameterType, 'date')
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `node frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs`

Expected: 因 `DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED` 失败，证明当前实现拒绝仅开始 token。

- [ ] **Step 3: 最小修改 token 匹配逻辑**

将仅结束判断改为任一单边 token：

```typescript
const isSingleBoundary = activeTokens.length === 1
  && (expectedTokens as readonly string[]).includes(activeTokens[0])
return isCompleteRange || isSingleBoundary
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `node frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs`

Expected: exit code 0。

- [ ] **Step 5: 提交前端契约修改**

```powershell
git add -- frontend/src/views/dashboard/utils/dashboardChartConfig.ts frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs
git commit -m "修复：允许单边看板日期参数"
```

---

### Task 2: 统一后端校验、渲染和执行链

**Files:**
- Modify: `backend/apps/dashboard/crud/dashboard_date_filter.py:301-450`
- Modify: `backend/apps/chat/service/chat_date_filter.py:167-186`
- Modify: `backend/apps/dashboard/crud/dashboard_service.py:1959-1975,4061-4071,5357-5364`
- Test: `backend/tests/test_dashboard_permission_cache.py:37-86`
- Test: `backend/tests/test_chat_dashboard_date_filter.py:20-30,194-224`

**Interfaces:**
- Consumes: `validate_dashboard_date_parameter_sql(sql: str, parameter_type: str) -> str | None`。
- Produces: `prepare_dashboard_date_filter(...) -> DashboardDateFilterPreparation` 对普通表和 `event_realtime` 使用相同行为；普通看板和聊天不再返回实时表日期限制错误。

- [ ] **Step 1: 把仅开始参数测试改成合法并验证渲染**

将拒绝测试替换为：

```python
def test_date_parameter_sql_accepts_start_only_mode() -> None:
    assert validate_dashboard_date_parameter_sql(
        "select * from event where dt >= {{dashboard_start_yyyymmdd}}",
        "yyyymmdd_number",
    ) is None
```

增加渲染测试：

```python
@pytest.mark.parametrize("table_name", ["event", "event_realtime"])
def test_start_only_date_filter_renders_identically_for_all_tables(table_name: str) -> None:
    pivot = DashboardPivotRequest(time_field="dt")
    date_filter = DashboardDateFilterRequest(parameter_type="yyyymmdd_number")
    prepared = prepare_dashboard_date_filter(
        f"select * from `{table_name}` where dt >= {{{{dashboard_start_yyyymmdd}}}}",
        ds_type="mysql",
        pivot=pivot,
        date_filter=date_filter,
        today=date(2026, 7, 29),
    )
    assert prepared.capability["status"] == "available"
    assert "20260715" in prepared.sql
    assert "{{dashboard_start_yyyymmdd}}" not in prepared.sql
```

在聊天测试中新增开始单边 SQL：

```python
REALTIME_DATE_START_ONLY_SQL = (
    "SELECT * FROM event_realtime WHERE dt >= {{dashboard_start_yyyymmdd}}"
)
```

将历史范围、仅结束测试改为断言渲染结果，并增加仅开始测试：

```python
def test_render_allows_historical_range_for_realtime_table():
    sql = render_chat_date_filter_sql(
        REALTIME_DATE_TEMPLATE_SQL,
        "mysql",
        {"enabled": False, **DATE_FILTER},
        today=date(2026, 8, 4),
    )
    assert "20260728" in sql
    assert "20260803" in sql


@pytest.mark.parametrize(
    ("sql_template", "expected_date"),
    [
        (REALTIME_DATE_START_ONLY_SQL, "20260804"),
        (REALTIME_DATE_END_ONLY_SQL, "20260804"),
    ],
)
def test_render_allows_single_boundary_filter_for_realtime_table(
    sql_template: str,
    expected_date: str,
):
    sql = render_chat_date_filter_sql(
        sql_template,
        "mysql",
        {"enabled": False, **TODAY_DATE_FILTER},
        today=date(2026, 8, 4),
    )
    assert expected_date in sql
    assert "{{dashboard_" not in sql
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_permission_cache.py backend/tests/test_chat_dashboard_date_filter.py -q`

Expected: 仅开始校验返回 `incomplete_parameters`，实时表历史范围和单边 SQL 仍返回 `realtime_table`。

- [ ] **Step 3: 放开三个合法 token 集合**

在 `validate_dashboard_date_parameter_sql` 中使用：

```python
allowed_token_sets = ({tokens[0]}, {tokens[1]}, set(tokens))
```

删除 `prepare_dashboard_date_filter` 的 `allow_realtime_current_day` 参数、`is_realtime` 判断、提前返回 `realtime_table` 的分支，以及解析日期表达式后的实时表当天完整区间限制。保留物理表解析与正常 token 替换。

`render_chat_date_filter_sql` 调用共享服务时删除：

```python
allow_realtime_current_day=True,
```

在 `dashboard_service.py` 删除 `_dashboard_has_explicit_date_range` 及普通看板批量加载、SQL 预览中的 `status == "realtime"` 拦截块。不得增加新的表名判断或兼容兜底。

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_permission_cache.py backend/tests/test_chat_dashboard_date_filter.py -q`

Expected: 全部通过。

- [ ] **Step 5: 验证生产路径不再包含日期实时表特例**

Run: `rg -n "allow_realtime_current_day|dashboard_date_filter_realtime|realtime_table" backend/apps/dashboard backend/apps/chat/service/chat_date_filter.py`

Expected: 无匹配。

- [ ] **Step 6: 提交后端统一规则修改**

```powershell
git add -- backend/apps/dashboard/crud/dashboard_date_filter.py backend/apps/chat/service/chat_date_filter.py backend/apps/dashboard/crud/dashboard_service.py backend/tests/test_dashboard_permission_cache.py backend/tests/test_chat_dashboard_date_filter.py
git commit -m "修复：统一看板日期参数规则"
```

---

### Task 3: 完整回归与交付检查

**Files:**
- Verify: `frontend/src/views/dashboard/utils/dashboardChartConfig.ts`
- Verify: `backend/apps/dashboard/crud/dashboard_date_filter.py`
- Verify: `backend/apps/dashboard/crud/dashboard_service.py`
- Verify: `backend/apps/chat/service/chat_date_filter.py`

**Interfaces:**
- Consumes: Tasks 1-2 的前后端统一日期契约。
- Produces: 可交付的测试与构建证据。

- [ ] **Step 1: 运行所有相关前端契约测试**

Run: `node frontend/src/views/dashboard/utils/dashboardChartConfig.test.mjs`

Expected: exit code 0。

- [ ] **Step 2: 运行后端相关回归**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_permission_cache.py backend/tests/test_chat_dashboard_date_filter.py backend/tests/test_dashboard_date_filter_migration.py backend/tests/test_dashboard_execution_datasource.py -q`

Expected: 全部通过。

- [ ] **Step 3: 运行前端构建**

Run: `npm run build`

Working directory: `frontend`

Expected: exit code 0；允许现有非阻断 warning，但不得出现 TypeScript 或 Vue 编译错误。

- [ ] **Step 4: 检查差异与工作区**

Run: `git diff --check`

Expected: 无输出，exit code 0。

Run: `git status --short --branch`

Expected: 只包含计划内文件；提交后工作区干净。
