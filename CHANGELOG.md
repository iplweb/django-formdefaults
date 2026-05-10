# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-05-10

### Added

- `FormFieldDefaultValue.is_auto_snapshot: bool` — flag identifying rows
  that came from `Form.initial` automatically and should be kept in sync
  with the code. Cleared on every UI edit (popup or Django admin),
  making the value "sticky".
- `update_form_db_repr` now refreshes value of rows where
  `is_auto_snapshot=True` and value drifted from current
  `form_field.initial`. Sticky rows are never touched.
- Data migration `0007_backfill_is_auto_snapshot` backfills the flag for
  existing rows: True if `value == form_field.initial`, False otherwise.
- `formdefaults._autosnap_backfill.resolve_initial` — helper used by the
  backfill migration; importable from tests.

### Changed

- Popup save (`build_user_defaults_form().save()`) and admin save
  (`FormRepresentationAdmin.save_formset`) both clear
  `is_auto_snapshot` on every write so user/admin overrides become
  sticky immediately.

## [0.2.0] — 2026-05-10

### Added

- `register_form` decorator and `FORMDEFAULTS_FORMS` setting for
  pre-registration of forms; snapshot is taken on `post_migrate`.
- `pre_registered` flag on `FormRepresentation`.
- Per-user popup edit UX:
  - `UserFormDefaultsView` (GET fragment / POST save) and
    `formdefaults.urls`.
  - `{% formdefaults_button %}` template tag.
  - Vanilla-JS modal in `static/formdefaults/modal.js` (no jQuery/HTMX
    dependency).
- `build_user_defaults_form` for programmatic per-user override editing.
- `dedupe_formdefaults` management command for migrating older databases.
- `example_project/` demonstrating all three registration paths.
- Unique constraint on `FormFieldDefaultValue(field, user)` for non-NULL
  users + partial unique on `(field) WHERE user IS NULL` for system-wide
  rows + index on `(parent, user)`.

### Fixed

- `FormDefaultsMixin.get_initial` now passes `request.user` so per-user
  overrides apply via the mixin (the previous version always returned
  system-wide values).
- Race condition on first render of an unsnapshotted form when two requests
  hit at once (`update_form_db_repr` now wraps the body in
  `transaction.atomic` and swallows `IntegrityError` from concurrent
  inserts).
- `FormRepresentationManager.get_or_create_for_instance` now seeds `label`
  with `full_name` so admin never sees an empty label.

### Changed

- Per-process freshness cache in `core.get_form_defaults` skips redundant
  `update_form_db_repr` calls within a 60-second window.
- Test suite now runs against PostgreSQL via testcontainers (Docker
  required) instead of in-memory SQLite, matching the production target.

## [0.1.0] — 2026-05-09

### Added

- Initial public release. Extracted from
  [iplweb/bpp](https://github.com/iplweb/bpp) where it lived as the
  in-tree `formdefaults` Django app.
- `FormRepresentation`, `FormFieldRepresentation`, `FormFieldDefaultValue`
  models: store default values per form, per field, optionally per user.
- `FormDefaultsMixin` for class-based views: drop-in `get_initial()`
  that pulls saved defaults for the current user.
- `core.get_form_defaults(form_instance, label=None, user=None)` —
  programmatic access for non-CBV use.
- Two pre-existing migrations preserved verbatim from the original
  in-tree app (initial schema + Django 3.2 JSONField alter).
