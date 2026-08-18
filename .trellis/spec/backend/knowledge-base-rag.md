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

## Scenario: Published Knowledge Retrieval Eligibility And Restoration

### 1. Scope / Trigger
- Applies to V2 publication, vector retrieval candidate selection, management UI, archive, inspection, and restoration.

### 2. Signatures
- `GET /knowledge-base/list?archived=false|true&visibility_scope=...&tenant_id=...`
- `POST /knowledge-base/{id}/restore`
- `KnowledgeRetrievalService._load_candidate_metadata(...)`
- V2 does not expose `PUT /knowledge-base/{id}/active`; knowledge-level retrieval eligibility is not user-configurable.

### 3. Contracts
- A knowledge base is lifecycle-eligible for retrieval only when `KnowledgeBase.current_version_id == KnowledgeBaseVersion.id`, that version has `status=PUBLISHED`, and `KnowledgeBase.archived=false`.
- `knowledge_base.active` remains a legacy storage field until a separate schema cleanup, but V2 retrieval and management UI must not read it as an eligibility switch. Successful publication and restoration set it to `true` only to keep retained data coherent; archive sets it to `false`.
- Existing workspace override, tenant/datasource/object permissions, visibility, applicability, schema epoch, index readiness, and embedding checks remain additional mandatory filters. Publication never bypasses them.
- A new draft does not replace the current published version until publication succeeds. The prior current published version remains retrievable while a draft or publishing job exists.
- Management lists default to `archived=false`; archive views must request `archived=true` and retain normal workspace and permission filters.
- Archived records, version history, and retained source files remain readable, but lifecycle mutations are rejected until restoration.
- Restore selects the newest `ARCHIVED` version with a non-null `publish_time`; a discarded unpublished draft must never become the restored current version. It changes that version to `PUBLISHED`, restores the current pointer, clears draft/publishing pointers, sets `archived=false`, and immediately restores lifecycle retrieval eligibility.

### 4. Validation & Error Matrix
- No current version, current version not `PUBLISHED`, or `archived=true` -> exclude from retrieval candidates.
- `active=false` with a current `PUBLISHED` version and `archived=false` -> do not exclude on the legacy field; continue evaluating all other eligibility filters.
- Archived lifecycle mutation before restore -> `409 KNOWLEDGE_ARCHIVED_READ_ONLY`.
- Restore without an archived published version -> `409 KNOWLEDGE_RESTORE_VERSION_NOT_FOUND`.
- Cross-workspace or unauthorized access -> existing permission-boundary 403/404 response.
- Call to removed V2 active route -> no matching V2 operation; clients must use publish/archive/restore lifecycle operations.

### 5. Good/Base/Bad Cases
- Good: restore chooses the newest previously published version and it becomes retrievable immediately when all permission, applicability, and index checks pass.
- Base: a knowledge base with a current published version and a newer draft continues serving only the current published version.
- Bad: filter candidates with `KnowledgeBase.active.is_(True)`, expose an independent management switch, or retrieve an unpublished/archived version.

### 6. Tests Required
- Retrieval query tests assert the published status, current-version pointer, and non-archived predicates are present while `knowledge_base.active` is absent.
- Publication tests start with `active=false` and assert successful finalization synchronizes it to `true` without using it as the retrieval authority.
- State-machine tests cover automatic retrieval restoration, discarded archived drafts, idempotent restore, and missing published history.
- API and frontend contract tests assert the V2 active route, API client method, list column, and editor switch are absent.
- Browser checks cover current and archived views at desktop and mobile widths and verify no horizontal overflow after removing the column.

### 7. Wrong vs Correct
#### Wrong
```python
query.where(
    KnowledgeBaseVersion.status == "PUBLISHED",
    KnowledgeBase.active.is_(True),
)
```

#### Correct
```python
query.where(
    KnowledgeBaseVersion.status == "PUBLISHED",
    KnowledgeBase.current_version_id == KnowledgeBaseVersion.id,
    KnowledgeBase.archived.is_(False),
)
```

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

## Scenario: Strict Markdown Knowledge Uploads

### 1. Scope / Trigger
- Applies to legacy knowledge uploads, V2 create-flow uploads, row uploads, and draft source replacement.

### 2. Signatures
- Create request: `POST /api/v1/knowledge-base/create` accepts name, description, visibility scope, and optional tenant context; `knowledge_type` is forbidden.
- V2 replacement: `POST /api/v1/knowledge-base/{id}/draft/file` accepts `version_id`, `revision`, and one `.md` or `.markdown` file.
- Server-owned parser version: `markdown-v1`, persisted to `knowledge_base_version.parser_version` after a successful V2 source replacement.

### 3. Contracts
- Public management APIs expose one ordinary-document model; `DOCUMENT` remains only as the fixed database and version-payload marker.
- Uploaded source files must use `.md` or `.markdown` and strict UTF-8 (BOM allowed). They are pure Markdown and must not require or generate `template_type`, `template_version`, or other platform metadata.
- The document starts with a non-empty H1, contains at least one non-empty H2 and meaningful body text, and has no unclosed fenced code block.
- Headings inside fenced code never satisfy the H2 contract or create document blocks. A fence closes only with the same marker character and at least the opening marker length, so a `~~~` example inside a backtick fence cannot alter section parsing.
- Parser identity is server-owned. The client and Markdown content cannot select or override it; successful V2 replacement carries `markdown-v1` through `SourceFileRef.parser_version` into the version row.
- Validation errors return a message beginning with `格式错误`; V2 uses error code `KNOWLEDGE_MARKDOWN_FORMAT_INVALID`.
- Validation and parsing complete before draft CAS. Failure preserves the current payload, source reference, block structure, and revision and removes only the request's staged file.
- Legacy replacement commits the new database reference before checking and deleting an unreferenced old source. If commit fails, delete the newly uploaded file and retain the old source.

### 4. Validation & Error Matrix

| Input | Required behavior |
| --- | --- |
| `.docx`, `.xlsx`, or another extension | `422`; message starts with `格式错误`; no draft mutation |
| Invalid UTF-8 | `422`; message starts with `格式错误` and identifies UTF-8 |
| Missing H1, H2, meaningful body, or closing fence | Reject before draft CAS |
| Valid pure Markdown with UTF-8 or UTF-8 BOM | Replace document blocks, persist `markdown-v1`, then advance revision |

### 5. Good/Base/Bad Cases
- Good: a downloaded content template or independently authored pure Markdown document is uploaded, converted to ordinary document blocks, and tagged with the server parser version.
- Base: UTF-8 BOM and CRLF line endings are normalized and accepted under the same structure contract.
- Bad: a client bypasses frontend validation with an Office file or incomplete Markdown; the backend rejects it without changing payload, revision, or source reference.

### 6. Tests Required
- Backend and frontend contract tests cover pure Markdown, UTF-8 BOM, invalid UTF-8, missing headings/body, and unclosed fences.
- Mixed-marker fence tests cover validation, section splitting, and document-block conversion so front/back behavior cannot drift.
- V2 upload tests assert the server parser version reaches `SourceFileRef` and is persisted to `knowledge_base_version.parser_version`.
- Upload regressions assert invalid input cannot reach draft save, cannot change revision or source state, and leaves no staged file.
- UI source-upload tests cover create, row, and editor replacement entrances and assert no Word/Excel claim remains in any locale.

### 7. Wrong vs Correct

#### Wrong
```python
metadata, markdown = parse_front_matter(uploaded_bytes)
if metadata["template_type"] != "knowledge_document":
    raise ValueError("wrong template")
save_draft(parser_version=str(metadata["template_version"]))
```

#### Correct
```python
parsed = parse_knowledge_markdown_bytes(uploaded_bytes)
payload = payload.model_copy(update={"blocks": document_blocks_from_markdown(parsed.markdown)})
source_file = SourceFileRef(file_id=file_id, parser_version=parsed.parser_version)
save_draft(payload=payload, source_file=source_file)
```
