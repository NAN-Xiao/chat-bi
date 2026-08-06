# Knowledge Base RAG Batch 08 SQL Semantic Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one immutable business semantic context and use it for Smart Q&A and AI dashboard SQL generation without changing existing Data Skill selection priority or limits.

**Architecture:** Build the permission snapshot first, derive an eligible Skill ID set from current object projections, pass that set into the existing `find_data_skills` authority, then combine selected Skills, tracking/structured records, and one knowledge retrieval result. Attach the immutable result to `BusinessSqlContext`, persist hashes/citations in existing snapshots, and keep execution-time AST and permission revalidation as the final authority.

**Tech Stack:** Existing `find_data_skills`, SQL context service, knowledge retrieval, permission snapshots, Smart Q&A graph, dashboard AI SQL graph, pytest.

## Global Constraints

- `find_data_skills` remains the only Skill selection authority.
- Preserve explicit selection, automatic embedding/keyword matching, foundation Skills, `_dedupe_overridden_data_skills`, datasource scoping, three visibility scopes, and the current maximum of 12.
- The knowledge feature does not change or bypass existing MCP-related Skill behavior; it only intersects candidates with object eligibility.
- Missing/FAILED/STALE Skill projection, source-hash mismatch, projector-version mismatch, or unresolved object removes the Skill before its text is loaded.
- An explicitly selected ineligible Skill returns a permission/applicability error and never falls back to automatic matching.
- Each request/task performs knowledge retrieval once and reuses the fixed context for generation, repair, chart planning, and response.
- Knowledge and Skill content cannot override datasource selection, permission, schema, SQL safety, event constraints, row filters, or masking.

---

### Task 1: Eligible Skill Filtering in the Existing Selector

**Files:**
- Modify: `backend/apps/chat/curd/custom_prompt.py`
- Modify: `backend/apps/chat/curd/skill_object_references.py`
- Test: `backend/tests/test_data_skill_context_integration.py`
- Test: `backend/tests/test_skill_object_projection.py`

**Interfaces:**
- Consumes: `data_skill_object_projection`, object resolution, and `PermissionScopeSnapshot`.
- Produces: `eligible_data_skill_ids()` and optional `eligible_skill_ids` argument on `find_data_skills()`.

- [ ] **Step 1: Write explicit/automatic and zero-reference eligibility tests**

```python
def test_explicit_ineligible_skill_returns_error_not_auto_fallback(session, skill, snapshot):
    with pytest.raises(DataSkillEligibilityError) as error:
        find_data_skills(
            session,
            datasource=9,
            skill_id=skill.id,
            current_user_id=8,
            tenant_id=2,
            eligible_skill_ids=frozenset(),
        )
    assert error.value.code == "DATA_SKILL_NOT_AVAILABLE"


def test_ready_zero_reference_skill_remains_candidate(session, neutral_skill, snapshot):
    eligible = eligible_data_skill_ids(session, snapshot=snapshot)
    assert neutral_skill.id in eligible
```

- [ ] **Step 2: Run and confirm the selector cannot accept eligibility**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_data_skill_context_integration.py backend/tests/test_skill_object_projection.py -q`

Expected: FAIL because `eligible_skill_ids` is not accepted or enforced.

- [ ] **Step 3: Add a narrowing-only selector argument**

Append `eligible_skill_ids: Collection[int] | None = None` after the existing `current_user` parameter without changing the order/defaults of any existing parameter. The return type remains `tuple[str, list[str], int | None]`.

Filter rows by `eligible_skill_ids` before reading `prompt`, parsing required tables, ranking, or building output. `None` preserves the exact old path for callers not yet migrated. For explicit selection, distinguish absent/unauthorized/ineligible from no automatic match and raise a safe domain error. Do not reorder or re-add rows after current dedupe/ranking.

- [ ] **Step 4: Run the full Skill selection regression**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_data_skill_context_integration.py backend/tests/test_skill_object_projection.py backend/tests/test_custom_prompt_datasource_scope.py backend/tests/test_data_skill_conflict_regressions.py -q`

Expected: PASS for explicit, automatic, personal/workspace/platform, foundation, overrides, and at-most-12 behavior.

- [ ] **Step 5: Commit eligible Skill filtering**

```powershell
git add backend/apps/chat/curd/custom_prompt.py backend/apps/chat/curd/skill_object_references.py backend/apps/chat/curd/skill_object_projection.py backend/tests/test_data_skill_context_integration.py backend/tests/test_skill_object_projection.py
git commit -m "feat: 按对象权限收窄 Data Skill 候选"
```

### Task 2: Unified Business Semantic Context Service

**Files:**
- Create: `backend/apps/datasource/crud/semantic_context.py`
- Modify: `backend/apps/datasource/crud/sql_engine.py`
- Modify: `backend/apps/chat/curd/agent_context_snapshot.py`
- Test: `backend/tests/test_business_semantic_context.py`
- Test: `backend/tests/test_sql_engine_context.py`

**Interfaces:**
- Consumes: permission snapshot service, eligible Skills, existing `find_data_skills`, structured context, knowledge retrieval, and audit writer.
- Produces: `SelectedSkillSnapshot`, `BusinessSemanticContext`, `BusinessSemanticContextService.build()`, and `BusinessSqlContext.semantic`.

- [ ] **Step 1: Write order, snapshot-hash, and single-retrieval tests**

```python
def test_semantic_context_builds_permission_before_skill_and_retrieval(call_trace, service):
    service.build(**semantic_request())
    assert call_trace == ["permission", "eligible_skills", "find_data_skills", "schema", "structured", "retrieval", "audit"]


def test_context_hash_changes_when_permission_skill_or_knowledge_version_changes(service):
    base = service.build(**semantic_request())
    assert service.build(**semantic_request(permission_epoch=2)).context_hash != base.context_hash
    assert service.build(**semantic_request(skill_source_hash="b")).context_hash != base.context_hash
    assert service.build(**semantic_request(knowledge_version_hash="c")).context_hash != base.context_hash
```

- [ ] **Step 2: Run and confirm unified context is absent**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_business_semantic_context.py backend/tests/test_sql_engine_context.py -q`

Expected: FAIL because `BusinessSqlContext` currently combines tracking and Skill text only.

- [ ] **Step 3: Implement the immutable semantic data contract**

```python
@dataclass
class BusinessSemanticContext:
    permission_snapshot: PermissionScopeSnapshot
    selected_skills: list[SelectedSkillSnapshot] = field(default_factory=list)
    skill_text: str = ""
    skill_selection_hash: str | None = None
    tracking_config: str = ""
    tracking_summary: list[str] = field(default_factory=list)
    knowledge_context: str = ""
    knowledge_citations: list[KnowledgeCitation] = field(default_factory=list)
    knowledge_version_hash: str | None = None
    warnings: list[str] = field(default_factory=list)
    context_hash: str | None = None
```

`BusinessSemanticContextService.build()` confirms datasource access/binding, builds one snapshot, computes eligible IDs, calls `find_data_skills` once, builds authorized schema, loads structured context, calls knowledge retrieval once, and writes a semantic audit. Hash IDs, permission version, schema hash, Skill selection hash, knowledge version hash, and citation IDs, not bodies.

- [ ] **Step 4: Extend `BusinessSqlContext` compatibly**

Add required `semantic: BusinessSemanticContext`. Keep `data_skill`, `data_skill_list`, `tracking_config`, `tracking_summary`, and `warnings` as read-only compatibility properties delegating to `semantic`. Update `snapshot_metadata()` to include permission version, schema hash, selected Skill IDs/mode hash, knowledge version hash, citation safe summaries, and warnings.

- [ ] **Step 5: Run context regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_business_semantic_context.py backend/tests/test_sql_engine_context.py backend/tests/test_tracking_context_projection.py backend/tests/test_data_skill_context_integration.py -q`

Expected: PASS with one retrieval and no duplicated selection path.

- [ ] **Step 6: Commit semantic context service**

```powershell
git add backend/apps/datasource/crud/semantic_context.py backend/apps/datasource/crud/sql_engine.py backend/apps/chat/curd/agent_context_snapshot.py backend/tests/test_business_semantic_context.py backend/tests/test_sql_engine_context.py
git commit -m "feat: 统一构建业务语义上下文快照"
```

### Task 3: Smart Q&A Integration

**Files:**
- Modify: `backend/apps/chat/task/llm.py`
- Modify: `backend/apps/chat/task/smart_qa_graph.py`
- Modify: `backend/apps/chat/curd/agent_context_snapshot.py`
- Test: `backend/tests/test_knowledge_smart_qa_context.py`
- Test: `backend/tests/test_smart_qa_graph.py`

**Interfaces:**
- Consumes: `BusinessSqlContextService.build()` and existing SQL execution permission recheck.
- Produces: fixed semantic context in both Smart Q&A paths and safe citation metadata in task/conversation results.

- [ ] **Step 1: Write one-build, repair-reuse, and citation safety tests**

```python
def test_smart_qa_builds_context_once_across_sql_repair(graph_harness):
    graph_harness.force_first_sql_failure()
    result = graph_harness.run(question="revenue")
    assert graph_harness.semantic_build_calls == 1
    assert graph_harness.retrieval_calls == 1
    assert result.agent_context_snapshot["business_context"]["knowledge_citations"]


def test_smart_qa_result_does_not_expose_chunk_or_file_storage(result):
    serialized = json.dumps(result.public_payload, ensure_ascii=False)
    assert "file_id" not in serialized
    assert "UPLOAD_DIR" not in serialized
```

- [ ] **Step 2: Run and confirm Smart Q&A lacks knowledge context**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_smart_qa_context.py backend/tests/test_smart_qa_graph.py -q`

Expected: FAIL because the snapshot has no knowledge version/citations and paths can rebuild context separately.

- [ ] **Step 3: Inject one context into both Smart Q&A implementations**

Build after datasource confirmation and before prompt/SQL planning. Store the object on the task/service and pass the same reference to SQL generation, repair, chart configuration, insight, and final response. Add `<retrieved-knowledge priority="reference-only">` after higher-authority schema/tracking/Skill sections. Continue using execution-time permission recheck for every SQL call.

- [ ] **Step 4: Run Smart Q&A regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_smart_qa_context.py backend/tests/test_smart_qa_graph.py backend/tests/test_smart_qa_task_generator.py backend/tests/test_chat_api_sse.py -q`

Expected: PASS for legacy and graph paths, retries, persisted snapshot, and safe citation response.

- [ ] **Step 5: Commit Smart Q&A integration**

```powershell
git add backend/apps/chat/task/llm.py backend/apps/chat/task/smart_qa_graph.py backend/apps/chat/curd/agent_context_snapshot.py backend/tests/test_knowledge_smart_qa_context.py backend/tests/test_smart_qa_graph.py
git commit -m "feat: 在 Smart Q&A 使用统一知识上下文"
```

### Task 4: AI Dashboard SQL Integration

**Files:**
- Modify: `backend/apps/dashboard/models/dashboard_model.py`
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py`
- Test: `backend/tests/test_knowledge_dashboard_ai_sql.py`
- Test: `backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:**
- Consumes: normalized dashboard builder intent and unified `BusinessSqlContext`.
- Produces: `knowledge_citations`, `knowledge_version_hash`, and `retrieval_warnings` on `DashboardAiSqlGenerateResponse`.

- [ ] **Step 1: Write graph-order and response-snapshot tests**

```python
def test_dashboard_retrieval_uses_normalized_builder_intent(generator):
    generator.generate(builder_request(metric="Revenue", dimension="Region"))
    assert generator.trace.index("normalize_manual_config") < generator.trace.index("build_business_sql_context")
    assert generator.retrieval_query == normalized_intent_text(metric="Revenue", dimension="Region")


def test_dashboard_response_saves_references_not_knowledge_body(response):
    assert response.knowledge_citations
    assert response.knowledge_version_hash
    assert "retrieved-knowledge" not in response.model_dump_json()
```

- [ ] **Step 2: Run and confirm dashboard response lacks knowledge fields**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_dashboard_ai_sql.py backend/tests/test_dashboard_ai_sql_generator.py -q`

Expected: FAIL on absent response fields or incorrect graph order.

- [ ] **Step 3: Integrate after intent normalization and before formula planning**

Use the graph order `collect_context -> normalize_manual_config -> build_permission_scope -> build_business_sql_context -> build_formula_ir -> deterministic_validate -> build_sql_plan -> generate_sql -> validate_sql -> finalize_response`. Build the knowledge query from normalized intent fields, return safe citation summaries/warnings, and save only IDs/version/hash with dashboard configuration.

- [ ] **Step 4: Run dashboard SQL regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_dashboard_ai_sql.py backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_dashboard_execution_datasource.py backend/tests/test_dashboard_permission_cache.py -q`

Expected: PASS; selected datasource and execution permission remain authoritative.

- [ ] **Step 5: Commit dashboard SQL integration**

```powershell
git add backend/apps/dashboard/models/dashboard_model.py backend/apps/dashboard/crud/ai_sql_generator.py backend/tests/test_knowledge_dashboard_ai_sql.py backend/tests/test_dashboard_ai_sql_generator.py
git commit -m "feat: 在 AI 看板 SQL 使用知识上下文"
```
