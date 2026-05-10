# django-formdefaults

[![PyPI version](https://img.shields.io/pypi/v/django-formdefaults.svg)](https://pypi.org/project/django-formdefaults/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-formdefaults.svg)](https://pypi.org/project/django-formdefaults/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Database-backed default values for Django forms — let users (and admins)
save the values they typed last time and have them pre-filled on next visit.

Originally extracted from [iplweb/bpp](https://github.com/iplweb/bpp).

## What it does

Most non-trivial Django apps eventually grow a "remember what I last
selected" feature on report forms, filter forms, search forms.
`django-formdefaults` is the small infrastructure for that:

- Inspect any Django form, snapshot its fields into the database.
- For each field, store one *or many* default values:
  - **No `user` set** → the system-wide default (what new users see).
  - **`user` set**    → that user's personal override.
- On render, return a dict of `{field_name: value}` ready to feed into
  `Form(initial=...)` — the user's overrides shadow the global defaults.
- Show admins a Django admin page where they can curate per-form,
  per-user defaults without touching code.
- Bonus: each form can carry `html_before` / `html_after` snippets
  (also editable from the admin) that you can render around the form —
  useful for legends, contextual help, in-page docs.

It is deliberately *not*:

- A form-state-saver (no resume-where-you-left-off mid-edit).
- A draft-submission system.
- A wizard.

## Installation

```bash
pip install django-formdefaults
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "formdefaults",
]
```

Run migrations:

```bash
./manage.py migrate
```

The package requires Django 4.2+ and supports Django up through 5.2.
Postgres is the original target, but the JSONField storage is
database-agnostic from Django 3.1 onwards.

## Quick start

### In a class-based FormView

```python
from django.views.generic.edit import FormView
from formdefaults.helpers import FormDefaultsMixin

from .forms import MonthlyReportForm


class MonthlyReportView(FormDefaultsMixin, FormView):
    form_class = MonthlyReportForm
    template_name = "reports/monthly.html"
    title = "Monthly report"  # used as the human-readable form label

    def form_valid(self, form):
        ...
```

The first time `MonthlyReportView` is rendered, `formdefaults` snapshots
the form fields and stores each field's `Form.initial` value as the
system-wide default. On every subsequent render, `get_initial()` pulls
those defaults (with the current user's overrides layered on top) and
hands them to the form.

### Programmatic access

```python
from formdefaults.core import get_form_defaults

initial = get_form_defaults(MonthlyReportForm(), user=request.user)
form = MonthlyReportForm(initial=initial)
```

### Curating defaults from the Django admin

Go to **admin → Formdefaults → Lista wartości domyślnych formularza**.
Pick a form by its label, then for each field add or edit
`FormFieldDefaultValue` rows:

- Leave **User** empty → system-wide default.
- Set **User** → personal override for that user only.
- The **Value** is stored as JSON, so anything `json.dumps()`-able works.

`html_before` / `html_after` are plain text fields that surface in the
returned `initial` dict under the keys `formdefaults_pre_html` and
`formdefaults_post_html`. Render them however your template/form
layout system likes — e.g. via crispy-forms, plain `{{ form.initial.formdefaults_pre_html|safe }}`,
or your own helper.

## Public API

| Symbol | Purpose |
|---|---|
| `formdefaults.helpers.FormDefaultsMixin` | Drop-in CBV mixin: provides `get_initial()` and `get_form_title()`. |
| `formdefaults.core.get_form_defaults(form, label=None, user=None, update_db_repr=True)` | Snapshot the form's fields (if needed), return `{field_name: value}`. |
| `formdefaults.core.update_form_db_repr(form, form_repr, user=None)` | Lower-level: refresh DB representation of a form's fields. |
| `formdefaults.models.FormRepresentation` | One row per Django form class. |
| `formdefaults.models.FormFieldRepresentation` | One row per field of a form. |
| `formdefaults.models.FormFieldDefaultValue` | One row per (form, field, user-or-null) default value. |
| `formdefaults.util.full_name(obj)` | `module.ClassName` — used as the form's primary key. |

## How the storage looks

Three tables:

```
FormRepresentation
  full_name (PK)        # e.g. "myapp.forms.MonthlyReportForm"
  label                 # human-readable, editable in admin
  html_before, html_after

FormFieldRepresentation
  parent → FormRepresentation
  name, label, klass, order

FormFieldDefaultValue
  parent → FormRepresentation
  field  → FormFieldRepresentation
  user   → AUTH_USER_MODEL (nullable; null = system-wide)
  value  (JSON)
```

Layering on read: `system-wide values, then user values overlaid on top`.

## Limitations & gotchas

- A form is identified by its **fully qualified Python path**. Renaming
  or moving a `Form` class invalidates the saved defaults. There is
  currently no migration helper for that — rename, then re-curate.
- Only fields whose `initial` is JSON-serialisable get a stored
  default. Lambdas / callables on `initial` are skipped silently
  (they keep working at the form level — they just don't get persisted).
- `FormFieldDefaultValue.clean()` re-instantiates the form to validate
  the typed value against the field's `to_python()` / `validate()`.
  If your form's `__init__` does heavy work, admin saves are slow.

## Running the tests

```bash
pip install -e ".[test]"
pytest
```

The test suite uses an in-memory SQLite database — no Postgres is
required to run it.

## License

MIT — see [LICENSE](LICENSE).
