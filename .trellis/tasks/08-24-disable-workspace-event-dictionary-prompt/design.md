# Technical Design

## Boundary

The change applies at the shared AI-context assembly boundary. Event dictionary management and persistence remain unchanged.

## Current Data Flow

1. `find_tracking_prompt_context()` loads `TenantTrackingConfigDTO` and builds `<Workspace-Tracking-Rules>`.
2. AI surfaces place that text into their SQL/answer prompts.
3. `_dictionary_schema_from_workspace()` separately projects matching event properties into `m-schema`.
4. Smart Q&A post-processing also parses the generated tracking text for event fields and configured event names.

## Target Data Flow

1. Shared tracking context continues to expose only non-event workspace metadata: table/field descriptions, generic field roles, SQL constraints, and workspace notes.
2. Event names, mappings, groups, event-specific defaults, and event properties are not serialized into AI prompt text or summaries.
3. Workspace dictionary schema assembly does not call or append request event schema projection.
4. No alternative physical-table event discovery is introduced. Any internal post-check that depended on prompt-serialized event data must become inactive when the event channel is absent rather than probing a replacement source.

## Compatibility

- No database migration or API contract change.
- Event catalog, configuration editor, import/export, and permission behavior remain available.
- AI responses may still mention an event when it comes from the user request, Data Skills, knowledge context, or ordinary table/field metadata.

## Verification Strategy

- Update prompt-context tests to assert event sections are absent while non-event sections remain.
- Update schema assembly tests to assert event projections are not called or appended.
- Add a Smart Q&A regression proving channel removal does not fall back to physical event probing.
- Run existing event catalog and Excel tests to protect management behavior.

## Rollback

Revert the shared context and schema assembly changes. No persisted data requires restoration.
