# Flam 推荐看板日期控件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Flam 推荐看板指定的非实时、非当日抽屉提供真正生效的日期表达式控件。

**Architecture:** 在 `tools/` 中维护显式迁移清单和受控 SQL 替换规则；脚本在数据库画布 JSON 内写入日期参数、构建器配置和透视配置。所有写入通过备份、行锁、CAS 和读回校验保护。

**Tech Stack:** Python、psycopg、PostgreSQL JSON 画布配置、Node/Python 测试。

## Global Constraints

- 仅修改 Flam 租户 `7477202383789887488` 的推荐看板。
- 不修改 ChatMon、实时、标题含“当日”的指标和“日充值用户数”。
- 日期选择必须改变 SQL 的业务日期条件，禁止只展示控件。
- 保持现有数据源、图表字段、图表类型与非目标抽屉内容不变。

---

### Task 1: 定义可审计的迁移目标

**Files:**
- Modify: `tools/enable_flam_default_dashboard_date_filters.py`
- Test: `backend/tests/test_enable_flam_default_dashboard_date_filters.py`

- [ ] 为每个指定抽屉声明看板 ID、图表 ID、业务日期字段、旧日期边界及预期参数数量。
- [ ] 为实时、当日、“日充值用户数”和 ChatMon 写入显式排除断言。
- [ ] 编写失败测试，验证不在目标清单的抽屉不会进入迁移计划。

### Task 2: 实现受控 SQL 与日期配置迁移

**Files:**
- Modify: `tools/enable_flam_default_dashboard_date_filters.py`
- Test: `backend/tests/test_enable_flam_default_dashboard_date_filters.py`

- [ ] 为单日期窗口和 cohort 成熟期窗口实现显式替换器，输出 `{{dashboard_start_yyyymmdd}}` 与 `{{dashboard_end_yyyymmdd}}`。
- [ ] 写入 `dateExpressionPickerEnabled`、`timeExpression`、`time_field` 和日期参数类型。
- [ ] 编写失败测试，验证旧 SQL 条件不匹配、参数数量错误或日期字段缺失时拒绝写入。

### Task 3: 预演、应用与读回验证

**Files:**
- Modify: `tools/enable_flam_default_dashboard_date_filters.py`
- Test: `backend/tests/test_enable_flam_default_dashboard_date_filters.py`

- [ ] 预演输出按看板分组的目标和排除项。
- [ ] 应用前备份，应用时行锁与 CAS，应用后校验目标配置和非目标哈希。
- [ ] 运行脚本预演、单元测试与本地页面日期切换验证。
