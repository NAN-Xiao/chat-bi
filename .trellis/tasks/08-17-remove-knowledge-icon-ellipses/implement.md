# Implementation Log

## Changes

- Replaced the two circular Element Plus buttons in `DocumentEditor.vue` with text-style icon buttons.
- Added one shared `block-icon-action` style with a stable 32px square hit area, transparent normal state, no border, and compact hover/focus feedback.
- Added a focused source regression assertion that rejects future `circle` usage for these actions and verifies the borderless button contract.

## Scope Review

- Kept add, delete-confirmation, minimum-block, readonly, tooltip, and accessibility behavior unchanged.
- No backend, API, data model, or global component style changes were needed.
- No reusable project-wide convention was introduced, so `.trellis/spec/` remains unchanged.
