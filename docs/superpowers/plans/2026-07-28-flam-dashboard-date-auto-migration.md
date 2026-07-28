# Flam 看板抽屉日期自动迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Flam 指定看板抽屉的固定日期 SQL 安全改为接收看板日期参数，并保留 cohort 成熟观察期。

**Architecture:** 扩展已有迁移脚本的显式目标表和受限自动替换器。每个目标使用四种迁移模式之一：单日期范围、结束日锚点卡片、cohort 成熟期、周快照/ROI 多窗口；无法唯一识别的 SQL 在预演时失败而不写入。写入继续使用现有备份、行锁、CAS 与读回校验。

**Tech Stack:** Python 3、psycopg、pytest、Flam MySQL SQL、Vue 看板日期表达式配置。

## Global Constraints

- 仅操作 Flam 租户 `7477202383789887488` 的默认叶子看板。
- 不迁移 ChatMon 四类看板、实时看板、标题包含“当日”的抽屉和 `日充值用户数`。
- 日期参数固定为 `{{dashboard_start_yyyymmdd}}`、`{{dashboard_end_yyyymmdd}}`，类型为 `yyyymmdd_number`。
- 留存、LTV、活动后续付费和 ROI 的 cohort 范围使用参数，D1、D7、D30、ROI period 等成熟期条件不得修改。
- 不替换不存在唯一业务日期字段、无 SQL 或已正确参数化的抽屉。
- 不触碰工作区中与本任务无关的已有改动。

---

### Task 1: 定义迁移目标与拒绝边界

**Files:**
- Modify: `D:/AIWork3/chat-bi/tools/enable_flam_default_dashboard_date_filters.py`
- Test: `D:/AIWork3/chat-bi/backend/tests/test_enable_flam_default_dashboard_date_filters.py`

**Interfaces:**
- Consumes: `migrate_canvas(canvas: dict[str, Any], dashboard_id: str)`。
- Produces: `DATE_MIGRATION_TARGETS: dict[tuple[str, str], DateMigration]` 与 `migration_for_view(...) -> Callable[[str], str] | None`。

- [ ] **Step 1: 写入目标清单的失败测试**

```python
def test_target_manifest_covers_requested_drawers_and_excludes_daily_recharge():
    titles = {
        target.title
        for target in migration.DATE_MIGRATION_TARGETS.values()
    }

    assert {"活跃用户", "新增用户", "充值人数", "充值总额"} <= titles
    assert {"ROI总览", "ROI地区总览", "ROI广告地区总览", "安装投放趋势"} <= titles
    assert "日充值用户数" not in titles
    assert all("当日" not in title for title in titles)
```

- [ ] **Step 2: 运行目标清单测试并确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py::test_target_manifest_covers_requested_drawers_and_excludes_daily_recharge -q`

Expected: FAIL，`DATE_MIGRATION_TARGETS` 尚未定义。

- [ ] **Step 3: 实现不可猜测的显式目标声明**

```python
@dataclass(frozen=True)
class DateMigration:
    title: str
    kind: Literal["range", "end_anchor", "cohort", "weekly_snapshots", "roi"]
    date_field: str
    transform: Callable[[str], str]

DATE_MIGRATION_TARGETS = {
    ("6d50bd7dfc9f46ba961d636814c3294d", "c23c019171804f608e92961dc06ae8b2"): DateMigration("活跃用户", "end_anchor", "dt", migrate_end_anchor_metric_sql),
    ("2b990d3821fa4c3d97f0dda519b644e8", "98918b6a38b14ca2b3ec63ff4cc8753f"): DateMigration("ROI总览", "dt", "roi", migrate_roi_sql),
}
```

清单加入已确认的核心、新增、活跃、付费、主城、出征、渠道、活动、ROI 和投放目标；不加入实时、ChatMon、当日和日充值用户数。

- [ ] **Step 4: 运行目标清单测试并确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py::test_target_manifest_covers_requested_drawers_and_excludes_daily_recharge -q`

Expected: PASS。

### Task 2: 实现受限 SQL 转换器

**Files:**
- Modify: `D:/AIWork3/chat-bi/tools/enable_flam_default_dashboard_date_filters.py`
- Test: `D:/AIWork3/chat-bi/backend/tests/test_enable_flam_default_dashboard_date_filters.py`

**Interfaces:**
- Consumes: `START_TOKEN`、`END_TOKEN`、`_parameter_date(token: str) -> str`。
- Produces: `migrate_range_sql`、`migrate_end_anchor_metric_sql`、`migrate_cohort_sql`、`migrate_weekly_snapshots_sql` 与 `migrate_roi_sql`。

- [ ] **Step 1: 写入单范围与结束日锚点的失败测试**

```python
def test_migrate_end_anchor_metric_uses_selected_end_day_for_comparison():
    migrated = migration.migrate_end_anchor_metric_sql(_three_point_metric_sql())

    assert "{{dashboard_end_yyyymmdd}}" in migrated
    assert "INTERVAL 1 DAY" in migrated
    assert "INTERVAL 7 DAY" in migrated
    assert "CURDATE()" not in migrated

def test_migrate_range_sql_rejects_two_business_date_windows():
    with pytest.raises(ValueError, match="唯一"):
        migration.migrate_range_sql("SELECT * FROM e WHERE e.dt BETWEEN 1 AND 2 AND p.dt BETWEEN 1 AND 2")
```

- [ ] **Step 2: 运行上述测试并确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py -k "end_anchor or range_sql" -q`

Expected: FAIL，转换器尚未实现。

- [ ] **Step 3: 实现单范围与结束日锚点转换器**

```python
def migrate_end_anchor_metric_sql(sql: str) -> str:
    end_date = _parameter_date(END_TOKEN)
    result = str(sql)
    result = result.replace("DATE_SUB(CURDATE(), INTERVAL 1 DAY)", end_date)
    result = result.replace(
        "DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 1 DAY)",
        f"DATE_SUB({end_date}, INTERVAL 1 DAY)",
    )
    result = result.replace(
        "DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 7 DAY)",
        f"DATE_SUB({end_date}, INTERVAL 7 DAY)",
    )
    if "CURDATE" in result.upper() or END_TOKEN not in result:
        raise ValueError("结束日锚点 SQL 未完整参数化")
    return result
```

`migrate_range_sql` 只替换唯一 `<alias>.dt BETWEEN <固定表达式> AND <固定表达式>`，保留其他筛选；任何多个业务日期窗口立即抛出 `ValueError`。

- [ ] **Step 4: 写入 cohort、周快照和 ROI 的失败测试**

```python
def test_migrate_cohort_sql_keeps_d30_maturity_window():
    migrated = migration.migrate_cohort_sql(_ltv_sql())

    assert "{{dashboard_start_yyyymmdd}}" in migrated
    assert "{{dashboard_end_yyyymmdd}}" in migrated
    assert "INTERVAL 29 DAY" in migrated

def test_migrate_roi_sql_replaces_every_cohort_date_boundary_only():
    migrated = migration.migrate_roi_sql(_roi_sql())

    assert "CURDATE()" not in migrated
    assert "r.period <= 360" in migrated
    assert migrated.count("{{dashboard_start_yyyymmdd}}") == 4
    assert migrated.count("{{dashboard_end_yyyymmdd}}") == 4
```

- [ ] **Step 5: 运行 cohort、周快照和 ROI 测试并确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py -k "cohort or roi or weekly" -q`

Expected: FAIL，专用转换器尚未实现。

- [ ] **Step 6: 实现专用转换器并限制输入模式**

```python
def migrate_roi_sql(sql: str) -> str:
    result = _replace_all_exact_date_bounds(
        sql,
        start=_parameter_date(START_TOKEN),
        end=_parameter_date(END_TOKEN),
    )
    if "CURDATE" in result.upper() or "period <=" not in result:
        raise ValueError("ROI SQL 的 cohort 边界或成熟期校验失败")
    return result
```

`migrate_cohort_sql` 仅替换注册、购买或活动参与 cohort 条件；`migrate_weekly_snapshots_sql` 从 `END_TOKEN` 推导最近八个完整周的快照日，不改累计金额分箱。每个函数必须检查替换次数和剩余的 `CURDATE/CURRENT_DATE`，失败即拒绝。

- [ ] **Step 7: 运行迁移脚本单元测试并确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py -q`

Expected: PASS。

### Task 3: 接入画布迁移、预演与页面验证

**Files:**
- Modify: `D:/AIWork3/chat-bi/tools/enable_flam_default_dashboard_date_filters.py`
- Modify: `D:/AIWork3/chat-bi/backend/tests/test_enable_flam_default_dashboard_date_filters.py`

**Interfaces:**
- Consumes: `DATE_MIGRATION_TARGETS` 和专用 SQL 转换器。
- Produces: `migrate_canvas(...)` 对显式目标调用对应转换器；`migrate_default_dashboards(apply: bool)` 返回每个改动图表标题与 SQL 哈希。

- [ ] **Step 1: 写入画布集成失败测试**

```python
def test_migrate_canvas_uses_manifest_transform_and_preserves_unlisted_view():
    canvas = {
        "c23c019171804f608e92961dc06ae8b2": _core_active_metric_view(),
        "01b402cb5b5f4c95bc457cf505a2ecc7": _daily_recharge_view(),
    }

    migrated, unchanged = migration.migrate_canvas(
        canvas,
        dashboard_id="6d50bd7dfc9f46ba961d636814c3294d",
    )

    assert "{{dashboard_end_yyyymmdd}}" in migrated["c23c019171804f608e92961dc06ae8b2"]["sql"]
    assert unchanged["01b402cb5b5f4c95bc457cf505a2ecc7"] == migration.stable_json_hash(canvas["01b402cb5b5f4c95bc457cf505a2ecc7"])
```

- [ ] **Step 2: 运行集成测试并确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py::test_migrate_canvas_uses_manifest_transform_and_preserves_unlisted_view -q`

Expected: FAIL，`migrate_canvas` 尚未读取新目标清单。

- [ ] **Step 3: 接入显式目标与读回校验**

```python
target = DATE_MIGRATION_TARGETS.get((dashboard_id, chart_id))
if target is not None:
    targets.append(chart_id)
    continue
```

在目标处理循环中调用 `target.transform`，使用 `configure_explicit_date_view` 写入日期控件，并在 `verify_canvas` 中按目标期望的参数数量和 `target.date_field` 校验。无 SQL 的“各类型加速情况（待字段映射）”保留不改并写入预演 `skipped` 原因。

- [ ] **Step 4: 运行完整单元测试与预演**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_enable_flam_default_dashboard_date_filters.py -q`

Expected: PASS。

Run: `backend/.venv/Scripts/python.exe tools/enable_flam_default_dashboard_date_filters.py`

Expected: `applied: false`，列出将写入的目标图表，`skipped` 只包含无 SQL 或非唯一日期条件的明确原因。

- [ ] **Step 5: 应用迁移并读回校验**

Run: `backend/.venv/Scripts/python.exe tools/enable_flam_default_dashboard_date_filters.py --apply`

Expected: `applied: true`，每个更新的看板生成一个 `.codex-runtime/dashboard-date-expression-backups/` 快照，`chart_count` 与预演一致。

- [ ] **Step 6: 本地页面抽测日期切换**

在每个受影响看板至少选取一个代表抽屉，依次切换“过去 30 天”和“过去 7 天”；验证网络请求中起止参数变化、后端执行成功、图表数据或时间轴范围变化，并检查浏览器控制台无错误。
