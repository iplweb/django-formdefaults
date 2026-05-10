# django-formdefaults

[![PyPI version](https://img.shields.io/pypi/v/django-formdefaults.svg)](https://pypi.org/project/django-formdefaults/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-formdefaults.svg)](https://pypi.org/project/django-formdefaults/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Database-backed default values for Django forms. Plug it into any Django form
in one line and admins (system-wide) plus end-users (personal overrides) can
curate `Form.initial` from the UI.

Originally extracted from [iplweb/bpp](https://github.com/iplweb/bpp).

## Idea

When a form is rendered, `django-formdefaults`:

1. **Builds or refreshes a representation of the form in the DB** — its set
   of fields, their order, types and labels, and a snapshot of `Form.initial`.
2. **Lets you set default values per field** — e.g. a boolean that should
   always default to `True`, a date that should always default to the current
   month, an integer with a fixed initial.
3. **Exposes two editing scopes**:
   - **System-wide** — any superuser edits in Django admin (one default per
     field, applied to everyone).
   - **Per-user** — each logged-in user overrides their own copy via a popup
     rendered next to the form. Their override shadows the system-wide value.

A form's DB representation can be created in **three ways**:

- `@register_form` decorator on the Form class — snapshot at Django startup
  (`post_migrate`).
- `FORMDEFAULTS_FORMS` setting — list of dotted paths, also snapshot at
  startup. Useful for forms you don't own.
- **No registration** — snapshot happens on first render via
  `get_form_defaults()` / `FormDefaultsMixin`.

## Installation

```bash
pip install django-formdefaults
```

`INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "formdefaults",
]
```

`urls.py` (only required if you want the per-user popup):

```python
urlpatterns = [
    # ...
    path("formdefaults/", include("formdefaults.urls")),
]
```

Run migrations:

```bash
./manage.py migrate
```

Requires Django 4.2+ and Python 3.10+.

## Quick start

### Path 1 — Decorator (recommended for forms you own)

```python
# myapp/forms.py
from django import forms
from formdefaults import register_form

@register_form(label="Monthly report")
class MonthlyReportForm(forms.Form):
    year = forms.IntegerField(initial=2026)
    month = forms.ChoiceField(choices=[(i, str(i)) for i in range(1, 13)])
```

Snapshot is created on `migrate`.

### Path 2 — Setting (for forms you don't own)

```python
# settings.py
FORMDEFAULTS_FORMS = [
    "thirdparty.forms.SomeForm",
    "myapp.forms.UserSettingsForm",
]
```

Optional class-level `formdefaults_label = "..."` becomes the row's label;
otherwise the class name is used.

### Path 3 — Ad-hoc (no registration)

In a CBV, mix in `FormDefaultsMixin`:

```python
from formdefaults.helpers import FormDefaultsMixin

class MonthlyReportView(FormDefaultsMixin, FormView):
    form_class = MonthlyReportForm
    title = "Monthly report"
```

In an FBV, call `get_form_defaults`:

```python
from formdefaults.core import get_form_defaults

initial = get_form_defaults(MonthlyReportForm(), user=request.user)
form = MonthlyReportForm(initial=initial)
```

Either way, snapshot is created on first render.

## Editing defaults

### System-wide (Django admin)

`/admin/formdefaults/formrepresentation/` — pick a form by label, then for
each field add or edit a `FormFieldDefaultValue` row with `User` empty.

The `FormRepresentation` row also has `html_before` and `html_after` text
fields, useful for surfacing in-form legends, contextual help, or a quick
note. They land in the form's `initial` dict under
`formdefaults_pre_html` and `formdefaults_post_html`. Render them in your
template however you like:

```django
{{ form.initial.formdefaults_pre_html|safe }}
{{ form }}
{{ form.initial.formdefaults_post_html|safe }}
```

### Per-user (popup next to the form)

In your template:

```django
{% load formdefaults static %}

<form method="post">
  {% csrf_token %}
  {{ form }}
  <button type="submit">Submit</button>
</form>

{% formdefaults_button form %}

<script src="{% static 'formdefaults/modal.js' %}" defer></script>
<link rel="stylesheet" href="{% static 'formdefaults/modal.css' %}">
```

> Place `{% formdefaults_button form %}` **outside** the `<form>` element — the modal injects its own `<form>` for saving overrides, and HTML5 forbids nesting forms.

The button only renders for authenticated users. Clicking it opens a modal
with one input per form field, pre-filled with the currently-effective
default value (your override if you have one, otherwise the system-wide
value).

Each field in the popup has a small checkbox to its left. The checkbox
controls whether your edit becomes an override:

- Unchecked → leave the field alone; the system-wide default applies to
  you.
- Checked → save the value next to it as your personal override.

The checkbox auto-checks when you actually edit the field, so the common
flow is "type your new value, save". Uncheck if you want to delete a
previously-saved override.

## Try it locally

```bash
git clone https://github.com/iplweb/django-formdefaults
cd django-formdefaults/example_project
python manage.py migrate
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. Three forms demonstrate all three registration
paths. Create a superuser (`./manage.py createsuperuser`) to try system-wide
editing in `/admin/`.

## Public API

| Symbol | Purpose |
|---|---|
| `formdefaults.register_form` | Decorator: register a Form class for startup snapshot. |
| `formdefaults.helpers.FormDefaultsMixin` | CBV mixin: provides `get_initial()`. |
| `formdefaults.core.get_form_defaults(form, label=None, user=None, update_db_repr=True)` | Snapshot + return `{field_name: value}`. |
| `formdefaults.core.update_form_db_repr(form, form_repr, user=None)` | Lower-level: refresh DB representation. |
| `formdefaults.forms.build_user_defaults_form(form_repr, user, data=None)` | Build the popup edit form. |
| `formdefaults.views.UserFormDefaultsView` | View backing the popup endpoint. |
| `{% formdefaults_button form %}` | Template tag rendering the "edit my defaults" button. |
| `formdefaults.models.FormRepresentation` / `FormFieldRepresentation` / `FormFieldDefaultValue` | DB models. |

## Storage

Three tables:

```
FormRepresentation
  full_name (PK)         # "myapp.forms.MonthlyReportForm"
  label                  # human-readable
  pre_registered         # True if registered via decorator/setting
  html_before, html_after

FormFieldRepresentation
  parent → FormRepresentation
  name, label, klass, order
  unique_together (parent, name)

FormFieldDefaultValue
  parent → FormRepresentation
  field  → FormFieldRepresentation
  user   → AUTH_USER_MODEL  # nullable; null = system-wide
  value  (JSON)
  is_auto_snapshot          # True until first UI edit; sticky after
  unique constraint (field, user) for non-NULL users
  unique constraint (field) WHERE user IS NULL for system-wide
```

## Limitations & gotchas

- Forms identified by fully qualified Python path. Renaming or moving a Form
  class invalidates the saved defaults.
- Only fields whose `initial` is JSON-serialisable get a stored default.
  Lambdas / callables on `initial` keep working at the form level but aren't
  persisted.
- `FormFieldDefaultValue.clean()` re-instantiates the form to validate typed
  values. Forms with heavy `__init__` cost slow down admin saves.
- The popup is opt-in: it only works if you include `formdefaults.urls`,
  load the template tag, and serve the static JS/CSS.
- `is_auto_snapshot` is set to True heuristically for pre-0.3.0 rows
  during the data migration: rows whose value matches the form's
  current `initial` become `True` (the row looks untouched), the rest
  become `False`. False positives happen rarely (someone deliberately
  edited the value to match the code default and the data migration
  can't tell). False positives become real on the next code change —
  the value is treated as auto-snapshot and refreshed.

## Running the tests

```bash
pip install -e ".[test]"
pytest
```

Tests run against PostgreSQL via [testcontainers](https://testcontainers-python.readthedocs.io/) — Docker is required on the test machine.

## License

MIT — see [LICENSE](LICENSE).
