# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] — 2026-05-11

### Added

- **System-wide defaults from the popup.** A second "System defaults"
  button next to the personal one opens the same modal bound to
  `FormFieldDefaultValue` rows with `user=NULL`. Modal is visibly flagged
  (amber accent, "applies to ALL users" notice) to avoid scope mistakes.
- `formdefaults.views.SystemFormDefaultsView` (`formdefaults:system-edit`
  URL) — backs the new popup; reuses `build_user_defaults_form(user=None)`
  and validates via the permission hook.
- `formdefaults.permissions.can_edit_system_wide_defaults(user, form_repr=None, form_class=None)`
  — pluggable permission hook. Resolution order: per-form class attribute
  `formdefaults_can_edit_system_wide(user, form_repr) -> bool` → settings
  `FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE` (dotted path) → default
  (`user.is_superuser`).
- Demo: `SearchForm` in `example_project` opts out of system-wide editing
  via the per-form attribute, exercising the hook end-to-end.
- README "Screenshots" section embedding three rendered shots (regular
  user, admin both-buttons, admin system modal) under
  `docs/screenshots/`.
- Polish translations for the new strings ("System defaults",
  system-wide warning text, modal help).

### Changed

- `{% formdefaults_button form %}` now renders a second button only when
  the permission hook returns True for the request user — otherwise the
  output is unchanged.
- Popup closes automatically on a successful save (HTTP 200). Errors
  (HTTP 400) still re-render in place with field-level error messages.

## [0.4.1] — 2026-05-10

### Added

- HTML `title` tooltip on every override checkbox in the popup —
  hovering explains the toggle.
- Help text in the popup modal explaining the checkbox-vs-value
  contract, so users discover the UX without reading docs.
- Polish translation shipped in
  `src/formdefaults/locale/pl/LC_MESSAGES/django.{po,mo}`.

### Changed

- Package templates (`_button.html`, `_modal_fragment.html`) now use
  English source strings wrapped in `{% trans %}`. Polish-speaking
  installs see the same text via `LANGUAGE_CODE='pl'`.
- example_project is now fully internationalised: English source plus
  a Polish `.po`/`.mo`, language switcher in nav, `LocaleMiddleware`
  wired up.
- README "Per-user popup" section: removed obsolete "Empty input
  clears the override" sentence (superseded by v0.4.0's override
  checkbox).

## [0.4.0] — 2026-05-10

### Added

- Per-field override toggle in the popup edit form. Each value field
  has a companion `_override_<name>` checkbox rendered to its left.
  Unchecked → the field is **not** written as an override on save (and
  any existing override is deleted). Checked → the value is upserted as
  the user's override, regardless of what the value is.
- `_user_edit_form.html` template uses a new `form.field_pairs()` helper
  that yields `(override_checkbox, value_field)` tuples in `fields_set`
  order.
- `modal.js` auto-checks the override checkbox when the user edits a
  field's value (input/change events). The user can manually uncheck it
  to revert.
- Default initial value for the popup field is now the currently-effective
  default (user override if present, else system-wide), so the user can
  see what they're getting and edit from there.

### Changed (BREAKING)

- `build_user_defaults_form().save()` no longer treats empty input as
  "delete this override". The override checkbox controls write/delete
  exclusively. POST data must include `_override_<name>=on` for any
  field the caller wants to upsert.
- The popup template `_user_edit_form.html` now expects the form to
  expose `field_pairs()`. Custom templates overriding it must adapt.

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
