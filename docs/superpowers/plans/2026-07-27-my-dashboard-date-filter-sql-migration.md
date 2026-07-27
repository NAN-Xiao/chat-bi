# 我的看板日期筛选 SQL 配置迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 flam 工作空间当前用户 `dongjinchao_test` 的 6 张历史 SQL 图表补齐日期参数模板和时间字段配置，使其显示独立日期选择器并支持点击“应用”后按所选范围查询。

**Architecture:** 直接迁移星通数智系统库 `core_dashboard.canvas_view_info` 中当前用户拥有的目标图表配置。迁移前导出完整原始行；迁移时只替换已确认的 `YYYYMMDD` 日期谓词并补齐 `pivot.time_field`、`pivot.date_parameter_type`、`pivot.range_enabled`；迁移后调用现有 `prepare_dashboard_date_filter` 和 SQL 预览链验证，不修改业务数据库。

**Tech Stack:** PostgreSQL（系统库）、Python/psycopg、现有 Dashboard 日期参数能力、MySQL/ADS 业务 SQL

## Global Constraints

- 只修改租户 `7477202383789887488`、用户 `7482253745313550336` 拥有的“我的看板”。
- 目标看板仅为 `ROI看板`（ID `6773e46d6a8e49e18c8811ec1dbab37e`）和 `T1`（ID `9fb09576a8e046edb9b35845b3e87675`）。
- `运营` 看板无图表，不更新。
- `主城升级漏斗转化率` 没有可选日期维度，不更新。
- 任何读取 `event_realtime` 的 SQL 不迁移。
- 默认日期范围由现有后端能力计算为昨天往前共 14 天，不包含今天。
- 只更新系统库看板配置；业务库保持只读。

---

### Task 1: 备份和锁定目标配置

**Files:**
- Create: `.codex-runtime/dashboard-date-filter-backups/my-dashboard-20260727.json`
- Verify: `core_dashboard`

**Interfaces:**
- Consumes: 系统库中两个目标看板的完整数据库行。
- Produces: 包含 `id`、`name`、`canvas_view_info`、`canvas_style_data`、`component_data`、`update_time` 的可回滚 JSON 备份。

- [ ] **Step 1: 在只读事务中按租户、创建人和看板 ID 查询目标行**

查询条件必须同时包含：

```sql
tenant_id = 7477202383789887488
AND create_by = '7482253745313550336'
AND id IN (
  '6773e46d6a8e49e18c8811ec1dbab37e',
  '9fb09576a8e046edb9b35845b3e87675'
)
AND COALESCE(delete_flag, 0) = 0
```

- [ ] **Step 2: 将完整目标行写入备份文件并计算 SHA-256**

备份必须在更新事务开始前落盘，输出两个看板 ID、图表数和备份哈希。

- [ ] **Step 3: 校验迁移清单恰好包含 6 张图**

预期：`ROI看板` 4 张，`T1` 2 张；若标题、ID 或 SQL 与盘点结果不一致，中止而不写库。

### Task 2: 迁移 6 张图表配置

**Files:**
- Modify: PostgreSQL `core_dashboard.canvas_view_info`
- Reference: `backend/apps/dashboard/crud/dashboard_date_filter.py`

**Interfaces:**
- Consumes: Task 1 锁定的两个看板配置和 6 个图表 ID。
- Produces: 带成对日期模板与显式时间字段配置的 `canvas_view_info`。

- [ ] **Step 1: 迁移 ROI 看板 4 张图**

图表 ID：

```text
2195197577098600448
2195198304432857088
2195199004655132672
2196532897761107968
```

将每个 revenue、video revenue、installs、spending CTE 中的固定范围：

```sql
>= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 21 DAY), '%Y%m%d') AS BIGINT)
<= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS BIGINT)
```

分别替换为：

```sql
>= {{dashboard_start_yyyymmdd}}
<= {{dashboard_end_yyyymmdd}}
```

为每张图写入：

```json
{
  "time_field": "日期",
  "date_parameter_type": "yyyymmdd_number",
  "range_enabled": true
}
```

保留原有 `pivot.enabled` 和其他透视设置。

- [ ] **Step 2: 迁移 T1 的活跃趋势**

图表 ID `2191568784127598592`：将 `event.dt` 固定近 30 天条件替换为一对 `{{dashboard_start_yyyymmdd}}` / `{{dashboard_end_yyyymmdd}}`，并配置：

```json
{
  "time_field": "事件日期",
  "date_parameter_type": "yyyymmdd_number",
  "range_enabled": true
}
```

- [ ] **Step 3: 迁移 T1 的付费异常日期**

图表 ID `2195192460584591360`：将固定字符串范围 `'20260701'` / `'20260723'` 替换为一对 `{{dashboard_start_yyyymmdd}}` / `{{dashboard_end_yyyymmdd}}`，并配置：

```json
{
  "time_field": "日期",
  "date_parameter_type": "yyyymmdd_number",
  "range_enabled": true
}
```

- [ ] **Step 4: 在单个 PostgreSQL 事务内执行带旧值校验的更新**

更新前使用 `SELECT ... FOR UPDATE` 重新读取两行，并校验 `canvas_view_info` 与备份一致。任一替换次数不符合预期、目标图表缺失、出现 `event_realtime` 或非目标图表发生变化时回滚整个事务。

### Task 3: 验证能力、SQL 和页面行为

**Files:**
- Verify: `backend/apps/dashboard/crud/dashboard_date_filter.py`
- Verify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`

**Interfaces:**
- Consumes: Task 2 更新后的 6 张图表配置。
- Produces: 每张图 `available`、默认近 14 天 SQL 可解析执行、页面显示独立日期选择器的验证证据。

- [ ] **Step 1: 只读重新查询并验证配置边界**

断言恰好 6 张目标图包含完整模板、正确 `time_field` 和 `date_parameter_type`；`主城升级漏斗转化率` 不包含模板；其他用户看板哈希不变。

- [ ] **Step 2: 对 6 张图调用 `prepare_dashboard_date_filter`**

使用 `ds_type='mysql'`，预期每张返回：

```json
{"status": "available"}
```

并验证默认范围是 `2026-07-13` 至 `2026-07-26`。

- [ ] **Step 3: 对渲染后的 6 条 SQL 执行只读预览**

使用当前用户、租户和数据源 3 的既有 `/dashboard/sql_preview` 权限链；预期 SQL 解析通过、只读校验通过，且最终 SQL 不再包含 `{{dashboard_...}}`。

- [ ] **Step 4: 浏览器验证逐图交互**

打开 `ROI看板` 和 `T1`，确认 6 张目标图显示日期选择器和“应用”；漏斗图不显示。修改一张图的日期但不点击“应用”时不得请求；点击后只刷新该图，刷新页面后恢复默认近 14 天。

- [ ] **Step 5: 记录回滚方式**

若验证失败，使用 Task 1 备份中的原始 `canvas_view_info` 按相同租户、创建人和看板 ID 条件在单个事务中恢复，并再次核对 SHA-256。
