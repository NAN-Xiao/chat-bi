# Design

## API Contract

- Extend `GET /knowledge-base/list` with `archived: bool = false`.
- Add `POST /knowledge-base/{id}/restore` for authorized managers.
- Add `PUT /knowledge-base/{id}/active` with an explicit boolean body for
  authorized managers; archived records and records without a current
  published version cannot be enabled.
- Keep detail and version routes readable for archived records through their
  existing permission checks.

## Lifecycle

Archive already clears all record pointers and changes the published version
to `ARCHIVED`. Restore locks the knowledge record, requires manage permission,
selects the newest archived version with a non-null `publish_time`, changes it
back to `PUBLISHED`, sets it as `current_version_id`, clears other lifecycle
pointers, and updates the record to `archived=false`, `active=false`.

If the record is not archived, restore is idempotent. If no previously
published archived version exists, return an explicit lifecycle conflict.

## Frontend

Add a segmented current/archived filter to the existing management toolbar.
Pass that state to the list API. Archived rows show an archived status and use
`查看` rather than `编辑`; their drawer is read-only even for managers. Expose a
restore command for managers in both row actions and the drawer. Hide creation
and retrieval preview in the archived view where those actions are not
relevant.

The current list shows an explicit enable/disable switch for managers. This is
the required confirmation step after restore and is not inferred from publish
or other lifecycle operations.

## Safety

Retrieval already requires both `archived=false` and `active=true`. Keeping a
restored record inactive prevents accidental re-publication. Workspace and
platform visibility continue through the existing record resolution and
permission services.
