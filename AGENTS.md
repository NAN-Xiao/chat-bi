# Agent Instructions

Scope: entire repository.

## Local Dev Runbook

- For local Windows development, treat the stack as three separate local services:
  `frontend` Vite on `0.0.0.0:5173`, backend API on `0.0.0.0:8000`, and MCP server on `0.0.0.0:8001`.
- Before retrying random ports or passwords, use the known-good local app database settings from the repo root `.env`:
  `POSTGRES_SERVER=127.0.0.1`, `POSTGRES_PORT=15432`, `POSTGRES_DB=zhishu_bi`, `POSTGRES_USER=root`, `POSTGRES_PASSWORD=Password123@pg`.
- Do not confuse the local app system database with the SLG BI demo datasources:
  the 星通智数 system database is PostgreSQL `zhishu_bi` on `127.0.0.1:15432` with user `root` / password `Password123@pg`;
  the seeded BI demo datasources are PostgreSQL on `127.0.0.1:5432` with user `postgres` / password `111111`,
  where datasource `SLG BI Mock` points to database `slg_bi_mock` and datasource `SLG BI Mock 2 - Season War` points to `slg_bi_mock_2`.
- For this workspace's current default online LLM, use:
  `base_url=https://aikey.elex-tech.com/v1`, `api_key=apg_c2a9f12cb04b6db44c905952402619ba39a4eb446185653c`, `default_model=qwen3.5-plus`.
  The same OpenAI-compatible endpoint also provides the remote embedding model `text-embedding-v4`.
  If Smart Q&A fails immediately before SQL generation, verify the `ai_model` default row in the app database first instead of retrying random domains, ports, or passwords.
- If you need to inspect datasource definitions in the 星通智数 system database, query `core_datasource` in `zhishu_bi` on port `15432`.
- Local startup logs to check first:
  `.codex-runtime/backend-8000.current.err.log`, `.codex-runtime/backend-8001.current.err.log`, `.codex-runtime/frontend-5173.current.out.log`,
  plus application logs under `logs/` and `backend/logs/`.
- For local backend startup on this machine, set these environment overrides before running `uvicorn` so paths and ports match the workspace:
  `POSTGRES_SERVER=127.0.0.1`, `POSTGRES_PORT=15432`, `POSTGRES_DB=zhishu_bi`, `POSTGRES_USER=root`, `POSTGRES_PASSWORD=Password123@pg`,
  `FRONTEND_HOST=http://localhost:5173`, `BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`,
  `BASE_DIR=D:/work/AI/SQLBot/.codex-runtime/zhishu`, `UPLOAD_DIR=D:/work/AI/SQLBot/.codex-runtime/file`,
  `MCP_IMAGE_PATH=D:/work/AI/SQLBot/.codex-runtime/images`, `EXCEL_PATH=D:/work/AI/SQLBot/.codex-runtime/excel`.
- MCP tools are disabled by default in this workspace. Set `MCP_ENABLED=false` for local backend/MCP startup unless you are explicitly testing MCP access controls.
- In this local workspace, embedding uses the remote OpenAI-compatible `text-embedding-v4` model from the repo root `.env`; do not set `EMBEDDING_ENABLED=false` or `TABLE_EMBEDDING_ENABLED=false` unless you are intentionally disabling semantic retrieval.
- Known-good local startup commands on Windows PowerShell are:
  backend API:
  ``$env:POSTGRES_SERVER='127.0.0.1'; $env:POSTGRES_PORT='15432'; $env:POSTGRES_DB='zhishu_bi'; $env:POSTGRES_USER='root'; $env:POSTGRES_PASSWORD='Password123@pg'; $env:FRONTEND_HOST='http://localhost:5173'; $env:BACKEND_CORS_ORIGINS='http://localhost:5173,http://127.0.0.1:5173'; $env:BASE_DIR='D:/work/AI/SQLBot/.codex-runtime/zhishu'; $env:UPLOAD_DIR='D:/work/AI/SQLBot/.codex-runtime/file'; $env:MCP_IMAGE_PATH='D:/work/AI/SQLBot/.codex-runtime/images'; $env:EXCEL_PATH='D:/work/AI/SQLBot/.codex-runtime/excel'; $env:MCP_ENABLED='false'; Start-Process -FilePath 'D:\work\AI\SQLBot\backend\.venv\Scripts\python.exe' -WorkingDirectory 'D:\work\AI\SQLBot\backend' -ArgumentList '-m','uvicorn','main:app','--host','0.0.0.0','--port','8000' -RedirectStandardOutput 'D:\work\AI\SQLBot\.codex-runtime\backend-8000.current.out.log' -RedirectStandardError 'D:\work\AI\SQLBot\.codex-runtime\backend-8000.current.err.log' -WindowStyle Hidden``
  MCP:
  ``$env:POSTGRES_SERVER='127.0.0.1'; $env:POSTGRES_PORT='15432'; $env:POSTGRES_DB='zhishu_bi'; $env:POSTGRES_USER='root'; $env:POSTGRES_PASSWORD='Password123@pg'; $env:FRONTEND_HOST='http://localhost:5173'; $env:BACKEND_CORS_ORIGINS='http://localhost:5173,http://127.0.0.1:5173'; $env:BASE_DIR='D:/work/AI/SQLBot/.codex-runtime/zhishu'; $env:UPLOAD_DIR='D:/work/AI/SQLBot/.codex-runtime/file'; $env:MCP_IMAGE_PATH='D:/work/AI/SQLBot/.codex-runtime/images'; $env:EXCEL_PATH='D:/work/AI/SQLBot/.codex-runtime/excel'; $env:MCP_ENABLED='false'; Start-Process -FilePath 'D:\work\AI\SQLBot\backend\.venv\Scripts\python.exe' -WorkingDirectory 'D:\work\AI\SQLBot\backend' -ArgumentList '-m','uvicorn','main:mcp_app','--host','0.0.0.0','--port','8001' -RedirectStandardOutput 'D:\work\AI\SQLBot\.codex-runtime\backend-8001.current.out.log' -RedirectStandardError 'D:\work\AI\SQLBot\.codex-runtime\backend-8001.current.err.log' -WindowStyle Hidden``
  frontend:
  ``Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -WorkingDirectory 'D:\work\AI\SQLBot\frontend' -ArgumentList '/c','npm run dev' -RedirectStandardOutput 'D:\work\AI\SQLBot\.codex-runtime\frontend-5173.current.out.log' -RedirectStandardError 'D:\work\AI\SQLBot\.codex-runtime\frontend-5173.current.err.log' -WindowStyle Hidden``
- Known-good health checks after startup:
  `http://127.0.0.1:5173/` should return `200`,
  `http://127.0.0.1:8000/api/v1/system/getLoginMethod` may return `401` but proves backend is up,
  and `0.0.0.0:8000`, `0.0.0.0:8001`, `0.0.0.0:5173` should all be listening for LAN testing.
- Current deployment direction: keep local development simple and single-replica by default, but keep production deployment multi-replica capable through configuration. Local backend replicas can be started with `tools/backend-local.ps1`; default `-BackendPorts 8000` is development mode, while `-BackendPorts 8000,8002,8003 -CacheType redis` is the local production-like mode. Local Nginx can be run with `tools/nginx-local.ps1`, defaulting to port `8080`.
- For backend multi-replica mode, use Redis-backed cache/state. Do not rely on process-local memory cache for shared auth, assistant, datasource, lock, rate-limit, or task state. Start replicas sequentially or run database migrations once before starting all replicas; avoid concurrent Alembic migrations from multiple backend processes.
- Object storage is intentionally deferred for now. Local single-machine replicas may share `.codex-runtime/file`, `.codex-runtime/excel`, and `.codex-runtime/images`; before multi-machine production, these paths must move to shared storage or object storage.
- Docker is not a current requirement for this Windows development workspace. Prefer native PowerShell scripts plus local PostgreSQL, Redis, and optional Nginx zip runtime until Docker/WSL is deliberately revisited.
- Task queue first version is Redis-backed. Use `tools/worker-local.ps1` for local workers. Only enqueue registered task handlers; do not expose arbitrary task execution to normal users. Keep sensitive credentials out of task payloads.
- Use `tools/stack-local.ps1` for one-command local orchestration. Default local development stays single-backend on `8000`; pass multiple `-BackendPorts` only for pressure tests or production-like simulation.
- Use `tools/postgres-backup-local.ps1` for local PostgreSQL backups/restores before risky schema or data changes. Backups go under `.codex-runtime/pg-backups` and must not be committed.

## SLG BI Mock Data Constraints

- When creating or changing the SLG BI mock database, keep the dataset at tracking/event detail level.
- Do not create persisted aggregate KPI tables such as `agg_*`, `*_kpis`, `daily_kpis`, or similar metric summary tables unless the user explicitly asks for an analysis layer.
- Do not create daily/player snapshot tables derived from events, such as `fact_daily_player_snapshot`, unless the user explicitly asks for snapshots.
- Do not create analysis views as part of the mock tracking dataset unless the user explicitly asks for reusable views.
- Metrics such as DAU, retention, ARPU, ARPPU, payer rate, and LTV must be computed from detail tables at query time or in an external BI layer.
- `fact_*` tables must represent event-level or domain-detail records traceable to a player, session, and event time.
- `dim_*` tables may describe players, servers, products, alliances, and event dictionaries.

## Product Direction: General BI Platform

- Treat this repository as a production-oriented, general-purpose BI / ChatBI platform, not as an SLG-only or game-only application.
- SLG data, terminology, SQL examples, prompts, and test questions are demo/domain fixtures only. They must not become assumptions in core backend logic, frontend logic, global prompts, permission logic, routing, chart logic, or datasource selection.
- Core product behavior must be domain-agnostic and datasource-agnostic. It should work for finance, ecommerce, operations, SaaS, manufacturing, games, and other analytical domains through configuration and metadata.
- Do not hardcode business table names, field names, datasource IDs, metric formulas, channel names, product names, event names, server names, date windows, or domain-specific thresholds in shared application code.
- Do not special-case SLG, game, payment, retention, LTV, DAU, or similar concepts in shared code unless the implementation is a generic capability that applies to arbitrary configured metrics.
- Assistant surfaces such as Smart Q&A, analysis assistant, embedded assistant, and document-oriented assistant must share the same datasource access, permission, semantic-layer, and metadata configuration services. They may differ in answer style or task framing, but not through duplicated hardcoded datasource rules.
- Datasource access and the currently selected datasource context take precedence over user wording, test questions, semantic examples, and assistant-specific prompts. If a user mentions a datasource that is not selected or not authorized in the current context, the assistant must not generate SQL against it or use its schema/semantic examples; it should explain the permission/context mismatch and ask the user to switch or request access.
- If domain-specific behavior is needed for a demo or customer scenario, keep it in configuration, seed scripts, documentation, test fixtures, or datasource-scoped semantic records. Do not wire it into the platform runtime path.
- Production logic should be driven by system configuration, datasource metadata, user/workspace permissions, semantic-layer records, and selected assistant settings. Prefer extending those configuration mechanisms before adding code branches.

## Temporarily Hidden Smart Q&A Actions

- Smart Q&A chart-answer actions for data analysis and data prediction are intentionally hidden, not deleted.
- The current switch is `showChartAnalysisPredictActions = false` in `frontend/src/views/chat/index.vue`.
- Keep `clickAnalysis(...)`, `clickPredict(...)`, `AnalysisAnswer.vue`, `PredictAnswer.vue`, `analysis_record_id`, `predict_record_id`, and related APIs/data compatibility unless the user explicitly asks to permanently remove the capability.
- Product direction: Smart Q&A should focus on asking data questions and generating charts; deeper analysis and prediction should be handled by the analysis assistant.
- See `docs/smart_qa_hidden_analysis_predict_actions.md` for the detailed memo and restore steps.

## Semantic Layer First

- For business data issues involving metric definitions, analysis口径, SQL generation, chart field selection, datasource selection, or result interpretation, prefer solving them through the semantic layer: terminology, data-training SQL examples, datasource/table/field metadata, recommended questions, custom prompts, assistant configuration, and permission configuration.
- Avoid hardcoding business口径 in global prompts, agent prompts, frontend logic, backend logic, or mock data generation when terminology, SQL examples, metadata, or other system configuration can express the rule clearly.
- Use code changes for generic platform behavior only, such as SQL safety, permission handling, datasource discovery, semantic retrieval, chart rendering correctness, null handling, mature-window handling, or reusable validation that is not tied to one business metric or domain.
- Semantic-layer seed scripts must be idempotent and datasource-scoped. They should associate records with the intended `oid` and datasource IDs instead of relying on global hidden assumptions.
- Datasource-scoped terminology, SQL examples, recommended questions, and test questions must not leak into other datasources. When a semantic record is specific to one datasource, store and retrieve it only under that datasource's allowed context.
- When adding or correcting business口径 for the SLG BI mock project, update `tools/seed_slg_bi_training.py` and rerun it so every assistant surface that uses the same datasource can share the same terminology and SQL examples.
