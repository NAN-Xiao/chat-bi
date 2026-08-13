# Implementation Plan

1. Add repository and lifecycle-service restore behavior with state-machine
   tests for successful, inactive restore and invalid archived history.
2. Extend management list filtering and add the restore API with permission
   and response tests.
3. Extend the frontend API types and management panel with archived filtering,
   read-only detail behavior, restore actions, and explicit activation control.
4. Add focused frontend source-contract assertions and run backend tests,
   frontend build, runtime API checks, and browser verification.
5. Record verification results and review whether the lifecycle contract needs
   a stable spec update.

## Implementation Log

- Added tenant-scoped archived list filtering and `POST /knowledge-base/{id}/restore`.
- Added repository/lifecycle restoration of the latest archived version with a
  non-null publish time; restoration clears draft/publishing pointers and keeps
  the record inactive.
- Kept archived detail, version history, and source downloads readable while
  blocking lifecycle mutations until restoration.
- Added the current/archived management filter, read-only archived drawer, and
  manager restore actions without removing the concurrent source-upload work.
- Added an explicit manager activation switch for current published knowledge;
  restored knowledge stays inactive until this switch is confirmed.
- Recorded the durable archive lifecycle contract in the backend knowledge-base
  spec.
