# Agent Instructions

Scope: entire repository.

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

## Semantic Layer First

- For business data issues involving metric definitions, analysis口径, SQL generation, chart field selection, datasource selection, or result interpretation, prefer solving them through the semantic layer: terminology, data-training SQL examples, datasource/table/field metadata, recommended questions, custom prompts, assistant configuration, and permission configuration.
- Avoid hardcoding business口径 in global prompts, agent prompts, frontend logic, backend logic, or mock data generation when terminology, SQL examples, metadata, or other system configuration can express the rule clearly.
- Use code changes for generic platform behavior only, such as SQL safety, permission handling, datasource discovery, semantic retrieval, chart rendering correctness, null handling, mature-window handling, or reusable validation that is not tied to one business metric or domain.
- Semantic-layer seed scripts must be idempotent and datasource-scoped. They should associate records with the intended `oid` and datasource IDs instead of relying on global hidden assumptions.
- Datasource-scoped terminology, SQL examples, recommended questions, and test questions must not leak into other datasources. When a semantic record is specific to one datasource, store and retrieve it only under that datasource's allowed context.
- When adding or correcting business口径 for the SLG BI mock project, update `tools/seed_slg_bi_training.py` and rerun it so every assistant surface that uses the same datasource can share the same terminology and SQL examples.
