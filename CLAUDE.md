# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`django-formdefaults` is a Django app shipped on PyPI as `django-formdefaults`.
Per-user + system-wide database-backed defaults for any Django form, edited
from a popup. Originally extracted from `iplweb/bpp`.

## Repository layout

- `src/formdefaults/` — the published package. Everything inside here ships
  in the wheel/sdist. **Nothing outside is shipped.**
- `example_project/` — a runnable demo Django site. Excluded from the
  distribution by `[tool.hatch.build.targets.{sdist,wheel}]` in
  `pyproject.toml`.
- `tests/` — pytest suite. `tests/settings.py` boots a
  `postgres:16-alpine` testcontainer at import time and stops it via
  `atexit`. Docker must be running.
- `dist/` — gitignored build output.
- `Makefile` — local-only helper (not shipped).

## Big picture

Three DB models live in `src/formdefaults/models.py`:

- `FormRepresentation` (PK = dotted `full_name` of the Form class) — one
  row per registered form. Carries optional `html_before` / `html_after`
  and a `pre_registered` flag (True when registered via decorator/setting
  rather than discovered lazily).
- `FormFieldRepresentation` — one row per field of a representation,
  records `name`, `klass` (dotted), `label`, `order`.
- `FormFieldDefaultValue` — the actual default. Either system-wide
  (`user=NULL`) or per-user. JSON-serialized via
  `forms._serialize`. `is_auto_snapshot=True` means "this row mirrors
  `Form.initial` from code and may be refreshed automatically".
  Any UI edit flips it to `False` and freezes the row.

**Resolution order at render time** (per field): per-user override →
system-wide default → code-level `Form.initial`. Per-user shadows
system; both shadow code.

**Three registration paths**, all funnel through
`core.update_form_db_repr`:

1. `@register_form` decorator (`registry.py`) — class is registered in
   a module-level dict, then `signals.snapshot_registered_forms`
   (connected to `post_migrate`) instantiates each and snapshots its
   fields. `signals.autodiscover_formdefaults` imports `<app>.forms` for
   every installed app first.
2. `FORMDEFAULTS_FORMS` setting — list of dotted Form paths, imported
   and snapshotted the same way.
3. Lazy / zero-registration — `FormDefaultsMixin` (or calling
   `core.get_form_defaults(form, user)` directly from a view) snapshots
   on first render. The freshness cache `core._LAST_SNAPSHOT` keeps
   re-snapshots cheap (`SNAPSHOT_TTL_SECONDS = 60.0`, per-process).

**Snapshot reconciliation** (`core._do_update`): keys in `Form.fields`
get an `INSERT … ON CONFLICT` upsert into `FormFieldRepresentation`;
rows for keys that disappeared from code get deleted. `klass` and
`label` updates only touch the row if they actually changed.
`FormFieldDefaultValue` rows with `is_auto_snapshot=True` are kept in
sync with `Form.initial`; rows with `is_auto_snapshot=False` are
preserved verbatim.

**Editing UI**: server-rendered modal fragment, plain JS
(`src/formdefaults/static/formdefaults/modal.{js,css}`). No
jQuery/HTMX. `views.UserFormDefaultsView` (per-user scope) and
`views.SystemFormDefaultsView` (system scope) both render
`templates/formdefaults/_modal_fragment.html`. The dynamic edit form
is built by `forms.build_user_defaults_form` / `build_system_defaults_form`
— each "real" field gets a paired `_override_<name>` checkbox; on POST,
unchecked override means "delete the row".

**System-wide permission hook** (`permissions.py`): resolution order
per-form `formdefaults_can_edit_system_wide` attribute →
`settings.FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE` (dotted path) →
`user.is_superuser`.

**`apps.ready()`** wires the `post_migrate` signal and sets
`default_auto_field = AutoField` (pinned for backwards-compat with
projects whose `0001_initial` predates `BigAutoField`).

## Common commands

```bash
pytest                                  # full suite (needs Docker)
pytest tests/test_core.py::test_name    # single test
ruff check                              # lint
ruff check --fix                        # lint + autofix
ruff format                             # format
pre-commit run --all-files              # both, on all files
make messages                           # regen both .po files safely
make compilemessages                    # compile both .mo files
uv build                                # wheel + sdist into dist/
uv run example_project/manage.py runserver
uv run --extra=example example_project/manage.py run_site  # full demo stack
```

## i18n — translation catalogs MUST stay isolated

Two separate `django.po` files live in this repo:

| Path | Scope | Shipped? |
|---|---|---|
| `src/formdefaults/locale/<lang>/LC_MESSAGES/django.po` | strings used inside `src/formdefaults/` | yes — in the wheel |
| `example_project/demo/locale/<lang>/LC_MESSAGES/django.po` | demo-only strings | no |

**Why it matters.** Django merges per-app translations on top of its core
catalog at runtime. If the published package's `.po` accidentally carries
a generic msgid like `"Log in"` translated as `"Zaloguj"`, every Django
site that installs `formdefaults` loses Django core's `"Zaloguj się"` on
the admin login page. This actually happened pre-0.6.2 (see CHANGELOG).

**The rule.** Never run `django-admin makemessages` from the repo root.
xgettext walks everything under cwd, so a root-level run will harvest
demo strings into the package catalog. Always cd into the right scope —
the `Makefile` does this for you.

```bash
make messages LOCALE=de   # add a new locale (LOCALE, not LANG — the
                          # latter clashes with the shell env var)
```

Manual equivalents (if you can't / won't use `make`):

```bash
cd src/formdefaults && django-admin makemessages -l pl --no-obsolete
cd example_project && python manage.py makemessages -l pl --no-obsolete
```

## Release workflow

1. Bump `version` in `pyproject.toml`.
2. Add a section to `CHANGELOG.md` (Keep-a-Changelog, semver).
3. `make messages compilemessages` if translatable strings changed.
4. Commit (`chore: release X.Y.Z`).
5. `git tag -a vX.Y.Z -m "Release X.Y.Z"`.
6. `git push origin main vX.Y.Z`.
7. `uv build`.
8. `uv publish` — or `uv publish dist/django_formdefaults-X.Y.Z*` when
   older versions still linger in `dist/`.

The `[example]` extra pins `run-site>=0.4` because `run-site` 0.5+ has
been renamed to `django-run-site` and is not yet on PyPI — PyPI rejects
direct git URLs in extras. Don't "fix" this by adding a git URL.

## Conventions

- Direct pushes to `main` may be blocked by Claude Code's auto-mode
  classifier even though the project's history uses them. The user
  approves interactively when needed.
- `runsite.toml`, `.dev_helpers_port`, `.dev_helpers_token` at the repo
  root are per-developer files — don't commit them.
- `apps.py` pins `default_auto_field = AutoField` deliberately. Don't
  "modernize" it to `BigAutoField` — it would surface as a spurious
  migration on every project that already has this app installed.
