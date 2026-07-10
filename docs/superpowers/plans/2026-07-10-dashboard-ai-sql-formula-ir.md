# Dashboard AI SQL Formula IR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/dashboard_ai_sql_formula_ir_diagnosis_redesign.md` 落地手动看板 AI SQL 的公式 IR、确定性校验和诊断链路重排，避免 LLM 诊断误阻断合法公式。

**Architecture:** 后端新增手动配置归一化、公式 IR 构建、确定性校验、SQL plan 构建和 advice 合并节点；旧 LLM `diagnose_config` 不再参与 graph 阻断。SQL 生成继续复用现有 LLM SQL 节点，但会收到公式 IR 和 SQL plan 作为结构化上下文。

**Tech Stack:** Python 3、FastAPI/Pydantic、LangGraph、pytest、Vue 3、Element Plus、Node.js 静态测试。

## Global Constraints

- 代码和文档默认使用中文说明。
- 只允许代码层产生阻断；LLM 或 advice 文案不能覆盖确定性校验的 `can_generate_sql=true`。
- 第一版公式语言只支持基础指标引用、公式内 `atomicMetric`、`+ - * /`、括号、数字常量、小数位和除法 `NULLIF` 保护。
- 复杂公式不因复杂本身阻断；只有超出当前公式语言能力或配置不完整才阻断。
- 不把业务口径硬编码到平台代码里；业务语义仍由 Data Skill、字段元数据和当前配置表达。

---

### Task 1: 后端公式 IR 和确定性校验

**Files:**
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py`
- Modify: `backend/apps/dashboard/models/dashboard_model.py`
- Test: `backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:**
- Produces: `_normalize_manual_config(request: DashboardAiSqlGenerateRequest) -> dict[str, Any]`
- Produces: `_build_formula_ir(normalized_config: dict[str, Any]) -> dict[str, Any]`
- Produces: `_deterministic_validate_manual_config(request, normalized_config, formula_ir) -> DashboardAiSqlGenerateResponse`

- [ ] **Step 1: Write failing tests**

Add tests that assert:

```python
def test_formula_ir_allows_cross_event_atomic_metric_formula_without_blocking() -> None:
    ...

def test_formula_ir_blocks_incomplete_formula_token_sequence() -> None:
    ...

def test_explain_advice_keeps_success_when_deterministic_validation_passed() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dashboard_ai_sql_generator.py -q`

Expected: FAIL because formula IR and deterministic validation helpers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement normalization, expression parser, deterministic validation response, and warning merge.

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dashboard_ai_sql_generator.py -q`

Expected: PASS for the dashboard AI SQL generator tests.

### Task 2: 后端 graph 重排

**Files:**
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py`
- Test: `backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:**
- Produces: `_node_normalize_manual_config`
- Produces: `_node_build_formula_ir`
- Produces: `_node_deterministic_validate`
- Produces: `_route_after_deterministic_validate`
- Produces: `_node_build_sql_plan`
- Produces: `_node_explain_advice`

- [ ] **Step 1: Write failing tests**

Add tests that assert route decisions only read deterministic validation, and SQL prompt includes formula IR / SQL plan.

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dashboard_ai_sql_generator.py -q`

Expected: FAIL before graph nodes and prompt context are implemented.

- [ ] **Step 3: Write minimal implementation**

Replace runtime graph edges with:

```text
collect_context -> normalize_manual_config -> build_formula_ir -> deterministic_validate
  -> build_sql_plan -> generate_sql -> validate_sql -> explain_advice -> finalize_response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dashboard_ai_sql_generator.py -q`

Expected: PASS.

### Task 3: 前端 warning 展示和上下文瘦身

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.event-filter-advice.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`

**Interfaces:**
- Consumes: backend response `warnings: list[str]`
- Produces: warning 进入建议区但不进入阻断问题

- [ ] **Step 1: Write failing tests**

Add static assertions that `warnings` are collected as non-blocking suggestions and `availableJsonFields` is not sent in AI SQL context.

- [ ] **Step 2: Run test to verify it fails**

Run: `node frontend/src/views/dashboard/common/DashboardSqlEditor.event-filter-advice.test.mjs`

Expected: FAIL before frontend changes.

- [ ] **Step 3: Write minimal implementation**

Update advice item collection and remove `availableJsonFields` from `collectBuilderAiContext()`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.event-filter-advice.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
```

Expected: PASS.

### Task 4: Final verification

**Files:**
- Review: `docs/dashboard_ai_sql_formula_ir_diagnosis_redesign.md`
- Review: `docs/superpowers/plans/2026-07-10-dashboard-ai-sql-formula-ir.md`

- [ ] **Step 1: Run focused backend tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dashboard_ai_sql_generator.py -q`

- [ ] **Step 2: Run focused frontend tests**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.event-filter-advice.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
```

- [ ] **Step 3: Check git diff**

Run: `git diff --stat`

- [ ] **Step 4: Report verification evidence**

Summarize changed files, test commands, and remaining risks.
