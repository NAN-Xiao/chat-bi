# 完善知识库归档查看与恢复

## Goal

Complete the knowledge-base archive lifecycle so administrators can find,
inspect, and restore previously published knowledge bases without making a
restored item immediately available to retrieval.

## Requirements

- Add an explicit current/archived list filter to the V2 knowledge management
  page and API.
- Archived knowledge bases remain readable, including their version history
  and source-file downloads when present.
- Archived knowledge bases are read-only until restored.
- Authorized managers can restore an archived knowledge base.
- Restore the most recent previously published version as the current version.
- A restored knowledge base must remain inactive and must not participate in
  retrieval until explicitly enabled by a later management action.
- Authorized managers can explicitly enable or disable a current published
  knowledge base; archived knowledge cannot be enabled directly.
- Keep unpublished knowledge deletion behavior unchanged; only published
  archived records appear in the archive list.
- Preserve workspace and platform permission boundaries.

## Acceptance Criteria

- [ ] The list defaults to current knowledge and excludes archived records.
- [ ] Selecting archived knowledge displays only archived records for the
      selected scope/workspace and keyword.
- [ ] An archived row opens a read-only drawer with retained version history.
- [ ] An authorized manager can restore an archived row from the list or
      detail drawer.
- [ ] Restore re-establishes the latest published version pointer and version
      status while leaving `active=false` and `archived=false`.
- [ ] Restored knowledge remains excluded from retrieval while inactive.
- [ ] A manager can explicitly enable the restored current knowledge, after
      which its active published version is eligible for retrieval again.
- [ ] Backend lifecycle/list tests and frontend contract/layout tests cover the
      new behavior; frontend build passes.

## Notes

- No database migration is required; the existing record and version fields
  contain enough lifecycle information.
- This task must preserve unrelated in-progress source-upload edits in the
  shared frontend component.
