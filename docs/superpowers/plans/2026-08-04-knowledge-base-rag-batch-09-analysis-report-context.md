# Knowledge Base RAG Batch 09 Analysis and Report Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the comprehensive analysis assistant and dashboard report interpretation reuse the same immutable, permission-safe semantic context as SQL surfaces.

**Architecture:** Add a small analysis-context adapter around `BusinessSqlContextService` rather than expanding the existing analysis API file with another context implementation. Build once before planning, retain the fixed semantic snapshot for plan/repair/summary/report stages, and rely on execution-time permission version recheck for every query in long-running analyses.

**Tech Stack:** FastAPI SSE, existing analysis assistant, unified semantic context, dashboard report target validation, pytest.

## Global Constraints

- Do not create another Skill collector, tracking collector, or knowledge retriever in the analysis module.
- Do not use `include_all_target_scopes=True` for report interpretation.
- Visible chart data remains the factual source for report conclusions; knowledge explains definitions and context but does not recalculate chart values.
- Plan, time policy, SQL generation, SQL repair, semantic validation, block summary, final answer, and report interpretation use the same captured context.
- Permission revocation during a long task triggers the batch 3 execution-time recheck and blocks or rebuilds before the next SQL execution.
- Retrieval failure is surfaced as a warning; permission, schema, or explicit structured-mapping failure is not silently swallowed.

---

### Task 1: Analysis Semantic Context Adapter

**Files:**
- Create: `backend/apps/analysis_assistant/service/semantic_context.py`
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py`
- Test: `backend/tests/test_knowledge_analysis_assistant.py`

**Interfaces:**
- Consumes: `BusinessSqlContextService.build()`, analysis request, selected datasource, and target scope.
- Produces: `AnalysisSemanticContextAdapter.build()` and `AnalysisSemanticContext`.

- [ ] **Step 1: Write build-once and stage-identity tests**

```python
def test_analysis_builds_context_once_before_plan(analysis_harness):
    result = analysis_harness.run(question="compare revenue", force_sql_repair=True)
    assert analysis_harness.semantic_build_calls == 1
    assert analysis_harness.trace.index("semantic_context") < analysis_harness.trace.index("plan")
    assert len(set(analysis_harness.context_hashes_by_stage.values())) == 1
    assert result.context_snapshot["business_context"]["knowledge_version_hash"]
```

- [ ] **Step 2: Run and observe duplicate/ad-hoc context assembly**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_analysis_assistant.py -q`

Expected: FAIL because analysis currently merges tracking and Skill strings directly.

- [ ] **Step 3: Implement a narrow adapter and replace call-site assembly**

```python
@dataclass(frozen=True)
class AnalysisSemanticContext:
    business_sql_context: BusinessSqlContext
    prompt_text: str
    public_snapshot: dict[str, Any]


class AnalysisSemanticContextAdapter:
    @staticmethod
    def build(*, session, current_user, request, datasource_id: int) -> AnalysisSemanticContext:
        business_context = BusinessSqlContextService.build(
            session=session,
            current_user=current_user,
            tenant_id=require_current_tenant_id(current_user),
            datasource_id=datasource_id,
            question=request.question,
            target_scope=request.target_scope,
            data_skill_id=request.data_skill_id,
        )
        return AnalysisSemanticContext(
            business_sql_context=business_context,
            prompt_text=business_context.semantic_context,
            public_snapshot=business_context.snapshot_metadata(),
        )
```

Build one `BusinessSqlContext` with `target_scope=ANALYSIS_ASSISTANT`, construct prompt sections in authority order, and expose only safe citation summaries to SSE. Replace runtime calls that separately invoke `find_data_skills` or tracking collectors in the main analysis path; retain unrelated custom-agent logic and current model selection.

- [ ] **Step 4: Thread the same object through all stages**

Pass `AnalysisSemanticContext` to planning, time policy, SQL generation, repair, semantic validation, per-block summary, and final answer. Do not rebuild after an LLM or SQL retry. Each actual SQL execution continues to receive the captured permission snapshot for pre-execution version recheck.

- [ ] **Step 5: Run analysis regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_analysis_assistant.py backend/tests/test_analysis_assistant_sql_generation.py backend/tests/test_analysis_assistant_time_policy.py backend/tests/test_analysis_assistant_permissions.py -q`

Expected: PASS for plan, repair, time policy, revocation, summaries, and SSE snapshot.

- [ ] **Step 6: Commit analysis integration**

```powershell
git add backend/apps/analysis_assistant/service/semantic_context.py backend/apps/analysis_assistant/api/analysis_assistant.py backend/tests/test_knowledge_analysis_assistant.py
git commit -m "feat: 在综合分析助手复用统一知识上下文"
```

### Task 2: Dashboard Question and Report Interpretation Integration

**Files:**
- Modify: `backend/apps/analysis_assistant/service/semantic_context.py`
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py`
- Test: `backend/tests/test_knowledge_report_interpretation.py`
- Test: `backend/tests/test_analysis_assistant_permissions.py`

**Interfaces:**
- Consumes: validated `ReportInterpretationTarget`, visible chart metadata/data, and unified semantic service.
- Produces: one context for `/analysis-assistant/report-interpretation` and safe citation/warning SSE events.

- [ ] **Step 1: Write target-scope, visible-fact, and failure-warning tests**

```python
def test_report_interpretation_uses_report_scope_not_all_scopes(report_harness):
    report_harness.run(question="explain change")
    assert report_harness.find_data_skills_args["target_scope"] == "REPORT_INTERPRETATION"
    assert report_harness.find_data_skills_args["include_all_target_scopes"] is False


def test_retrieval_failure_is_visible_warning_not_empty_context(report_harness):
    report_harness.fail_retrieval("embedding unavailable")
    events = report_harness.run(question="explain change")
    assert any(event["type"] == "context_warning" for event in events)
    assert report_harness.used_visible_chart_data is True
```

- [ ] **Step 2: Run and confirm report path uses separate collectors**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_report_interpretation.py backend/tests/test_analysis_assistant_permissions.py -q`

Expected: FAIL because report interpretation directly collects and merges Skill/tracking text.

- [ ] **Step 3: Route report interpretation through the adapter**

After `validate_dashboard_report_target`, resolve the selected/authorized datasource and build with `target_scope=REPORT_INTERPRETATION`. Build retrieval query from user question, visible chart title, fields, and metrics, excluding full row data. Supply visible chart values separately as factual evidence. Emit citations and warnings through SSE and remove runtime use of ad-hoc data-Skill/tracking collectors on this route.

- [ ] **Step 4: Run report regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_report_interpretation.py backend/tests/test_analysis_assistant_permissions.py backend/tests/test_dashboard_execution_datasource.py -q`

Expected: PASS for report scope, datasource permission, visible facts, retrieval warning, and safe citations.

- [ ] **Step 5: Commit report integration**

```powershell
git add backend/apps/analysis_assistant/service/semantic_context.py backend/apps/analysis_assistant/api/analysis_assistant.py backend/tests/test_knowledge_report_interpretation.py backend/tests/test_analysis_assistant_permissions.py
git commit -m "feat: 在看板问答与报告解读使用统一上下文"
```

### Task 3: Four-Surface Snapshot and Permission Regression Gate

**Files:**
- Modify: `backend/apps/chat/curd/agent_context_snapshot.py`
- Modify: `backend/tests/test_knowledge_analysis_assistant.py`
- Modify: `backend/tests/test_knowledge_report_interpretation.py`
- Modify: `backend/tests/test_knowledge_smart_qa_context.py`
- Modify: `backend/tests/test_knowledge_dashboard_ai_sql.py`

**Interfaces:**
- Consumes: all four surface integrations.
- Produces: versioned safe context snapshot contract shared by Smart Q&A, dashboard SQL, analysis assistant, and report interpretation.

- [ ] **Step 1: Add a cross-surface contract test**

```python
@pytest.mark.parametrize("surface", ["SMART_QA", "DASHBOARD_AI_SQL", "ANALYSIS_ASSISTANT", "REPORT_INTERPRETATION"])
def test_surface_snapshot_has_same_security_fields(surface, run_surface):
    snapshot = run_surface(surface).context_snapshot["business_context"]
    assert snapshot["permission_version"]
    assert snapshot["schema_hash"]
    assert "selected_skills" in snapshot
    assert "knowledge_citations" in snapshot
    assert "warnings" in snapshot
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "knowledge_context" not in serialized
    assert "skill_text" not in serialized
```

- [ ] **Step 2: Run all four surface tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_smart_qa_context.py backend/tests/test_knowledge_dashboard_ai_sql.py backend/tests/test_knowledge_analysis_assistant.py backend/tests/test_knowledge_report_interpretation.py -q`

Expected: PASS with identical security metadata and no body leakage.

- [ ] **Step 3: Run SQL execution and Skill regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_db_query_execution_controls.py backend/tests/test_event_permission_enforcement.py backend/tests/test_data_skill_context_integration.py backend/tests/test_data_skill_conflict_regressions.py -q`

Expected: PASS; all surfaces still fail closed on revoked permissions and preserve Skill selection behavior.

- [ ] **Step 4: Commit the cross-surface gate**

```powershell
git add backend/apps/chat/curd/agent_context_snapshot.py backend/tests/test_knowledge_analysis_assistant.py backend/tests/test_knowledge_report_interpretation.py backend/tests/test_knowledge_smart_qa_context.py backend/tests/test_knowledge_dashboard_ai_sql.py
git commit -m "test: 统一四类 AI 场景的语义快照契约"
```
