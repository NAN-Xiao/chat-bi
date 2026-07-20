# 修仙实时付费图表拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将修仙推荐实时看板的单个错误付费图拆成支付记录数柱状图和收入金额折线图，并提供可验证、可回滚的数据更新工具。

**Architecture:** 使用一个纯函数完成 `component_data` 与 `canvas_view_info` 转换，命令行层只负责只读检查、备份、乐观锁更新和数据库复验。两个 view 复用原 SQL 与数据快照，只改变图表字段映射和布局。

**Tech Stack:** Python 3.11、psycopg、pytest、PostgreSQL JSON 文本、Vue 看板 `SQView` 配置。

## Global Constraints

- 目标租户固定为 `7482727237662281728`，数据源固定为 `6`。
- 目标看板固定为 `10604280d5a941af9720800bce6e030f`，原组件固定为 `2193936101973073920`。
- 原 SQL、日期条件、`event_realtime`、事件和产品过滤条件不得修改。
- 新组件 ID 固定为 `4c17e5deeaac4834a3ff780e0cf3c450`，更新前必须确认不存在冲突。
- 原版本必须为 `3`，数据库更新必须使用版本乐观锁并把版本增加为 `4`。
- 备份写入 `.codex-runtime/xiuxian-dashboard-config-backups`，不得提交备份文件。
- 不修改其他看板，不处理现有 `.superpowers/brainstorm/` 未跟踪文件。

---

### Task 1: 实现并测试纯配置转换

**Files:**
- Create: `tools/split_xiuxian_realtime_payment_dashboard.py`
- Create: `tests/test_split_xiuxian_realtime_payment_dashboard.py`

**Interfaces:**
- Consumes: 原始 `component_data: list[dict]` 与 `canvas_view_info: dict[str, dict]`。
- Produces: `split_dashboard_payload(component_data, canvas_view_info) -> tuple[list[dict], dict[str, dict]]`。

- [ ] **Step 1: 写失败测试**

测试夹具包含一个原始 `SQView` 和一个同时返回三个字段的 view。断言转换结果为两个组件、左右布局、不同图表类型、空系列、显式字段、相同 SQL，并断言输入未被修改。

```python
def test_split_dashboard_payload_creates_two_independent_charts():
    components, views = split_dashboard_payload(source_components, source_views)
    assert [item["id"] for item in components] == [SOURCE_VIEW_ID, REVENUE_VIEW_ID]
    assert components[0]["x"] == 1 and components[0]["sizeX"] == 35
    assert components[1]["x"] == 37 and components[1]["sizeX"] == 35
    assert views[SOURCE_VIEW_ID]["chart"]["type"] == "column"
    assert views[SOURCE_VIEW_ID]["chart"]["yAxis"] == [{"value": "支付记录数", "metricType": "additive", "pivotAggregation": "sum"}]
    assert views[REVENUE_VIEW_ID]["chart"]["type"] == "line"
    assert views[REVENUE_VIEW_ID]["chart"]["yAxis"] == [{"value": "收入金额", "metricType": "additive", "pivotAggregation": "sum"}]
    assert views[SOURCE_VIEW_ID]["chart"]["series"] == []
    assert views[REVENUE_VIEW_ID]["chart"]["series"] == []
    assert views[SOURCE_VIEW_ID]["sql"] == views[REVENUE_VIEW_ID]["sql"]
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests\test_split_xiuxian_realtime_payment_dashboard.py -q`

Expected: FAIL，因为工具模块或 `split_dashboard_payload` 尚不存在。

- [ ] **Step 3: 实现最小纯函数**

实现常量、输入结构检查、`deepcopy`、原组件左侧改造、新组件右侧创建，以及两份 chart 配置：

```python
def split_dashboard_payload(component_data, canvas_view_info):
    components = deepcopy(component_data)
    views = deepcopy(canvas_view_info)
    _validate_source_payload(components, views)
    source_component = components[0]
    source_component.update({"x": 1, "y": 1, "sizeX": 35, "sizeY": 14, "innerType": "column"})
    revenue_component = deepcopy(source_component)
    revenue_component.update({"id": REVENUE_VIEW_ID, "_dragId": REVENUE_VIEW_ID, "x": 37, "innerType": "line"})
    components.append(revenue_component)
    source_view = views[SOURCE_VIEW_ID]
    revenue_view = deepcopy(source_view)
    _configure_chart(source_view, SOURCE_VIEW_ID, "column", "每小时支付记录数", "支付记录数")
    _configure_chart(revenue_view, REVENUE_VIEW_ID, "line", "每小时收入金额", "收入金额")
    views[REVENUE_VIEW_ID] = revenue_view
    return components, views
```

- [ ] **Step 4: 运行聚焦测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests\test_split_xiuxian_realtime_payment_dashboard.py -q`

Expected: PASS，全部断言通过。

### Task 2: 增加备份、应用和复验命令

**Files:**
- Modify: `tools/split_xiuxian_realtime_payment_dashboard.py`
- Modify: `tests/test_split_xiuxian_realtime_payment_dashboard.py`

**Interfaces:**
- Consumes: `core_system_db_config()` 和目标 `core_dashboard` 行。
- Produces: `dry_run() -> dict`、`apply_change() -> Path`、`verify_change() -> dict`。

- [ ] **Step 1: 增加失败关闭测试**

覆盖原组件缺失、新 ID 已存在、字段集合不符、SQL 不含 `event_realtime`、版本不为 `3` 时拒绝应用；覆盖复验要求两个组件 ID 与两个 view ID 完全一致。

- [ ] **Step 2: 运行测试并确认新增用例失败**

Run: `backend\.venv\Scripts\python.exe -m pytest tests\test_split_xiuxian_realtime_payment_dashboard.py -q`

Expected: FAIL，提示数据库命令接口尚未实现。

- [ ] **Step 3: 实现命令行层**

命令行支持互斥的 `--dry-run`、`--apply`、`--verify`：

```python
UPDATE_SQL = """
UPDATE core_dashboard
SET component_data = %s,
    canvas_view_info = %s,
    version = version + 1
WHERE tenant_id = %s
  AND datasource = %s
  AND id = %s
  AND version = %s
"""
```

`--apply` 在同一事务中 `SELECT ... FOR UPDATE`，验证版本和结构，先把原始字段、版本、SHA-256 写入时间戳备份，再执行更新；受影响行数不是 1 时回滚。`--verify` 只读查询并复用严格验证函数。

- [ ] **Step 4: 运行完整聚焦测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests\test_split_xiuxian_realtime_payment_dashboard.py -q`

Expected: PASS，退出码为 0。

- [ ] **Step 5: 检查代码格式和工作树**

Run: `git diff --check -- tools/split_xiuxian_realtime_payment_dashboard.py tests/test_split_xiuxian_realtime_payment_dashboard.py`

Expected: 无输出，退出码为 0。

### Task 3: 应用数据库变更并验证页面

**Files:**
- Runtime backup only: `.codex-runtime/xiuxian-dashboard-config-backups/<timestamp>.json`

**Interfaces:**
- Consumes: Task 2 的 `--dry-run`、`--apply`、`--verify`。
- Produces: 数据库版本 `4`、两个并排 SQView、可回滚备份。

- [ ] **Step 1: 执行只读预检**

Run: `backend\.venv\Scripts\python.exe tools\split_xiuxian_realtime_payment_dashboard.py --dry-run`

Expected: 输出目标版本 `3`、原组件和新组件 ID、`ready=true`，数据库不变。

- [ ] **Step 2: 应用更新**

Run: `backend\.venv\Scripts\python.exe tools\split_xiuxian_realtime_payment_dashboard.py --apply`

Expected: 输出备份绝对路径、`updated_rows=1`、`version=4`。

- [ ] **Step 3: 数据库复验**

Run: `backend\.venv\Scripts\python.exe tools\split_xiuxian_realtime_payment_dashboard.py --verify`

Expected: 输出 `verified=true`，两个组件与两个 view 的 ID 集合一致，SQL摘要一致。

- [ ] **Step 4: 页面视觉复验**

切换到修仙工作空间并打开推荐看板“实时看板”，确认左右两张图分别为“每小时支付记录数”和“每小时收入金额”，且图例中不再出现收入数值。检查浏览器控制台和 `backend/logs/error.log` 没有本次刷新新增的 SQL 或渲染错误。

- [ ] **Step 5: 最终验证**

Run: `backend\.venv\Scripts\python.exe -m pytest tests\test_split_xiuxian_realtime_payment_dashboard.py -q`

Run: `git diff --check`

Expected: 聚焦测试全部通过，`git diff --check` 退出码为 0；仅工具、测试和计划文件属于本次代码变更。

