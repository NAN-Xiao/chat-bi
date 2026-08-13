# AI Dashboard Date Error Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 flam AI 看板 #65 的 `missing_date_filter` 解析错误和 #96 的当前日实时表日期渲染错误。

**Architecture:** 通用 JSON 提取器负责正确识别外层结构，不让 SQL 字符串内容影响括号匹配。聊天日期服务在通用 Dashboard 日期能力判定之外增加一个严格的当前日实时渲染分支，历史与跨日行为保持不变。

**Tech Stack:** Python 3.11、orjson、pytest、sqlglot、现有 Smart Q&A LangGraph 工作流。

## Global Constraints

- 不修改 flam 业务口径、数据源 ID、表名或事件名。
- 不静默改查 `event`，不放宽跨日 `event_realtime` 查询。
- 不改变普通 Dashboard 对实时表返回 `realtime_table` 的能力状态。
- 不触碰主工作区已有未提交修改。

---

### Task 1: SQL JSON 字符串感知提取

**Files:**
- Modify: `backend/common/utils/utils.py:99`
- Test: `backend/tests/test_utils.py`

**Interfaces:**
- Consumes: `extract_nested_json(text: str)` 现有接口。
- Produces: 相同返回类型；有效 JSON 返回原始 JSON 字符串，无有效 JSON 返回 `None`。

- [x] **Step 1: 写失败测试**

构造有效 fenced JSON，其中 SQL 同时包含 `{{dashboard_start_yyyymmdd}}`、`{{dashboard_end_yyyymmdd}}`、`[500, 1000)` 和完整 `date_filter`；断言 `extract_nested_json` 返回的 JSON 可解析且保留 `date_filter`。

- [x] **Step 2: 验证测试按预期失败**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_utils.py::test_extract_nested_json_ignores_brackets_inside_sql_string -q`

Expected: FAIL，当前函数返回 `None`。

- [x] **Step 3: 最小实现**

在括号扫描状态机中增加 `in_string` 与 `escaped` 状态；字符串内不维护括号栈，反斜杠转义后的双引号不结束字符串。

- [x] **Step 4: 验证测试与相关解析测试通过**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_utils.py backend/tests/test_chat_dashboard_date_filter.py -q`

Expected: 所有测试通过。

### Task 2: 当前业务日实时 SQL 日期渲染

**Files:**
- Modify: `backend/apps/chat/service/chat_date_filter.py:158`
- Modify: `backend/apps/dashboard/crud/dashboard_date_filter.py:324`
- Test: `backend/tests/test_chat_dashboard_date_filter.py`

**Interfaces:**
- Consumes: `render_chat_date_filter_sql(sql, datasource_type, pivot, today=None) -> str`。
- Produces: “今天/今日/当天”归一化为 `today`；当物理表为 `event_realtime` 且日期表达式严格解析为 `today..today` 时渲染受控 token；其他实时范围继续抛出 `ChatDateFilterConfigurationError("realtime_table")`。

- [x] **Step 1: 写失败测试**

使用 `event_realtime`、`yyyymmdd_number` token、当天动态表达式 `offset=0..0` 和固定 `today=date(2026, 8, 4)`；断言 SQL 中两个 token 都变成 `20260804`。

- [x] **Step 2: 写保护测试**

使用同一实时 SQL 但表达式为过去 7 个完整日；断言仍抛出 `realtime_table`。

- [x] **Step 3: 验证当天测试按预期失败**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_chat_dashboard_date_filter.py -k realtime -q`

Expected: 当前日测试 FAIL，错误为 `realtime_table`；保护测试 PASS。

- [x] **Step 4: 最小实现**

为 `prepare_dashboard_date_filter` 增加默认关闭的当前日实时开关；聊天渲染入口显式开启。仅对可解析、参数完整且解析范围等于当前业务日的 pivot 放行，不绕过 token/字段校验；普通 Dashboard 和历史范围保持原有行为。

- [x] **Step 5: 验证日期与 Smart Q&A 测试通过**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_chat_dashboard_date_filter.py tests/test_smart_qa_graph.py -q`

Expected: 所有测试通过。

### Task 3: 综合回归与真实记录复测

**Files:**
- Verify: `backend/common/utils/utils.py`
- Verify: `backend/apps/chat/service/chat_date_filter.py`
- Verify: `backend/tests/test_utils.py`
- Verify: `backend/tests/test_chat_dashboard_date_filter.py`

**Interfaces:**
- Consumes: Task 1、Task 2 的现有接口兼容实现。
- Produces: 可审查的测试输出和两个实际问题的复测记录。

- [x] **Step 1: 运行完整相关测试**

Run: `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests/test_utils.py tests/test_chat_dashboard_date_filter.py tests/test_smart_qa_graph.py tests/test_sql_repair.py -q`

Expected: 所有测试通过。

- [x] **Step 2: 审查差异**

Run: `git diff --check` 和 `git diff --stat`。

Expected: 无空白错误，差异只覆盖设计文档、计划、三个生产文件和对应测试。

- [x] **Step 3: 在修复代码环境中复测 #65 与 #96**

以最大并发 2 提交原始问题，核对新 `record_id` 的 SQL、数据、图表和错误字段。

Expected: #65 不再出现 `missing_date_filter`；#96 不再出现 `realtime_table`。若业务数据本身不可用，必须单独分类，不能视为日期修复失败。
