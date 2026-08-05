# AI Dashboard Date Template Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure explicit-date Smart Q&A time-series responses save reusable dashboard date tokens and a complete `date_filter`, including realtime event queries, while preserving metric and ordinary-dashboard behavior.

**Architecture:** Enforce the generic contract at `normalize_chat_date_filter_for_question()`, where the user question, chart type, SQL, and model payload are available, so an incomplete explicit-date response enters the existing SQL repair path. Align platform and datasource-scoped Data Skills with that runtime contract, then publish their idempotent seed definitions with backup, compare-and-swap, embedding refresh, and independent readback.

**Tech Stack:** Python 3, pytest, Smart Q&A graph/LLM services, PostgreSQL `custom_prompt`, datasource-scoped Data Skills.

## Global Constraints

- Do not change ordinary dashboard defaults or the Smart Q&A default past-seven-days behavior.
- Preserve fixed-semantic `metric` responses and questions without a supported explicit date phrase.
- Do not hardcode table names, date columns, datasource IDs, products, or business metrics in shared backend validation.
- Do not restore any blanket realtime-current-day restriction and do not migrate historical ChatRecords.
- Keep platform Skill 281 unchanged; modify only Skills 282, 283, and flam Skill 230.
- Use the existing `missing_date_filter` error and `DATE_FILTER_CONFIGURATION` SQL repair classification.
- All source, test, script, and runtime changes must stay in linked worktree `D:\AIWork3\chat-bi\.worktrees\codex-ai-dashboard-date-template-contract` on branch `codex/ai-dashboard-date-template-contract`.

---

### Task 1: Enforce The Explicit-Date Response Contract

**Files:**
- Modify: `backend/tests/test_chat_dashboard_date_filter.py`
- Modify: `backend/apps/chat/service/chat_date_filter.py`

**Interfaces:**
- Consumes: `normalize_chat_date_filter_for_question(question: str | None, payload: Any, sql: str, chart_type: str)` and existing explicit-date regexes.
- Produces: missing payloads for supported explicit-date, non-`metric` questions raise `ChatDateFilterConfigurationError("missing_date_filter")`; all existing valid and exempt paths retain their current return values.

- [ ] **Step 1: Add focused failing normalization tests**

Add cases to `backend/tests/test_chat_dashboard_date_filter.py` that assert:

```python
with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
    normalize_chat_date_filter_for_question(
        "按小时统计今天的付费次数",
        None,
        "SELECT COUNT(*) FROM event_realtime WHERE dt = 20260805",
        "line",
    )
```

Add the same expectation for `"最近14天每日付费金额趋势"`, plus assertions that an explicit-today `metric` and a non-explicit question with no payload still return `None`.

- [ ] **Step 2: Add a failing `LLMService.check_sql()` repair-boundary regression**

Build the existing lightweight `LLMService` fixture with an explicit-today question and a line-chart JSON response containing fixed-date SQL but no `date_filter`. Assert `check_sql()` raises `SingleMessageError` whose text contains `missing_date_filter`, proving the graph can classify it as `DATE_FILTER_CONFIGURATION`.

- [ ] **Step 3: Run the new tests and confirm RED**

Run:

```powershell
& 'D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe' -m pytest tests/test_chat_dashboard_date_filter.py -q
```

Expected: only the new missing-payload explicit-date tests fail because current code returns `None`.

- [ ] **Step 4: Implement the minimal generic guard**

In `backend/apps/chat/service/chat_date_filter.py`, add a private predicate using the existing patterns:

```python
def _question_requires_date_filter(question: str | None, chart_type: str) -> bool:
    if str(chart_type or "").strip().lower() == "metric":
        return False
    question_text = str(question or "")
    return bool(
        _EXPLICIT_CURRENT_DAY_PATTERN.search(question_text)
        or _EXPLICIT_PAST_DAYS_PATTERN.search(question_text)
    )
```

Before delegating a non-dict payload in `normalize_chat_date_filter_for_question()`, raise `ChatDateFilterConfigurationError("missing_date_filter")` when this predicate is true. Leave valid-payload normalization and ambiguous mixed-date handling on the existing path.

- [ ] **Step 5: Run the focused tests and confirm GREEN**

Run the Task 1 pytest command again. Expected: all tests pass, including valid realtime templates, literal-to-token rewriting, metric exemption, and no-date exemption.

### Task 2: Align Platform Data Skills 282 And 283

**Files:**
- Modify: `backend/tests/test_data_skill_conflict_regressions.py`
- Modify: `tools/seed_platform_realtime_event_table_skill.py`
- Modify: `tools/seed_platform_date_field_usage_skill.py`

**Interfaces:**
- Consumes: `realtime_seed.SKILL`, `seed_platform_date_field_usage_skill.SKILL`, and the unchanged platform Skill 281 contract.
- Produces: platform seed prompts that allow parameterized realtime partitions and require a complete today template for non-`metric` time series.

- [ ] **Step 1: Add failing prompt-contract tests**

Import the date-field seed beside the realtime seed. Assert Skill 282 includes both paired `{{dashboard_start_yyyymmdd}}` / `{{dashboard_end_yyyymmdd}}` tokens and `preset=today` for explicit-today non-`metric` time series. Assert Skill 283 names `partition_date` and `realtime_partition` as parameterizable roles, and does not contain `默认实时查询不套用历史日期 pivot` or make `realtime_date_policy` a prerequisite.

- [ ] **Step 2: Run the skill regression tests and confirm RED**

Run:

```powershell
& 'D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe' -m pytest tests/test_data_skill_conflict_regressions.py tests/test_data_skill_sql_validation.py -q
```

Expected: the new assertions fail against the old realtime-default and policy-prerequisite wording.

- [ ] **Step 3: Update Skill 282 selection guidance**

Retain realtime-vs-history table selection. Replace “直接限制当前业务日分区” with explicit guidance that a non-`metric` today time series must save paired dashboard tokens and return:

```json
{"time_field":"<Schema time field>","date_parameter_type":"<Schema date encoding>","date_expression":{"version":1,"mode":"preset","preset":"today"}}
```

State that fixed semantic `metric` responses remain exempt and that runtime renders the actual business date.

- [ ] **Step 4: Update Skill 283 date-role guidance**

Treat `partition_date` and `realtime_partition` as parameterizable when Schema supplies the field and encoding. Remove the blanket no-pivot realtime default. Describe `realtime_date_policy` only as an optional source of explicit extra restrictions, not a prerequisite for paired tokens or `date_filter`.

- [ ] **Step 5: Run platform skill tests and confirm GREEN**

Run the Task 2 pytest command. Expected: all prompt and SQL validation regressions pass.

### Task 3: Correct The Flam Payment Skill Contract

**Files:**
- Modify: `backend/tests/test_flam_first_zombie_data_skill_seed.py`
- Modify: `tools/seed_flam_first_zombie_data_skills.py`

**Interfaces:**
- Consumes: the `flam 付费与 LTV 口径` entry in `DATA_SKILLS`.
- Produces: flam Skill 230 with valid paired double-brace tokens and explicit today-realtime non-`metric` template guidance.

- [ ] **Step 1: Add a failing flam Skill 230 regression**

Locate the payment/LTV Skill by name. Assert its rendered prompt contains both valid double-brace tokens, contains `preset=today` and realtime non-`metric` guidance, and does not contain standalone single-brace `{dashboard_start_yyyymmdd}` or `{dashboard_end_yyyymmdd}` tokens.

- [ ] **Step 2: Run the flam seed tests and confirm RED**

Run:

```powershell
& 'D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe' -m pytest tests/test_flam_first_zombie_data_skill_seed.py -q
```

Expected: the new test exposes the rendered single-brace placeholder and missing today-realtime contract.

- [ ] **Step 3: Fix only the payment/LTV seed prompt**

Because the Skill body is an f-string, encode literal double braces with four source braces. Add a today-realtime non-`metric` clause requiring paired tokens and a complete `date_filter` with `preset=today`; retain all flam-specific metric definitions in the datasource-scoped Skill.

- [ ] **Step 4: Run the flam seed tests and confirm GREEN**

Run the Task 3 pytest command. Expected: all existing datasource-scope, SQL safety, and business-rule assertions remain green.

### Task 4: Verify The Runtime And Semantic Changes Together

**Files:**
- Test: `backend/tests/test_chat_dashboard_date_filter.py`
- Test: `backend/tests/test_data_skill_conflict_regressions.py`
- Test: `backend/tests/test_data_skill_sql_validation.py`
- Test: `backend/tests/test_flam_first_zombie_data_skill_seed.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: regression evidence for the exact user-visible symptom and related SQL repair paths.

- [ ] **Step 1: Run the primary regression suite**

```powershell
& 'D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe' -m pytest tests/test_chat_dashboard_date_filter.py tests/test_data_skill_conflict_regressions.py tests/test_data_skill_sql_validation.py tests/test_flam_first_zombie_data_skill_seed.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Discover and run related Smart Q&A repair tests**

Use `rg -l "DATE_FILTER_CONFIGURATION|missing_date_filter|normalize_chat_date_filter_for_question" backend/tests` from the worktree root, then run every additional relevant test module not already covered. Expected: all pass.

- [ ] **Step 3: Check patch hygiene**

Run `git diff --check` and inspect `git diff --stat` plus `git status --short`. Expected: no whitespace errors and no unrelated files.

### Task 5: Publish And Independently Verify Live Data Skills

**Files:**
- Runtime data: PostgreSQL `custom_prompt` rows 230, 281, 282, and 283.
- Backup artifacts: worktree `.codex-runtime/` paths created by the seed publishers and excluded from Git.

**Interfaces:**
- Consumes: tested seed definitions for Skills 230, 282, and 283; existing Skill 281 as the unchanged baseline.
- Produces: live Skill rows with unchanged tenant/scope identity, updated prompts, refreshed embeddings, and verified signatures.

- [ ] **Step 1: Read back the four target rows before mutation**

Query `custom_prompt` by IDs 230, 281, 282, 283 and record ID, tenant, visibility, datasource scope, prompt hash, embedding presence, and embedding signature. Verify Skill 230 remains tenant `7477202383789887488` / datasource `3`, while platform Skills remain platform-scoped.

- [ ] **Step 2: Dry-run both platform publishers**

Run from the worktree root:

```powershell
& 'D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe' tools/seed_platform_realtime_event_table_skill.py --mode dry-run
& 'D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe' tools/seed_platform_date_field_usage_skill.py --mode dry-run
```

Expected: each reports exactly one marker-scoped target and no mutation.

- [ ] **Step 3: Audit and narrow the flam publishing operation before execution**

Confirm the flam script locks/upserts only tenant `7477202383789887488`, datasource `3`, and expected marker rows. Create a pre-change JSON backup of Skill 230 and use compare-and-swap semantics for its current definition; do not blindly rewrite or delete unrelated flam Skills merely because the existing script can upsert the full catalog.

- [ ] **Step 4: Apply Skills 282 and 283, then publish Skill 230 narrowly**

Run the two platform scripts with `--mode apply`. Publish the tested Skill 230 definition through the audited narrow path, refresh embeddings only for changed IDs, and stop on concurrent-definition mismatch.

- [ ] **Step 5: Independently read back and validate Skills 230, 281, 282, and 283**

Verify IDs, tenants, scopes, and datasource bindings are unchanged; Skill 281's prompt hash is unchanged; Skills 230/282/283 contain their expected markers and valid paired double-brace tokens; old conflicting text and standalone single-brace tokens are absent; embeddings and signatures are populated and match current definitions.

- [ ] **Step 6: Perform final verification before reporting completion**

Re-run the Task 4 primary suite and `git diff --check`, inspect the final diff, then use the `verification-before-completion` skill. Report exact test counts, published Skill IDs, linked worktree path, and branch; do not claim historical ChatRecords were rewritten.
