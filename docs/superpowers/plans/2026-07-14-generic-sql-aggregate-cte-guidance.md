# 通用 SQL 聚合边界 CTE 引导 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让分析助手在未命中数据源专属 Data Skill 时，仍在 SQL 生成阶段避免将聚合或窗口函数写入同层 `WHERE`。

**Architecture:** 在普通分析、预测分析和 SQL 修正提示词中增加数据库与业务无关的聚合边界规则及抽象 CTE 参照。flam D7 的 cohort、JSON 和日期窗口仍只保留在数据源专属 Data Skill，且不增加执行前 SQL 改写。

**Tech Stack:** Python、pytest、LangChain 消息提示词。

## Global Constraints

- 共享提示词不得出现 flam、first_zombie、D7 或业务表字段。
- 三条生成/修正链路必须使用同一规则。
- 测试先失败，再修改生产代码。

---

### Task 1: 约束通用提示词的聚合边界

**Files:**
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py:231-337`
- Test: `backend/tests/test_analysis_assistant_sql_generation.py`

**Interfaces:**
- Consumes: `PLAN_PROMPT`、`FORECAST_PLAN_PROMPT`、`SQL_REPAIR_PROMPT`。
- Produces: 三条 SQL 生成链路共享的聚合边界约束。

- [ ] **Step 1: 写入失败测试**

```python
def test_all_sql_generation_prompts_require_aggregate_bounds_outside_where() -> None:
    prompts = (
        analysis_api.PLAN_PROMPT,
        analysis_api.FORECAST_PLAN_PROMPT,
        analysis_api.SQL_REPAIR_PROMPT,
    )
    for prompt in prompts:
        assert "聚合函数或窗口函数不得出现在同一查询层级的 WHERE" in prompt
        assert "WITH bounds AS" in prompt
        assert "FROM source_table" in prompt
```

- [ ] **Step 2: 运行失败测试**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_analysis_assistant_sql_generation.py::test_all_sql_generation_prompts_require_aggregate_bounds_outside_where -q`

Expected: FAIL，因为当前共享提示词缺少规则与 CTE 参照。

- [ ] **Step 3: 写入最小实现**

在三个提示词中加入：`聚合函数或窗口函数不得出现在同一查询层级的 WHERE；需要按 MAX/MIN/COUNT 等聚合结果筛选时，必须先在 CTE 或标量子查询中计算边界值，再由外层查询引用。`

并加入：`通用结构参照：WITH bounds AS (SELECT MAX(date_column) AS max_date FROM source_table) SELECT ... FROM source_table t CROSS JOIN bounds b WHERE t.date_column >= b.max_date；实际表名、字段名和日期计算必须以当前 schema 为准。`

- [ ] **Step 4: 验证通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_analysis_assistant_sql_generation.py backend\\tests\\test_flam_first_zombie_data_skill_seed.py backend\\tests\\test_analysis_assistant_permissions.py backend\\tests\\test_tracking_context_projection.py -q`

Expected: PASS。
