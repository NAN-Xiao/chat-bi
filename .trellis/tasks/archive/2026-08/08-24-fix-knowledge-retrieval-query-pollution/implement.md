# Implementation Plan

1. 加载 `trellis-before-dev` 和后端规范，复核统一语义层、检索服务及四类助手调用边界。
2. 在 `backend/apps/datasource/crud/semantic_context.py` 收窄 `_retrieval_query`：只返回清理后的主意图，并移除 Schema、允许表和 Skill 参数。
3. 扩展 `backend/tests/test_business_semantic_context.py`：捕获实际检索参数，覆盖短问题、辅助上下文变化和空问题；必要时补充检索服务阈值/空结果根因测试。
4. 运行统一语义、知识检索、Dashboard 和分析助手定向测试；处理任何真实契约回归，不添加静默兼容兜底。
5. 更新 `docs/dashboard_ai_sql_knowledge_skill_context_integration.md` 与 `.trellis/spec/backend/knowledge-base-rag.md`，替换已被真实故障否定的旧查询扩写规则。
6. 使用 `trellis-check` 执行规范检查、后端 lint/type/test 质量门，并记录结果到任务日志。
7. 按本地运行手册重启完整栈，核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`，确认 5173、8000、8001 和 Worker。
8. 通过真实 Smart Q&A 页面提问“商店购买”，核对知识引用和最新检索审计 query hash；验证不再引用 MAU、WAU、DAU、新增用户和付费用户。
9. 更新任务实现/检查记录和开发日志；提交前复核 worktree 只包含本任务改动。

## Validation Commands

```powershell
& backend\.venv\Scripts\python.exe -m pytest backend/tests/test_business_semantic_context.py backend/tests/test_knowledge_base_retrieval.py backend/tests/test_knowledge_dashboard_ai_sql.py backend/tests/test_knowledge_analysis_assistant.py
```

```powershell
.\tools\stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

## Risk And Rollback Points

- 风险：宽泛问题可能比旧行为召回更少知识。预期行为是无相关知识时返回空，不用辅助上下文制造命中。
- 风险：AI 看板依赖旧 Schema/Skill 扩写获得知识。规范化看板查询本身已包含显式指标、分组和筛选，应以它作为相关性权威；定向测试和真实调用覆盖该入口。
- 回滚点：本次无迁移；可回滚代码/文档提交，或临时关闭 `KNOWLEDGE_RETRIEVAL_ENABLED`。

## Start Gate

- [x] 用户批准最新规划摘要。
- [x] `prd.md`、`design.md`、`implement.md` 已完成并通过收敛检查。
- [x] 已显式运行 `task.py start`，当前任务来源为本 Codex session。

## Implementation Log

- 2026-08-24: User approved the implementation plan. Confirmed the active task, linked worktree, backend runtime guidance, and shared cross-layer contract before editing.
- 2026-08-24: Narrowed the shared retrieval query to the normalized caller-provided primary intent. Added service-boundary regressions for auxiliary-context isolation and blank-query handling. Updated the current dashboard integration document and backend RAG contract.
- 2026-08-24: Focused semantic-context tests passed (`6 passed`). The planned semantic/retrieval/dashboard/analysis suite passed (`18 passed`). Ruff, `py_compile`, and `git diff --check` passed.
- 2026-08-24: The first pytest attempt imported backend code from the separate `knowledge-base-rag` worktree through the shared virtual environment's editable path. Re-running with `PYTHONPATH=<task-worktree>/backend` confirmed the current source path and produced the passing results above.
- 2026-08-24: Started API, MCP, and one Worker from this linked worktree on queue `local-DONGJINCHAO-fix-kb-retrieval-query`. Verified ports 8000/8001/5173, frontend HTTP 200, backend HTTP 401, MCP HTTP 404, Worker startup log, and `LLM_REQUEST_TIMEOUT=120`, `LLM_TASK_MAX_WAIT_SECONDS=900`, `LLM_MAX_RETRIES=1`.
- 2026-08-24: Submitted `商店购买` through the authenticated Smart Q&A page. The two latest retrieval audits use the raw-intent SHA-256 `3a9928d280b14b3a0d9bd36b4a2ffb752b2559567575c7a3ab1b6858953bf18e`. Hits changed from MAU/WAU/DAU/new/paying-user chunks to the relevant `ShopBuyItem`, `ShopBuyComplete`, and purchase-process event chunks with scores `0.441597-0.508428`.

## Bug Analysis: Auxiliary Context Polluted Retrieval Relevance

### 1. Root Cause Category

- **Category**: B - Cross-Layer Contract, with D - Test Coverage Gap.
- **Specific Cause**: The shared semantic service treated permission/execution context as relevance intent and embedded long Schema and selected Skill text together with a short user question. Candidate filtering remained correct, but the similarity vector no longer represented the caller's primary intent.

### 2. Why Earlier Mitigations Would Fail

1. Raising the global threshold would not remove the false hits because the polluted query already scored them at `0.651525-0.704230`, and it would suppress legitimate low-confidence knowledge for unrelated questions.
2. Editing the five cited knowledge chunks would only move the symptom to other generic metric chunks because the query construction itself was wrong.
3. Special-casing `商店购买` or Smart Q&A would leave dashboard, report, and analysis-assistant callers exposed to the same shared-service behavior.

### 3. Prevention Mechanisms

| Priority | Mechanism | Specific Action | Status |
| --- | --- | --- | --- |
| P0 | Architecture | Make `_retrieval_query` accept only the caller-provided primary intent. | DONE |
| P0 | Regression test | Capture the real `search(query=...)` boundary and vary Schema, table, Skill, and surface inputs. | DONE |
| P0 | Empty-query test | Prove auxiliary context cannot manufacture a query and existing `EMPTY_QUERY` behavior remains active. | DONE |
| P1 | Executable specification | Record the primary-intent-only relevance contract in `knowledge-base-rag.md`. | DONE |
| P1 | Runtime verification | Assert the real audit query hash and citation identities after an authenticated Smart Q&A request. | DONE |

### 4. Systematic Expansion

- **Similar issues**: Every assistant surface using `BusinessSemanticContextService` shared the same pollution risk, so the fix is at that boundary rather than in one caller.
- **Design improvement**: Permission, applicability, Schema, Skill, tracking, and structured context remain separate typed inputs for candidate constraints and downstream execution; they are not relevance text.
- **Process improvement**: Retrieval regressions must validate both the exact query/hash and resulting citation identities. A UI count such as `已使用知识库（5）` is insufficient because five relevant hits and five polluted hits have the same count.

### 5. Knowledge Capture

- [x] Updated `.trellis/spec/backend/knowledge-base-rag.md` with the executable primary-intent-only contract.
- [x] Updated the current dashboard integration document; archived historical decisions remain unchanged.
- [x] Added service-boundary and real audit verification evidence to this task.
