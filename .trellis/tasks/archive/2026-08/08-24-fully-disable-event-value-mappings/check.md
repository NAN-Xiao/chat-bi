# Quality Check

## Root Cause

- `project_tracking_config_for_ai_context()` removed event mappings and defaults but retained each tracking field's `value_mappings`.
- AI schema comments and Tracking Prompt rendering read those mappings directly; field ranking also considered the serialized mapping text.
- `load_tracking_structured_records()` read the raw management DTO and projected tracking events into `BusinessSemanticContext.structured_context`, bypassing the existing AI-safe boundary.

## Implementation

- The shared AI-safe projection now clears `value_mappings` on copied tracking fields without mutating stored or API-visible configuration.
- Tracking field matching, Prompt rendering, and AI schema comment rendering no longer read `value_mappings`.
- The structured tracking adapter now consumes the same AI-safe projection, produces no tracking event records, and retains JSON field structure with empty mappings.
- Management field-list responses, event catalog behavior, configuration persistence, and Excel import/export remain unchanged.
- `.trellis/spec/backend/project-runtime.md` now documents Prompt, schema, field-ranking, and structured-context closure as one executable contract.

## Verification

- Final combined regression: `372 passed` across shared semantic context, SQL Engine, Smart Q&A, analysis assistant, AI dashboard, tracking Prompt/schema, structured context, field-list management, event catalog, configuration save, and Excel import/export tests.
- Management-focused regression: `77 passed`.
- Initial red tests reproduced Prompt and schema leakage plus the structured event bypass before implementation.
- Ruff: passed for task-owned files; `F`/`E9` checks passed for the legacy datasource module.
- Python compilation: passed.
- `git diff --check`: passed.

## Environment Baselines

- Mypy cannot start in the shared backend virtual environment because `0aca9ce3d91742c5b361__mypyc` is missing; no type-check result is claimed.
- The full legacy `tests/test_custom_prompt_agent_permissions.py` run has 12 unrelated SQLite fixture failures because `semantic_object_reference` is absent. The task-owned test in that file passes independently, and the failing tests stop before the changed assertion path.
- No live backend stack was restarted from this worktree, so runtime/server verification is not claimed.
