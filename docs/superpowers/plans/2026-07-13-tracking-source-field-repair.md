# Tracking Source Field Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 阻止事件参数 Excel 导入时静默回退到 `ext`，并用已有数据采样结果修复 First Zombie 当前工作空间的来源字段配置。

**Architecture:** 通用导入器只接受显式来源、同事件继承来源或点号属性名推断来源，无法确定时整次导入失败。数据修复通过独立、可重复执行的工具读取已采样确认的修复工作簿，只更新指定工作空间和数据源的 `event_name_mappings`，更新前写出 JSON 备份并在事务内完成校验。

**Tech Stack:** Python 3.11、pytest、pandas/openpyxl（现有 Excel 解析链路）、psycopg、PostgreSQL JSONB。

## Global Constraints

- 不得为来源字段增加 `ext`、首列或相似字段等静默兼容回退。
- 通用运行时代码不得硬编码 First Zombie 事件名或业务字段。
- 数据修复仅限 `tenant_id=7477202383789887488`、`datasource_id=3`。
- 当前采样依据为 10 个业务分区、3989 条事件样本；`ext` 非空样本为 0，`personal` 非空样本为 3899。
- 修复工作簿应得到 755 个属性，其中 `personal=469`、`ext=286`；未验证属性不得伪造成 `personal`。

---

### Task 1: 阻止缺失来源字段的 Excel 导入

**Files:**
- Modify: `backend/apps/system/crud/tracking_excel.py:1500-1540,1678-1681`
- Test: `backend/tests/test_tracking_excel.py`

**Interfaces:**
- Consumes: `_read_sheet_rows(..., include_row_number=True)` 写入的 `EXCEL_ROW_NUMBER_KEY`。
- Produces: `_parse_event_parameter_mapping_sheet(...)` 在无法确定来源字段时抛出带工作表名和 Excel 行号的 `ValueError`。

- [ ] **Step 1: 写失败测试**

新增用例：新事件首行属性 `money` 未填写“数据源字段”，调用 `parse_tracking_excel` 必须抛出 `ValueError`，错误同时包含 `事件参数对照`、`第 2 行` 和 `数据源字段`；另一个用例验证新事件不会继承上一个事件的 `personal`。

- [ ] **Step 2: 运行测试并确认 RED**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -k "requires_source_field or does_not_inherit_source_across_events" -q`

Expected: FAIL，因为当前实现使用 `last_source_field or "ext"`。

- [ ] **Step 3: 最小实现**

读取“事件参数对照”时启用 `include_row_number=True`。将来源计算改为当前行或同事件上下文，不再追加 `"ext"`；调用 `_split_event_parameter_source` 后若仍无 `source_field`，抛出：

```python
row_number = int(row.get(EXCEL_ROW_NUMBER_KEY) or 0)
raise ValueError(
    f"{EVENT_PARAMETER_MAPPING_SHEET} sheet 第 {row_number} 行属性 {raw_property_name} "
    "缺少数据源字段；请填写 personal/ext 等真实 JSON 宿主字段，或使用 personal.money 形式的属性名。"
)
```

- [ ] **Step 4: 运行定向和完整 Excel 测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py -q`

Expected: 全部 PASS。

### Task 2: 增加可回滚的 First Zombie 配置修复工具

**Files:**
- Create: `tools/repair_flam_first_zombie_event_sources.py`
- Test: `backend/tests/test_flam_first_zombie_event_source_repair.py`

**Interfaces:**
- Consumes: `parse_tracking_excel(bytes, TenantTrackingConfigDTO(...), physical_schema={}, datasource_type="mysql")` 和修复工作簿路径。
- Produces: `load_repaired_mappings(path) -> list[dict]`、`source_distribution(mappings) -> dict[str, int]`、`repair_event_sources(workbook, apply=False) -> dict`。

- [ ] **Step 1: 写失败测试**

测试来源分布统计、`ServerPayLog.money` 必须为 `personal/$.money`、错误租户/数据源不可更新，以及相同映射重复执行返回 `changed=false`。

- [ ] **Step 2: 运行测试并确认 RED**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_flam_first_zombie_event_source_repair.py -q`

Expected: ERROR/FAIL，因为修复模块尚不存在。

- [ ] **Step 3: 实现修复工具**

工具默认 dry-run；`--apply` 才更新数据库。应用前将原始 `event_name_mappings`、租户、数据源和时间写入 `.codex-runtime/event-source-backups/`。事务中使用 `SELECT ... FOR UPDATE` 锁定唯一配置行，验证工作簿属性数为 755、分布为 `personal=469/ext=286`，并验证 `ServerPayLog.money/orderId/productid` 均为 `personal` 后执行参数化 `UPDATE`。

- [ ] **Step 4: 运行修复工具测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_flam_first_zombie_event_source_repair.py -q`

Expected: 全部 PASS。

### Task 3: 备份、应用和数据验收

**Files:**
- Read: `outputs/event-parameter-mapping/tracking_dictionary_current_fixed_mixed_merged.xlsx`
- Generate: `.codex-runtime/pg-backups/*` 或 `.codex-runtime/event-source-backups/*.json`
- Generate: `outputs/event-parameter-mapping/tracking_dictionary_current_repaired.xlsx`

**Interfaces:**
- Consumes: Task 2 的命令行工具。
- Produces: 修复后的数据库配置和重新导出的验收工作簿。

- [ ] **Step 1: 执行 PostgreSQL 备份**

Run: `powershell -ExecutionPolicy Bypass -File tools/postgres-backup-local.ps1 -Action backup`

Expected: 输出 `.codex-runtime/pg-backups/zhishu_bi-<timestamp>.dump`；若本机缺少 `pg_dump`，Task 2 的配置级 JSON 备份仍必须成功后才能更新。

- [ ] **Step 2: dry-run 校验修复输入**

Run: `backend\.venv\Scripts\python.exe tools/repair_flam_first_zombie_event_sources.py --workbook outputs/event-parameter-mapping/tracking_dictionary_current_fixed_mixed_merged.xlsx`

Expected: `changed=true`、当前分布 `ext=755`、目标分布 `personal=469/ext=286`，数据库不变化。

- [ ] **Step 3: 应用修复并重复运行验证幂等**

Run: `backend\.venv\Scripts\python.exe tools/repair_flam_first_zombie_event_sources.py --workbook outputs/event-parameter-mapping/tracking_dictionary_current_fixed_mixed_merged.xlsx --apply`

Run again without `--apply`。

Expected: 首次更新一行并输出备份路径；第二次 `changed=false`。

- [ ] **Step 4: 导出并检查工作簿**

调用现有 `tracking_config_excel` 导出当前配置到 `outputs/event-parameter-mapping/tracking_dictionary_current_repaired.xlsx`，检查“事件参数对照”来源分布仍为 `personal=469/ext=286`，且 `ServerPayLog.money` 为 `personal`。

### Task 4: 全量回归验证

**Files:**
- Verify: `backend/apps/system/crud/tracking_excel.py`
- Verify: `tools/repair_flam_first_zombie_event_sources.py`

**Interfaces:**
- Consumes: 前三项任务的实现和数据库结果。
- Produces: 可复现的测试、静态检查和数据校验输出。

- [ ] **Step 1: 运行相关测试集**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_excel.py backend/tests/test_flam_first_zombie_event_source_repair.py backend/tests/test_flam_first_zombie_tracking_dictionary_seed.py -q`

Expected: 全部 PASS。

- [ ] **Step 2: 运行代码质量检查**

Run: `backend\.venv\Scripts\python.exe -m ruff check backend/apps/system/crud/tracking_excel.py tools/repair_flam_first_zombie_event_sources.py backend/tests/test_tracking_excel.py backend/tests/test_flam_first_zombie_event_source_repair.py`

Expected: exit code 0。

- [ ] **Step 3: 最终只读数据库核验**

查询目标配置并断言属性总数 755、来源分布 `personal=469/ext=286`，以及 `ServerPayLog.money` 的 `source_field=personal`、`json_path=$.money`。
