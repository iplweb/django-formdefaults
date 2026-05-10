# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
