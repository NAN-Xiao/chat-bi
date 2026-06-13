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
