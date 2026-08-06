# 移除 flam UTC+8 时间偏移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 flam 数据源实时 SQL 中固定的 `INTERVAL 8 HOUR`，直接按 Unix 毫秒时间戳转换小时。

**Architecture:** 只调整 flam 数据源的语义配置和实时看板 SQL 模板，不修改通用 SQL 生成器。生成阶段继续从 Data Skill、tracking 字典和当前看板配置获取时间表达式；所有三条来源统一为 `FROM_UNIXTIME(time / 1000)`。

**Tech Stack:** Python、pytest、PostgreSQL 语义种子、MySQL/StarRocks SQL 模板。

## Global Constraints

- 保持通用 BI 平台逻辑与其他数据源不变。
- 不新增静默时区兼容回退。
- flam 的语义配置必须通过 Data Skill 和 tracking 字典表达。
- 修改前后都必须验证实时小时 SQL 不包含 `INTERVAL 8 HOUR`。

---

### Task 1: 建立 flam 时间规则回归断言

**Files:**
- Modify: `backend/tests/test_flam_first_zombie_data_skill_seed.py`
- Test: `backend/tests/test_flam_first_zombie_data_skill_seed.py`

**Interfaces:**
- Consumes: `tools.seed_flam_first_zombie_data_skills.build_data_skills()` 和 `tools.seed_flam_first_zombie_tracking_dictionary.FIELDS`。
- Produces: 对 flam Data Skill 与 tracking 字典不再包含固定 UTC+8 偏移的可重复断言。

- [ ] **Step 1: Write the failing test**

在现有 flam Data Skill 与 tracking 字典断言中增加：实时 SQL、字段注释和字段 expression 必须包含 `FROM_UNIXTIME(... / 1000)`，且不包含 `INTERVAL 8 HOUR`。

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_flam_first_zombie_data_skill_seed.py -q`

Expected: FAIL because当前种子仍输出 `INTERVAL 8 HOUR`。

### Task 2: 统一 flam 语义种子和实时看板模板

**Files:**
- Modify: `tools/seed_flam_first_zombie_data_skills.py`
- Modify: `tools/seed_flam_first_zombie_tracking_dictionary.py`
- Modify: `tools/repair_flam_first_zombie_realtime_dashboard.py`

**Interfaces:**
- Consumes: Task 1 的回归断言。
- Produces: flam Data Skill、tracking 字典、实时看板修复脚本输出不带 UTC+8 偏移的 SQL。

- [ ] **Step 1: Replace the flam event-time expression**

将 `DATE_ADD(FROM_UNIXTIME(...), INTERVAL 8 HOUR)` 统一改为 `FROM_UNIXTIME(... / 1000)`，并同步实时日期边界与小时分组表达式。

- [ ] **Step 2: Run the focused tests**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_flam_first_zombie_data_skill_seed.py backend/tests/test_repair_flam_first_zombie_semantic_dashboards.py -q`

Expected: PASS。

### Task 3: 更新运行中的 datasource 3 语义与已保存实时看板

**Files:**
- Use: `tools/seed_flam_first_zombie_data_skills.py`
- Use: `tools/repair_flam_first_zombie_realtime_dashboard.py`

**Interfaces:**
- Consumes: Task 2 中已验证的种子和修复 SQL。
- Produces: core system database 中 datasource 3 的 Data Skill、tracking 字典和实时看板配置与代码规则一致。

- [ ] **Step 1: Run the datasource-scoped seed/sync commands**

先备份并更新 datasource 3 的 Data Skill 与 tracking 字典，再运行实时看板修复脚本；不得触碰其他 datasource。

- [ ] **Step 2: Query and verify persisted configuration**

确认 datasource 3 的 `custom_prompt`、`sys_tenant_tracking_field` 和 `core_dashboard.canvas_view_info` 中不再包含 `INTERVAL 8 HOUR`。

- [ ] **Step 3: Run the final focused tests and inspect the diff**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_flam_first_zombie_data_skill_seed.py backend/tests/test_repair_flam_first_zombie_semantic_dashboards.py -q`

Expected: PASS，且 git diff 仅包含本次 flam 语义规则变更。
