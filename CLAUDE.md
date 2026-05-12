# django-formdefaults — Claude project notes

Per-user, database-backed default values for Django forms. Published on
PyPI as `django-formdefaults`.

## Repository layout

- `src/formdefaults/` — the published package. Everything inside here
  ships in the wheel/sdist.
- `example_project/` — a runnable Django site that demos the package.
  **Never shipped on PyPI.** Excluded from sdist/wheel by
  `[tool.hatch.build.targets.{sdist,wheel}]` in `pyproject.toml`.
- `tests/` — pytest suite. Uses `pytest-django` + a Postgres
  `testcontainer` started in `tests/settings.py`. Run with `pytest`.
- `dist/` — gitignored build artifacts.

The `Makefile` and `example_project/` are deliberately NOT included
in the published distribution.

## i18n — translation catalogs MUST stay isolated

Two separate `django.po` files live in this repo:

| Path | Scope | Shipped? |
|---|---|---|
| `src/formdefaults/locale/<lang>/LC_MESSAGES/django.po` | strings used inside `src/formdefaults/` only | yes — in the wheel |
| `example_project/demo/locale/<lang>/LC_MESSAGES/django.po` | demo-only strings | no |

**Why it matters.** Django merges per-app translations on top of its core
catalog at runtime. If the published package's `.po` accidentally carries
a generic msgid like `"Log in"` translated as `"Zaloguj"`, every Django
site that installs `formdefaults` will lose Django core's `"Zaloguj się"`
on the admin login page. This actually happened pre-0.6.2 (see CHANGELOG).

**The rule.** Never run `django-admin makemessages` from the repo root.
xgettext walks everything under cwd, so a root-level run will harvest demo
strings into the package catalog. Always run from inside the right scope.

### Workflow

Use the `Makefile`:

```bash
make messages          # regenerates both .po files in the right cwd each
make messages-pkg      # only src/formdefaults/
make messages-example  # only example_project/demo/
make compilemessages   # both .mo files

make messages LOCALE=de   # add a new locale
```

The `LOCALE` variable is named that way on purpose — calling it `LANG`
would silently inherit the shell's `$LANG` env var (e.g.
`pl_PL.UTF-8`), and `makemessages` would create a `pl_PL.UTF-8/`
directory next to `pl/`.

If you must invoke `makemessages` manually:

```bash
cd src/formdefaults && django-admin makemessages -l pl --no-obsolete
cd example_project && python manage.py makemessages -l pl --no-obsolete
```

## Release workflow

1. Bump `version` in `pyproject.toml`.
2. Add a section to `CHANGELOG.md` (Keep-a-Changelog format, semver).
3. `make messages compilemessages` if any translatable strings changed.
4. Commit (typical message: `chore: release X.Y.Z`).
5. `git tag -a vX.Y.Z -m "Release X.Y.Z"`.
6. `git push origin main vX.Y.Z`.
7. `rm dist/django_formdefaults-*` (optional — clean slate).
8. `uv build`.
9. `uv publish` (or `uv publish dist/django_formdefaults-X.Y.Z*` to be
   explicit when older artifacts are still in `dist/`).

The `[example]` extra pins `run-site>=0.4` because `run-site` 0.5+ has
been renamed to `django-run-site` and is not yet on PyPI — PyPI rejects
direct git URLs in extras. Don't "fix" this by adding a git URL.

## Testing

```bash
pytest                              # full suite, uses Postgres testcontainer
pytest tests/test_core.py -k name   # single test
```

`tests/settings.py` starts a `postgres:16-alpine` container at import
time and stops it via `atexit`. Docker must be running.

## Permissions / conventions

- Direct pushes to `main` may be blocked by Claude Code's auto-mode
  classifier even though the project's history uses them. The user
  will approve interactively when needed.
- Don't commit `runsite.toml`, `.dev_helpers_port`, `.dev_helpers_token`
  at the repo root — they are per-developer generated files. (They
  should arguably be added to `.gitignore`; not done yet.)
