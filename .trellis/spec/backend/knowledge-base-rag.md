# Knowledge Base RAG Contracts

## Scenario: Published Version References and Chunk Retrieval

### 1. Scope / Trigger
- Applies to version publication, semantic object resolution, RAG retrieval, report interpretation, and analysis assistant flows.

### 2. Signatures
- `resolve_references_for_context(...)` accepts projected references or persisted reference rows.
- `KnowledgeRetrievalService._load_reference_resolution(...)` resolves a chunk reference directly, then falls back to its matching version reference.
- `knowledge_base_migrate.py status|verify --compatible-builds-confirmed` reports cutover readiness without changing state.

### 3. Contracts
- Publication retains both version-level and chunk-level references; applicability checks both levels.
- A chunk reference without its own resolution inherits the resolution matching `version_id + declared_key + source_kind`.
- Retrieval still enforces workspace, datasource, visibility, schema epoch, and allowed object keys after inheritance.
- Retrieval audit snapshots contain `knowledge_base_id`, `version_id`, `chunk_id`, `score`, and `visibility_scope`.
- Assistant surfaces use `report_interpretation` or `analysis_assistant`; user-visible failures remain safe Chinese messages.

### 4. Validation & Error Matrix
- Workspace or datasource mismatch -> filter the candidate; never fall back across scopes.
- No chunk or matching version resolution -> reject the reference and persist applicability state.
- `storage_probe_ready=false` or pending legacy backfill -> `verify` reports not ready and exits with code 2.
- Concurrent publication of one knowledge base -> return HTTP 409 with a Chinese message.

### 5. Good/Base/Bad Cases
- Good: only the version resolution exists; an authorized chunk inherits it and can be retrieved.
- Base: chunk and version resolutions both exist; validate with the chunk resolution.
- Bad: only an unauthorized workspace resolution exists; return no hit and retain the audit warning.

### 6. Tests Required
- Unit tests cover persisted-reference conversion, version-resolution inheritance, and permission filtering.
- Real calls prove non-empty audit snapshots for `report_interpretation` and `analysis_assistant`.
- Page checks assert `scrollWidth <= clientWidth + 2` at supported desktop viewports.
- Cutover checks preserve raw `status` and `verify` output.

### 7. Wrong vs Correct
#### Wrong
Read only chunk-level resolution and reject a chunk immediately when that row does not exist, producing zero retrieval hits after a valid publication.

#### Correct
Inherit the matching version-level resolution when the chunk row is absent, then continue enforcing workspace, datasource, schema, and object permissions.

### Common Mistake: Deduplicating Persisted Resolution Rows

- `declared_key + source_kind` is a logical projection key, not a database row identity.
- A published version can have one version-level reference and multiple chunk-level references with the same key; every reference needs its own `semantic_object_resolution` row.
- Persist the resolved result to all matching reference IDs, while evaluating the resolver once per logical key to avoid redundant catalog queries.
- Regression coverage must assert that duplicate version/chunk references all receive the same canonical key.

### Common Mistake: Sorting Citation Dictionaries Directly

- A retrieval can legitimately return multiple citations from one published version. Python dictionaries are not orderable, so `sorted(dict_generator)` raises `TypeError` as soon as more than one citation is present.
- Build the redacted citation identity snapshot first, then sort with an explicit tuple key such as `knowledge_base_id + version_id + chunk_id` before hashing.
- The version hash must be stable when citation order changes, and the regression test must contain at least two citations so a single-hit test cannot hide the failure.

### Common Mistake: Re-truncating Retrieved Knowledge After Retrieval

- `KNOWLEDGE_RETRIEVAL_MAX_CONTEXT_CHARS` must bound the final serialized `<retrieved-knowledge>` context, including wrapper tags and separators.
- If the first eligible chunk is too long, truncate the citation content in the retrieval snapshot itself before building `KnowledgeRetrievalResult`; do not truncate only a temporary counter string and then serialize the original body.
- Assistant surfaces must pass the bounded `knowledge_context` through unchanged. Re-truncating it in a Prompt builder can break XML tags and make the Prompt body disagree with citations and the knowledge version snapshot.
- Context snapshots must hash Data Skill content from the dedicated Skill field, not from a flattened semantic string that also contains tracking, structured, or retrieved knowledge.

## Scenario: SaaS Knowledge Management Workspace Boundary

### 1. Scope / Trigger
- Applies when the SaaS knowledge-management UI or API reads or writes platform-public knowledge and workspace knowledge from one management surface.

### 2. Signatures
- `GET /api/v1/knowledge-base/list?visibility_scope=PLATFORM_PUBLIC|ADMIN_PUBLIC&tenant_id=<workspace-id>`
- `POST /api/v1/knowledge-base/create` JSON may include `tenant_id` for `ADMIN_PUBLIC`.
- `POST /api/v1/knowledge-base/save` form data may include `tenant_id` for new `ADMIN_PUBLIC` records.
- Detail, draft, validation, publication, rollback, download, and archive routes resolve the persisted record and retain its tenant boundary.

### 3. Contracts
- `PLATFORM_PUBLIC` always maps to `DEFAULT_TENANT_ID`; callers must omit `tenant_id`.
- A global platform admin may pass an active, non-default workspace `tenant_id` and manage that workspace's knowledge.
- A workspace owner/admin may read platform knowledge, manage only the authenticated current workspace, and cannot select another workspace.
- A workspace member may read platform and current-workspace knowledge but cannot create, edit, publish, roll back, or archive.
- The backend filters by the authorized `tenant_id`; the frontend must not fetch all workspace records and hide unauthorized rows locally.

### 4. Validation & Error Matrix
- Platform scope with `tenant_id` -> HTTP 400.
- Global platform admin requests workspace scope without `tenant_id` -> HTTP 400 and require an explicit workspace selection.
- Workspace scope with missing/deactivated/default-platform tenant -> HTTP 404.
- Non-platform user requests another workspace `tenant_id` -> HTTP 403.
- Missing current workspace for a workspace-scoped request -> existing explicit tenant-context error.
- Write operation without `can_manage` permission -> HTTP 403; never substitute platform-admin or similarly named workspace context.

### 5. Good/Base/Bad Cases
- Good: platform admin selects workspace A; list/create operations carry A's `tenant_id`, while later lifecycle operations use the persisted record tenant.
- Base: workspace admin uses a disabled workspace selector fixed to the authenticated current workspace and receives editable rows there.
- Bad: a member changes the query string to workspace B; the API returns 403 instead of an empty list or cross-tenant data.

### 6. Tests Required
- Permission tests cover platform admin, workspace admin, and member for both platform and workspace scopes.
- API tests assert `tenant_id` filtering, cross-workspace 403, invalid/default workspace 404, and platform-scope-with-tenant 400.
- Frontend contract tests assert both scope options, the fixed non-platform workspace selector, and role-gated create/edit/archive controls.
- Browser tests use real authenticated accounts to verify the three-role matrix and at least two platform-admin workspace selections.

### 7. Wrong vs Correct
#### Wrong
Fetch all workspace knowledge for a platform administrator, filter it in Vue, and reuse the current tenant for create or lifecycle calls.

#### Correct
Send the selected authorized `tenant_id` to the list/create API, enforce it on the backend, and use the persisted knowledge record's tenant for subsequent lifecycle operations.

## Scenario: Multi-Block Knowledge Documents

### 1. Scope / Trigger
- Applies to `DOCUMENT` draft editing, validation, publication, chunk projection, retrieval citations, file replacement, and legacy Markdown reads.

### 2. Signatures
- A document payload stores ordered `blocks[]` plus `structure_revision`; each block stores stable `id`, `title`, `markdown`, `enabled`, and `block_revision`.
- Block content updates compare `block_revision`; add, delete, copy, reorder, and document metadata updates compare `structure_revision`.
- Published chunks may store nullable `source_block_id`; legacy chunks remain valid with `NULL`.

### 3. Contracts
- One management-list row remains one independently versioned document. Blocks share the document's tenant, permission, draft, validation, publication, and rollback boundary.
- Concurrent edits to different blocks may both save. A stale edit to the same block returns HTTP 409 with the server block snapshot and preserves local content in the client.
- A stale structure operation returns HTTP 409 with the latest server payload. Structure persistence must merge server-owned content for existing block IDs so a stale full block array cannot overwrite a concurrent block edit.
- Structure requests must not overwrite document metadata hidden from the block editor. Existing block content and revisions come from the locked server payload, and every newly submitted block starts at server-owned `block_revision=1`.
- Legacy `{markdown: ...}` payloads normalize to one deterministic `正文` block. The stable ID seed uses normalized Markdown so line-ending differences do not change the payload hash.
- New writes persist only `blocks`; do not silently dual-write `markdown`.
- Publication chunks enabled blocks independently and carries `source_block_id` through retrieval citations, preview responses, and semantic context snapshots.
- Successful block and structure writes add a tenant-scoped operation audit in the same database transaction. The audit identifies the document, version number and revision, actor, operation types, and affected stable block IDs without storing block content.

### 4. Validation & Error Matrix
- No blocks -> validation error at `blocks`.
- All blocks disabled -> validation error at `blocks`.
- Empty title -> validation error at `blocks[index].title`.
- Empty enabled body -> validation error at `blocks[index].markdown`.
- Stale block revision -> `KNOWLEDGE_DOCUMENT_BLOCK_CONFLICT` with `details.server_block`.
- Block deleted concurrently -> `KNOWLEDGE_DOCUMENT_BLOCK_DELETED` with latest structure context.
- Stale structure revision -> `KNOWLEDGE_DOCUMENT_STRUCTURE_CONFLICT` with `details.server_payload`.

### 5. Tests Required
- Cover different-block concurrent success, same-block conflict, structure conflict, and deleted-block conflict.
- Cover audit classification for block edits, enable/disable, add/delete, and reorder operations.
- Cover deterministic legacy normalization across line endings.
- Cover chunk `source_block_id` persistence and citation serialization.
- Frontend checks cover add, copy, reorder, enable/disable, delete, conflict comparison, local retry, and desktop/mobile horizontal overflow.
