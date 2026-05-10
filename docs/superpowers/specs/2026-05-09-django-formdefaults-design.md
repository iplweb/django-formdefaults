# django-formdefaults — design spec

**Date:** 2026-05-09
**Status:** Draft — awaiting user review of this document.

## 1. Idea

`django-formdefaults` is a small Django app that lets you wire any Django form
into a database-backed default-values system in one line, and edit those
defaults at two scopes:

- **System-wide** — superuser edits in Django admin.
- **Per-user override** — end-user edits via a popup modal rendered next to
  the form on whatever page contains it.

A form's database representation (its set of fields, their order, types, labels
and snapshot of `Form.initial`) is created either:

1. **Pre-registered** at Django startup (decorator or `FORMDEFAULTS_FORMS`
   setting) — `post_migrate` snapshot runs as part of the deploy.
2. **Ad-hoc** at first render — the existing `get_form_defaults()` /
   `FormDefaultsMixin` path. No registration, snapshot happens on first GET.

On every render, `get_form_defaults(form, user=request.user)` returns
`{field_name: value}` ready to feed `Form(initial=...)`, with the user's
override layered on top of the system-wide value.

## 2. Architecture

```
src/formdefaults/
├── apps.py                   # AppConfig — connects post_migrate signal
├── models.py                 # FormRepresentation, FormFieldRepresentation,
│                             # FormFieldDefaultValue
├── core.py                   # get_form_defaults, update_form_db_repr
├── helpers.py                # FormDefaultsMixin
├── admin.py                  # system-wide editing
├── util.py                   # full_name, get_python_class_by_name
├── registry.py               # NEW: register_form, _registry, iter_registered_forms()
├── signals.py                # NEW: post_migrate handler -> snapshot all registered
├── views.py                  # NEW: UserFormDefaultsView (GET fragment / POST save)
├── forms.py                  # NEW: build_user_defaults_form()
├── urls.py                   # NEW: /formdefaults/edit/<form_full_name>/
├── templatetags/
│   └── formdefaults.py       # NEW: {% formdefaults_button form %}
├── templates/formdefaults/
│   ├── _button.html
│   ├── _modal_fragment.html
│   └── _user_edit_form.html
├── static/formdefaults/
│   ├── modal.js              # ~80 lines, vanilla
│   └── modal.css
└── migrations/               # +0003, 0004
```

Module boundaries:

- `registry` — only knows *which* forms were pre-registered. No DB writes.
- `signals` — on `post_migrate`, walks registry + `FORMDEFAULTS_FORMS`, calls
  `core.update_form_db_repr` for each entry. Only entry point that interacts
  with both registry and core.
- `core` — writes DB representation. No knowledge of registration or popup.
- `views` + `forms` + `urls` + `templatetags` + statics + templates — the
  user-edit popup module. Optional: a host project can leave it out by simply
  not including `formdefaults.urls`.
- `admin` — system-wide editing surface for superuser.

All three registration paths (decorator, setting, ad-hoc) call the same
`core.update_form_db_repr`. There is no parallel snapshot pipeline.

## 3. Data model

Three existing tables stay; one new field, one new constraint, one new index.

```
FormRepresentation
  full_name        TEXT  PK
  label            TEXT
  html_before      TEXT  null/blank
  html_after       TEXT  null/blank
  pre_registered   BOOL  default False           # NEW (0003)

FormFieldRepresentation
  parent           FK FormRepresentation
  name             TEXT
  label            TEXT  null/blank
  klass            TEXT
  order            uint16
  unique_together  (parent, name)

FormFieldDefaultValue
  parent           FK FormRepresentation
  field            FK FormFieldRepresentation
  user             FK AUTH_USER_MODEL  null=True (NULL = system-wide)
  value            JSON  null/blank
  unique_constraint (field, user)               # NEW (0004)
  index            (parent, user)               # NEW (0004)
```

**Why `pre_registered`:** informational only. Lets admin and tests distinguish
"this form was opted-in via decorator/setting" from "this form was discovered
ad-hoc on first render". Does not change behaviour; useful for diagnosis.

**Why unique `(field, user)`:** prevents duplicate override rows for the same
field+user. Today only enforced in code (via `get_or_create` paths); the
constraint guarantees consistency under concurrent writes / raw SQL / loaddata.
Postgres treats NULL as distinct so system-wide vs per-user co-exist.

**Why index `(parent, user)`:** every render runs
`SELECT … WHERE parent=… AND user IS NULL` plus
`… AND user=current_user`. Index removes a seq-scan as the table grows.

**Refactor — `FormRepresentationManager.get_or_create_for_instance`:**
sets `defaults={"label": full_name}` so the row is never created with an empty
`label` field.

**Out of scope (deliberately):**
- No PK migration (`full_name` stays text PK).
- No "scope" table (per-group, per-tenant). `user IS NULL` vs concrete user
  is sufficient; per-group can be added later as a nullable column without
  breaking changes.
- No snapshot versioning.

**Migrations:**
- `0003_formrepresentation_pre_registered.py` — add field.
- `0004_unique_field_user_and_index.py` — add constraint + index.
- `dedupe_formdefaults` management command shipped alongside 0004 for users
  who somehow accumulated duplicates. Documented in 0004 as optional pre-step.

## 4. Pre-registration

### Two paths in, one path out

```python
# formdefaults/registry.py
@dataclass(frozen=True)
class _Entry:
    form_class: type[forms.Form]
    label: str | None

_REGISTRY: dict[str, _Entry] = {}

def register_form(*, label: str | None = None):
    def decorator(form_class):
        full_name_str = f"{form_class.__module__}.{form_class.__name__}"
        _REGISTRY[full_name_str] = _Entry(form_class, label)
        return form_class
    return decorator

def iter_registered_forms():
    yielded = set()
    for entry in _REGISTRY.values():
        full_name_str = f"{entry.form_class.__module__}.{entry.form_class.__name__}"
        yielded.add(full_name_str)
        yield entry
    for dotted in getattr(settings, "FORMDEFAULTS_FORMS", []):
        if dotted in yielded:
            continue
        try:
            cls = import_string(dotted)
        except (ImportError, AttributeError):
            logger.warning("FORMDEFAULTS_FORMS: cannot import %r", dotted)
            continue
        yield _Entry(cls, getattr(cls, "formdefaults_label", None))
```

Convention: a class registered via `FORMDEFAULTS_FORMS` may carry an optional
class-level attribute `formdefaults_label = "Human-readable name"` — that
attribute, if present, becomes the row's `label`. Otherwise `__name__` is used.
The decorator path takes the label as a keyword argument, so this attribute
convention only applies to the setting path.

### Snapshot at startup

```python
# formdefaults/signals.py
@receiver(post_migrate)
def snapshot_registered_forms(sender, **kwargs):
    if sender.name != "formdefaults":
        return
    autodiscover_formdefaults()  # imports "<app>.forms" for each INSTALLED_APP
    for entry in iter_registered_forms():
        try:
            instance = entry.form_class()
        except TypeError:
            logger.warning("Cannot instantiate %s without args; skipping snapshot",
                           entry.form_class)
            continue
        form_repr, created = FormRepresentation.objects.get_or_create(
            full_name=full_name(instance),
            defaults={"label": entry.label or entry.form_class.__name__,
                      "pre_registered": True},
        )
        if not form_repr.pre_registered:
            form_repr.pre_registered = True
            if entry.label and form_repr.label != entry.label:
                form_repr.label = entry.label
            form_repr.save(update_fields=["pre_registered", "label"])
        update_form_db_repr(instance, form_repr, user=None)
```

### Why `post_migrate`, not `AppConfig.ready`

- `AppConfig.ready` runs during `makemigrations` on a brand-new project where
  `formdefaults_*` tables don't exist yet → would crash on first
  `makemigrations` call.
- `post_migrate` runs as part of `migrate` (a normal deploy step). Tables
  exist by then.
- pytest-django runs `post_migrate` on test DB creation, so tests cover it
  for free.

### Hardening `update_form_db_repr` against races

Three changes (motivation: the user has seen rare unique-violation exceptions
on production):

1. Wrap the function body in `transaction.atomic()`.
2. Replace `db_fields.create(...)` and `values_set.create(...)` with
   `get_or_create(...)` so that two concurrent renders of an as-yet-unsnapshotted
   form don't both try to insert the same `(parent, name)` or `(field, user)`
   row.
3. Catch `IntegrityError` at the function boundary, refresh `form_repr`, and
   short-circuit (the other request just finished snapshotting; we don't need
   to retry).

### Optional: per-process freshness cache

`core` keeps a module-level dict `_LAST_SNAPSHOT: dict[str, float]` keyed by
`full_name`, value = `time.monotonic()`. `get_form_defaults` skips
`update_form_db_repr` if last snapshot for this form was within the last 60s.
Cache is per-process, so deploys reset it. Pure performance optimisation, not
a correctness requirement.

### Public API additions

```python
from formdefaults import register_form        # NEW, re-exported from __init__.py
```

## 5. Per-user popup edit

### Endpoint

```
GET  /formdefaults/edit/<form_full_name>/   → modal HTML fragment
POST /formdefaults/edit/<form_full_name>/   → validate + save + fragment
```

`form_full_name` is URL-encoded FQN of the form class. The view requires login
(`LoginRequiredMixin`). Permission model: a logged-in user can only read/write
rows where `user=request.user` — superusers do system-wide edits via Django
admin, not via this popup.

### View (`formdefaults/views.py`)

```python
class UserFormDefaultsView(LoginRequiredMixin, View):
    def get(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(form_repr, user=request.user)
        return render(request, "formdefaults/_modal_fragment.html",
                      {"form_repr": form_repr, "edit_form": edit_form})

    def post(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(form_repr, user=request.user,
                                             data=request.POST)
        if edit_form.is_valid():
            edit_form.save()
            return render(request, "formdefaults/_modal_fragment.html",
                          {"form_repr": form_repr, "edit_form": edit_form,
                           "saved": True})
        return render(request, "formdefaults/_modal_fragment.html",
                      {"form_repr": form_repr, "edit_form": edit_form},
                      status=400)
```

### `build_user_defaults_form(form_repr, user, data=None)` (`formdefaults/forms.py`)

- Instantiate `form_repr.get_form_class()` once to harvest field types.
- For each field, copy `(name, label, widget, choices)` to a new `forms.Form`
  subclass, but force `required=False` — empty input means "no override".
- `initial` is loaded from existing `FormFieldDefaultValue(field, user=user)`
  rows.
- `save()` iterates submitted cleaned_data:
  - If value is non-empty → `update_or_create` `FormFieldDefaultValue` for
    `(field, user)`.
  - If value is empty AND an override exists → delete it.
- Each field uses Django's own `to_python()` / `validate()` for type checking.

### Template tag

```django
{% load formdefaults %}
{% formdefaults_button form %}
```

Renders:

```html
<button type="button" class="fd-edit-btn"
        data-fd-url="/formdefaults/edit/myapp.MyForm/">
  ⚙ Moje wartości domyślne
</button>
<div class="fd-modal-host" hidden></div>
```

If `request.user` is anonymous, the tag renders nothing. Tag accepts a form
instance and reads its FQN.

### JS (`static/formdefaults/modal.js`)

Vanilla, no dependencies, ~80 lines. Behaviour:

1. Document-level click delegate on `.fd-edit-btn`.
2. On click → `fetch(GET data-fd-url)` → inject HTML into nearest
   `.fd-modal-host` → reveal.
3. On modal form submit → `preventDefault`, `fetch(POST same URL with form-data)`
   → swap fragment.
4. Close: ESC, click on backdrop, or click on `.fd-modal-close`.

Host project must include the script:

```html
<script src="{% static 'formdefaults/modal.js' %}" defer></script>
```

This is documented in README. The module is opt-in: don't include the script,
no popup, package still works for `get_form_defaults` and admin.

### CSS

`static/formdefaults/modal.css` — minimal, namespaced `.fd-*`. Modal is
`position: fixed; inset: 0;` with a centered content card. Easily overridable.

## 6. Example project

Sits outside `src/`, excluded from build.

```
example_project/
├── manage.py
├── example_project/
│   ├── __init__.py
│   ├── settings.py     # SQLite, INSTALLED_APPS = [..., formdefaults, demo]
│   ├── urls.py         # admin, formdefaults.urls, demo.urls
│   └── wsgi.py
└── demo/
    ├── __init__.py
    ├── apps.py
    ├── forms.py        # 3 forms
    ├── views.py        # CBV + FBV
    ├── urls.py
    └── templates/
        ├── base.html
        └── demo/
            ├── report.html
            ├── settings.html
            └── search.html
```

**Three registration paths, one per form:**

1. `MonthlyReportForm` — `@register_form(label="Raport miesięczny")` in
   `demo/forms.py`. View: `MonthlyReportView(FormDefaultsMixin, FormView)`.
2. `UserSettingsForm` — no decorator. `example_project/settings.py` has
   `FORMDEFAULTS_FORMS = ["demo.forms.UserSettingsForm"]`.
3. `SearchForm` — no registration. View is a function-based view that calls
   `get_form_defaults(SearchForm())` and passes `initial=…`.

Each template renders `{% formdefaults_button form %}` next to the form.

**Build exclusion:**
- `pyproject.toml` `[tool.hatch.build.targets.sdist] include` lists only
  `src/formdefaults`, so `example_project/` is naturally excluded from sdist.
- `[tool.hatch.build.targets.wheel] packages = ["src/formdefaults"]` —
  excluded from wheel.
- Add `src/formdefaults/templates/**` and `src/formdefaults/static/**` to
  the wheel include list.
- Add `example_project/db.sqlite3` to `.gitignore`.

**Local run:** documented in README:

```bash
cd example_project
python manage.py migrate
python manage.py runserver
```

## 7. Tests

Coverage scope: full (unit + integration + view-level + smoke), no browser.

```
tests/
├── conftest.py                  # existing — normal_django_user fixture
├── settings.py                  # existing
├── test_models.py               # existing
├── test_core.py                 # existing
├── test_util.py                 # existing
├── test_register.py             NEW
├── test_signals.py              NEW
├── test_user_edit_view.py       NEW
└── test_example_project.py      NEW
```

### `test_register.py`

- `register_form` registers class + label.
- `register_form` without label falls back to `__name__`.
- `iter_registered_forms` yields decorated + setting entries, deduplicated by
  FQN (decorator wins).
- Setting entry that fails `import_string` → logged warning, no exception.

### `test_signals.py`

- `post_migrate` handler creates `FormRepresentation` and field rows for a
  registered form.
- Field that disappears from form on next snapshot is deleted.
- Field whose `klass` changes gets `klass` updated.
- Idempotent: running snapshot twice does not change row counts.

### Additions to `test_core.py`

- Race-condition swallow: monkeypatch first `get_or_create` to raise
  `IntegrityError`; assert `update_form_db_repr` does not propagate.
  (Lives in `test_core.py`, not `test_signals.py`, because the behaviour
  is in `core.update_form_db_repr` — the signal handler just calls it.)

### `test_user_edit_view.py`

- Anonymous → 302 to login.
- Logged-in GET → 200 + fragment containing form fields.
- POST valid value → `FormFieldDefaultValue(user=request.user)` row created.
- POST same field again → `update_or_create` (one row, not two).
- POST empty value when override exists → override deleted.
- POST invalid value → 400, error rendered in fragment.
- `user` from POST data is ignored — view always uses `request.user`.

### `test_example_project.py`

- `python manage.py check` against example settings returns 0.
- Each of the three demo URLs returns 200 via Django test Client.
- After first SearchForm render → `FormRepresentation(pre_registered=False)`
  exists.
- After `post_migrate` runs → `FormRepresentation(pre_registered=True)` exists
  for MonthlyReportForm and UserSettingsForm.

Configuration: a separate `tests/example_settings.py` extends `tests/settings.py`,
adds `FORMDEFAULTS_FORMS` and the example project on `pythonpath`. The
`test_example_project.py` module switches settings via pytest mark.

## 8. Build, packaging, README

**`pyproject.toml`:**
- Wheel/sdist packaging already excludes `example_project/`.
- Add to wheel: `src/formdefaults/templates/**`, `src/formdefaults/static/**`,
  `src/formdefaults/templatetags/**`.

**README structure:**
- "Idea" — short paraphrase of the brief.
- "What it does" — extended with pre-registration and per-user popup.
- "Quick start" — decorator path + setting path + ad-hoc path.
- "Editing defaults" — split into "System-wide (admin)" and
  "Per-user (popup next to form)".
- "Try it locally" — link + commands for `example_project/`.
- "Public API" — adds `register_form`, `UserFormDefaultsView`,
  `{% formdefaults_button %}`, `build_user_defaults_form`.
- "Storage" — minor update for `pre_registered`.
- "Limitations & gotchas" — adds note on JS modal opt-in.

## 9. Out of scope (explicitly)

- Selenium / browser tests (modal JS validated only by endpoint tests + manual
  example_project check).
- Per-group / per-tenant defaults.
- Snapshot version history.
- Bootstrap/Tailwind/HTMX integration in the popup module (CSS class names
  are namespaced and easy to override; we don't ship adapters).
- Any change to PK strategy of `FormRepresentation`.
