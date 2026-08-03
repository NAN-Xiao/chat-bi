# Core Dashboard Metric Date Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将修仙、flam、模板_修仙三个空间的“核心看板”指标卡迁移到 `DashboardDateExpressionPicker`，并默认使用“昨日”。

**Architecture:** 共享前端增加一个持久化的、领域无关的指标卡日期表达式开关；只有显式启用的指标卡突破当前 `metric` 排除规则。一个默认只读、带备份/CAS/回滚的迁移脚本只处理三个已知 tenant 与“核心看板”目标，参数化指标卡 SQL 并写入“昨日”日期表达式；现有核心看板生成脚本同步产出同一配置。

**Tech Stack:** Vue 3、TypeScript、Element Plus、Node `node:test`/断言测试、Python 3、pytest、psycopg、PostgreSQL JSON 配置。

## Global Constraints

- 只修改修仙、flam、模板_修仙三个空间中名称为“核心看板”的现有指标卡。
- 不在共享运行时代码中硬编码空间名、数据源名、业务字段或指标名称。
- 未显式启用的指标卡和其他空间保持当前行为。
- 默认日期表达式固定为 `{ "version": 1, "mode": "preset", "preset": "yesterday" }`。
- 日期控件必须通过平台看板日期参数实际影响 SQL。
- 数据迁移必须默认只读预演，写入前备份，使用事务、行锁和 CAS，写入后重新读取验证，并提供回滚入口。
- 保留旧版 `el-date-picker` 分支，不迁移普通表单、MCP 日期参数或透视配置日期输入。
- 保留工作区现有未提交改动，不覆盖或回退用户文件。

---

### Task 1: 指标卡显式启用新版日期控件

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs`

**Interfaces:**
- Consumes: `sourceConfig.sql.builder.metricDateExpressionEnabled?: boolean`
- Produces: `shouldUseDashboardDateParameters(chartType)` 在非指标卡有时间字段时保持现状；指标卡仅在 `metricDateExpressionEnabled === true` 且有时间字段时返回 `true`。
- Produces: `builderConfigForSave()` 持久化 `metricDateExpressionEnabled`。

- [ ] **Step 1: 写失败测试**

在 `DashboardSqlEditor.date-expression.test.mjs` 中断言：

```js
assert.match(source, /metricDateExpressionEnabled:\s*false/)
assert.match(
  source,
  /chartType\s*!==\s*'metric'\s*\|\|\s*sqlBuilder\.metricDateExpressionEnabled\s*===\s*true/,
)
assert.match(source, /metricDateExpressionEnabled:\s*sqlBuilder\.metricDateExpressionEnabled\s*===\s*true/)
assert.match(source, /sqlBuilder\.metricDateExpressionEnabled\s*=\s*value\.metricDateExpressionEnabled\s*===\s*true/)
```

- [ ] **Step 2: 验证测试按预期失败**

Run: `node frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs`

Expected: FAIL，因为 `metricDateExpressionEnabled` 尚不存在。

- [ ] **Step 3: 实现最小通用能力**

在 SQL builder 状态中增加：

```ts
metricDateExpressionEnabled: false,
```

将日期参数判断收敛为：

```ts
function shouldUseDashboardDateParameters(chartType: ChartTypes | string = form.chartType) {
  const supportsConfiguredMetric =
    chartType !== 'metric' || sqlBuilder.metricDateExpressionEnabled === true
  return supportsConfiguredMetric && Boolean(sqlBuilder.timeField)
}
```

在 reset、restore 和 save 中分别恢复默认 `false`、读取严格布尔值、持久化严格布尔值。不得根据标题、空间或字段名推断启用。

- [ ] **Step 4: 运行目标测试与相邻日期测试**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
```

Expected: 三个命令均退出码 `0`。

### Task 2: 三空间核心看板迁移脚本

**Files:**
- Create: `tools/migrate_core_dashboard_metric_date_picker.py`
- Create: `backend/tests/test_migrate_core_dashboard_metric_date_picker.py`

**Interfaces:**
- Produces: `YESTERDAY_EXPRESSION: dict[str, Any]`
- Produces: `parameterize_metric_sql(sql: str, parameter_type: str) -> str`
- Produces: `migrate_metric_view(view: dict[str, Any], *, time_field: str, parameter_type: str) -> dict[str, Any]`
- Produces: `migrate_dashboard(*, apply: bool) -> dict[str, Any]`
- CLI: dry-run by default; `--apply`, `--verify`, `--restore <backup>`。

- [ ] **Step 1: 写迁移纯函数失败测试**

覆盖以下行为：

```python
def test_migrate_metric_view_enables_yesterday_expression():
    migrated = migration.migrate_metric_view(
        metric_view(), time_field="event.dt", parameter_type="yyyymmdd_number"
    )
    builder = migrated["sourceConfig"]["sql"]["builder"]
    assert builder["metricDateExpressionEnabled"] is True
    assert builder["dateExpressionPickerEnabled"] is True
    assert builder["timeRange"] == "expression"
    assert builder["timeExpression"] == migration.YESTERDAY_EXPRESSION
    assert migrated["pivot"]["date_expression"] == migration.YESTERDAY_EXPRESSION
    assert "{{dashboard_start_yyyymmdd}}" in migrated["sql"]
    assert "{{dashboard_end_yyyymmdd}}" in migrated["sql"]
```

另测：非 metric 拒绝迁移、未知 SQL 日期模式拒绝迁移、重复执行幂等、输入对象不被原地修改、非目标图表保持不变。

- [ ] **Step 2: 验证纯函数测试失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_migrate_core_dashboard_metric_date_picker.py -q`

Expected: FAIL，因为迁移模块尚不存在。

- [ ] **Step 3: 实现纯函数和严格目标清单**

目标清单用 tenant ID 与 dashboard ID 锁定三份核心看板；从数据库基线读取并在测试中固定 12 个目标 chart ID、标题、SQL 哈希和 time field。迁移函数必须：

```python
YESTERDAY_EXPRESSION = {"version": 1, "mode": "preset", "preset": "yesterday"}
```

将支持的固定单日条件替换为开始/结束日期参数范围，更新 `sourceConfig.sql.builder`、`pivot.date_expression`、日期参数类型和时间字段。任何未知模式、缺失目标或身份变化必须抛错，不做部分迁移。

- [ ] **Step 4: 写数据库边界失败测试**

通过假 cursor/monkeypatch 验证：dry-run 不 UPDATE、`--apply` 先备份再 CAS 更新、rowcount 非 1 拒绝、读回 SQL/config 不一致拒绝、restore 只接受匹配的备份所有权和哈希。

- [ ] **Step 5: 实现事务、备份、CAS、验证和回滚**

备份写入 `.codex-runtime/core-dashboard-metric-date-picker-backups/`，保存旧/新哈希与完整目标行。每个目标看板在同一事务中 `FOR UPDATE`，所有基线验证通过后才更新；任意失败整体回滚。写入提交后用新连接读回 12 个目标并验证，输出逐空间/看板/图表摘要与回滚命令。

- [ ] **Step 6: 运行迁移脚本测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_migrate_core_dashboard_metric_date_picker.py -q`

Expected: 全部通过。

### Task 3: 同步核心看板生成器

**Files:**
- Modify: `tools/add_xiuxian_core_dashboard_realtime_metrics.py`
- Modify: `backend/tests/test_add_xiuxian_core_dashboard_realtime_metrics.py`
- Modify: flam 核心看板实际生成这四个指标卡的既有脚本（通过搜索 `METRIC_SPECS`/目标 chart ID 确认准确文件后，仅改配置构造函数）
- Modify: 模板_修仙核心看板实际生成/快照脚本（通过目标 dashboard/chart ID 确认准确文件后，仅改指标卡构造函数）
- Test: 对应现有 pytest 文件；若没有独立测试则在 `backend/tests/test_migrate_core_dashboard_metric_date_picker.py` 增加生成器契约测试。

**Interfaces:**
- Consumes: 与 Task 2 相同的 builder/pivot 配置契约。
- Produces: 后续重建的目标指标卡仍含 `metricDateExpressionEnabled = true` 与 `yesterday` 表达式，SQL 使用看板日期参数。

- [ ] **Step 1: 写生成器失败测试**

对每个生成器输出的四个核心指标卡断言：

```python
assert view["sourceConfig"]["sql"]["builder"]["metricDateExpressionEnabled"] is True
assert view["sourceConfig"]["sql"]["builder"]["timeExpression"] == YESTERDAY_EXPRESSION
assert view["pivot"]["date_expression"] == YESTERDAY_EXPRESSION
assert "{{dashboard_start_" in view["sql"]
assert "{{dashboard_end_" in view["sql"]
```

- [ ] **Step 2: 运行测试并确认因旧生成配置失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_add_xiuxian_core_dashboard_realtime_metrics.py backend/tests/test_migrate_core_dashboard_metric_date_picker.py -q`

Expected: 新增断言 FAIL。

- [ ] **Step 3: 最小修改生成器配置**

复用或等价实现 Task 2 的日期配置契约，只修改目标指标卡构造路径。处理工作区已有未提交改动时，保留其 SQL、Data Skill 和快照内容，不回退不相关变更。

- [ ] **Step 4: 运行生成器和迁移测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_add_xiuxian_core_dashboard_realtime_metrics.py backend/tests/test_migrate_core_dashboard_metric_date_picker.py -q`

Expected: 全部通过。

### Task 4: 预演、备份和应用数据库迁移

**Files:**
- Runtime backup only: `.codex-runtime/core-dashboard-metric-date-picker-backups/`

**Interfaces:**
- Consumes: `tools/migrate_core_dashboard_metric_date_picker.py`
- Produces: 三个目标核心看板的 12 个指标卡已迁移；输出可执行回滚命令。

- [ ] **Step 1: 执行只读预演**

Run: `backend\.venv\Scripts\python.exe tools/migrate_core_dashboard_metric_date_picker.py`

Expected: `applied=false`，正好 3 个看板、12 个指标卡；无数据库写入。

- [ ] **Step 2: 执行应用迁移**

Run: `backend\.venv\Scripts\python.exe tools/migrate_core_dashboard_metric_date_picker.py --apply`

Expected: 创建备份，3 个 CAS UPDATE 成功，读回 12 个指标卡全部为 `yesterday`。

- [ ] **Step 3: 独立只读验证**

Run: `backend\.venv\Scripts\python.exe tools/migrate_core_dashboard_metric_date_picker.py --verify`

Expected: 3 个空间的目标核心看板均验证通过；非目标图表哈希不变。

### Task 5: 全量测试与浏览器验证

**Files:**
- No production file changes unless verification reveals a regression.

**Interfaces:**
- Produces: 自动化与实际 UI 的完成证据。

- [ ] **Step 1: 运行相关完整测试集**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-filter.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
node frontend/src/views/dashboard/common/dashboardDateExpression.test.mjs
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_migrate_core_dashboard_metric_date_picker.py backend/tests/test_add_xiuxian_core_dashboard_realtime_metrics.py -q
```

Expected: 所有命令退出码 `0`。

- [ ] **Step 2: 数据库独立统计**

用只读 SQL 验证三个 tenant 的“核心看板”中目标 metric：12/12 均有 `metricDateExpressionEnabled=true`、`dateExpressionPickerEnabled=true`、`timeRange=expression`、`timeExpression.preset=yesterday`，且 SQL 含成对日期参数；其他空间无新增 `metricDateExpressionEnabled=true`。

- [ ] **Step 3: 浏览器逐空间验证**

在本地应用分别进入修仙、flam、模板_修仙的核心看板，打开一个目标指标卡编辑抽屉，确认：

- 时间范围第三项渲染 `DashboardDateExpressionPicker`；
- 按钮文本为“昨日”；
- DOM 中不出现该目标图表的旧 `builder-date-range`；
- 不点击“应用到画布”或“保存”，避免额外写入。

- [ ] **Step 4: 检查最终差异**

Run: `git diff --check; git status --short`

Expected: 无空白错误；只包含本任务文件和用户原有未提交文件，无生成物或备份被暂存。
