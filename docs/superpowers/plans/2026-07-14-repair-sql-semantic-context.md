# SQL 修正语义上下文保留 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使分析助手的 SQL 失败重试始终获得完整的当前 Data Skill，避免工作空间埋点上下文截断数据源专属 SQL 示例。

**Architecture:** `_repair_sql` 接收分离的 `data_skill` 与 `tracking_context`。Data Skill 仍通过现有 `_data_skill_block` 优先注入；埋点上下文作为独立、限长的补充内容附加。两处修正调用传入未合并的原始上下文。

**Tech Stack:** Python、pytest、LangChain 消息。

## Global Constraints

- 不将 flam/D7 业务逻辑写入共享后端提示词。
- 不增加执行前 SQL 字符串替换或静默兼容。
- Data Skill 必须在修正提示词中完整且先于埋点上下文出现。

---

### Task 1: 保留 SQL 修正阶段的 Data Skill

**Files:**
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py:3101-3136,3574-3596`
- Modify: `backend/tests/test_analysis_assistant_sql_generation.py`

**Interfaces:**
- Consumes: `_repair_sql(..., tracking_context: str = "", data_skill: str = "")`。
- Produces: 修正提示词中完整的 Data Skill 和独立限长的埋点上下文。

- [ ] **Step 1: 写入失败测试**

使用记录消息的假 LLM 调用 `_repair_sql`，传入 25,000 字符埋点上下文和含 `七日留存 SQL 示例` 的 Data Skill；断言发送给 LLM 的用户消息同时包含 D7 示例、完整 Data Skill，以及被限长的埋点上下文。

- [ ] **Step 2: 运行测试并确认失败**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_analysis_assistant_sql_generation.py::test_sql_repair_keeps_data_skill_when_tracking_context_is_large -q`

Expected: FAIL，因为旧接口将合并内容当作 Data Skill 截断。

- [ ] **Step 3: 最小实现**

扩展 `_repair_sql` 参数，在提示词中先添加 `_data_skill_block(data_skill)`，再单独追加最多 12,000 字符的工作空间埋点上下文；将两个调用点由 `semantic_context` 改为 `tracking_context, data_skill`。

- [ ] **Step 4: 验证通过**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\test_analysis_assistant_sql_generation.py backend\\tests\\test_flam_first_zombie_data_skill_seed.py backend\\tests\\test_analysis_assistant_permissions.py backend\\tests\\test_tracking_context_projection.py -q`

Expected: PASS。
