# Quality Check

## Findings Fixed

- `backend/apps/knowledge_base/publisher.py` still used a literal fallback batch
  size of `32` when an injected embedding model did not expose `config`. The
  fallback now uses the shared `settings.EMBEDDING_BATCH_SIZE` contract.
- `backend/tests/test_knowledge_base_publisher.py` now covers the missing-model-
  config path and verifies that 23 chunks are sent as `10, 10, 3` without
  changing output cardinality.
- `.trellis/spec/backend/project-runtime.md` now records the shared API/Worker
  batch-size contract, deployment propagation, ordering requirement, and the
  prohibition on model-name branches or silent batch-size retries.

## Verification

- Targeted Ruff: pass for the changed backend files and tests.
- Targeted embedding and knowledge publication regression tests: 40 passed.
- Python compile check: pass for the affected source and test files.
- `git diff --check`: pass.
- Full backend Ruff: blocked by 1,346 pre-existing findings outside this change.
- Full/targeted strict mypy: blocked by the repository's existing type baseline
  (2,365 errors across imported modules); the checked changes introduced no
  new type suppression or unsafe cast.
- Remote `.193` runtime and publication verification: passed.

## Remote `.193` Verification

- Existing image `shuzhi:88-f4c1312b` and its SHA were recorded before the change.
- Backed up `/home/chat-bi/chat-bi.runtime.env` and `/home/chat-bi/install.conf`
  with timestamp `20260817161130`, then set the runtime and deployment values to
  `EMBEDDING_BATCH_SIZE=10` and `SHUZHI_EMBEDDING_BATCH_SIZE=10`.
- Recreated `chat-bi-api-8000`, `chat-bi-api-8002`, `chat-bi-worker-1`, and
  `chat-bi-worker-2` with the existing image, mounts, ports, and `default` queue.
  Both API containers became healthy; all four containers exposed the same
  database, Redis, queue, model, and batch-size settings.
- A real `text-embedding-v4` request for 23 inputs returned 23 vectors with
  dimension 1024 and observed `batch_size=10`.
- Revalidated and published knowledge base `事件参数对照_通用` (`knowledge_base_id=26`,
  `version_id=32`, revision 3) through the registered lifecycle and task queue.
  Job `36` reached `SUCCEEDED`; the version is `PUBLISHED`, index status is
  `READY`, and `current_version_id=32`.
- The application logs contained zero new `batch size is invalid` entries. An
  initial manual retry job (`35`) was rejected as `TASK_HANDLER_NOT_REGISTERED`
  because its isolated diagnostic process had not imported the task registry;
  this was not a production container failure and was followed by the successful
  registered retry above.

## Full Backend Baseline

- Running the full backend suite from the correct worktree loaded 1560 passing,
  37 failing, and 8 skipped tests. The failures are concentrated in unrelated
  date-filter, tenant-binding, and existing knowledge-route fixtures; the
  embedding/publisher-related collection passed. Full Ruff and strict mypy remain
  blocked by the repository baseline (1346 and 2365 existing findings).
