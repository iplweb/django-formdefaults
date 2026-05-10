# django-formdefaults v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `django-formdefaults` with pre-registration of forms (decorator + `FORMDEFAULTS_FORMS` setting + `post_migrate` snapshot), a per-user popup edit UX (endpoint + vanilla JS modal + template tag), an `example_project/` demonstrating all three registration paths, schema hardening (`pre_registered` flag, unique constraint, race-condition handling), and full test coverage.

**Architecture:** Three new internal modules — `registry`, `signals`, `forms+views+urls+templatetags+statics` — each with a single responsibility. Existing `core.update_form_db_repr` is the only writer of representation rows; both pre-registration and ad-hoc paths call it. The popup module is fully optional (host project can leave `formdefaults.urls` un-included).

**Tech Stack:** Django 4.2+, Python 3.10+, pytest-django, hatchling, vanilla JS (no jQuery/HTMX dependency).

**Spec:** `docs/superpowers/specs/2026-05-09-django-formdefaults-design.md`

---

## File Structure

**Created:**
- `src/formdefaults/registry.py` — `register_form`, `iter_registered_forms`
- `src/formdefaults/signals.py` — post_migrate handler + `autodiscover_formdefaults`
- `src/formdefaults/forms.py` — `build_user_defaults_form`
- `src/formdefaults/views.py` — `UserFormDefaultsView`
- `src/formdefaults/urls.py` — `formdefaults:user-edit` route
- `src/formdefaults/templatetags/__init__.py`
- `src/formdefaults/templatetags/formdefaults.py` — `{% formdefaults_button %}`
- `src/formdefaults/templates/formdefaults/_button.html`
- `src/formdefaults/templates/formdefaults/_modal_fragment.html`
- `src/formdefaults/templates/formdefaults/_user_edit_form.html`
- `src/formdefaults/static/formdefaults/modal.js`
- `src/formdefaults/static/formdefaults/modal.css`
- `src/formdefaults/management/__init__.py`
- `src/formdefaults/management/commands/__init__.py`
- `src/formdefaults/management/commands/dedupe_formdefaults.py`
- `src/formdefaults/migrations/0003_formrepresentation_pre_registered.py`
- `src/formdefaults/migrations/0004_unique_field_user.py`
- `example_project/manage.py`
- `example_project/example_project/{__init__,settings,urls,wsgi}.py`
- `example_project/demo/{__init__,apps,forms,views,urls}.py`
- `example_project/demo/templates/base.html`
- `example_project/demo/templates/demo/{report,settings,search}.html`
- `tests/test_register.py`
- `tests/test_signals.py`
- `tests/test_user_edit_view.py`
- `tests/test_example_project.py`
- `tests/example_settings.py`

**Modified:**
- `src/formdefaults/__init__.py` — re-export `register_form`
- `src/formdefaults/apps.py` — wire signals
- `src/formdefaults/core.py` — race-hardening + freshness cache
- `src/formdefaults/models.py` — `pre_registered` field, label fallback
- `src/formdefaults/admin.py` — minor: show `pre_registered` in list_display
- `tests/test_core.py` — race-condition test
- `pyproject.toml` — wheel includes for templates/static/templatetags
- `README.md` — Idea section, registration paths, popup, example
- `CHANGELOG.md` — 0.2.0 entry
- `.gitignore` — `example_project/db.sqlite3`

---

## Task 1: Initialize git repo + baseline commit

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Initialize git**

```bash
cd /home/mpasternak/Programowanie/django-formdefaults
git init
git add -A
git commit -m "chore: import django-formdefaults baseline"
```

Expected: a single commit on `main` with all current files.

- [ ] **Step 2: Verify pytest still passes from baseline**

```bash
.venv/bin/pytest -q
```

Expected: existing tests pass (the suite that was there before any changes).

---

## Task 2: Migration 0003 — `pre_registered` field

**Files:**
- Modify: `src/formdefaults/models.py`
- Create: `src/formdefaults/migrations/0003_formrepresentation_pre_registered.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
@pytest.mark.django_db
def test_FormRepresentation_pre_registered_default_false():
    fr = FormRepresentation.objects.create(full_name="x.Y", label="Y")
    assert fr.pre_registered is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_models.py::test_FormRepresentation_pre_registered_default_false -v
```

Expected: FAIL with `AttributeError` or migration error.

- [ ] **Step 3: Add field to model**

Edit `src/formdefaults/models.py`. After the `html_after` field of `FormRepresentation`, add:

```python
    pre_registered = models.BooleanField(
        "Zarejestrowany przez pre-rejestrację",
        default=False,
        help_text="True jeśli formularz został zarejestrowany dekoratorem "
                  "@register_form lub przez setting FORMDEFAULTS_FORMS.",
    )
```

- [ ] **Step 4: Generate migration**

```bash
DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django makemigrations formdefaults --name formrepresentation_pre_registered
```

Expected: writes `src/formdefaults/migrations/0003_formrepresentation_pre_registered.py`.

- [ ] **Step 5: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_models.py::test_FormRepresentation_pre_registered_default_false -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/formdefaults/models.py src/formdefaults/migrations/0003_formrepresentation_pre_registered.py tests/test_models.py
git commit -m "feat(model): add FormRepresentation.pre_registered flag"
```

---

## Task 3: Migration 0004 — unique constraint + index + dedupe command

**Files:**
- Modify: `src/formdefaults/models.py`
- Create: `src/formdefaults/migrations/0004_unique_field_user.py`
- Create: `src/formdefaults/management/__init__.py`
- Create: `src/formdefaults/management/commands/__init__.py`
- Create: `src/formdefaults/management/commands/dedupe_formdefaults.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
from django.db import IntegrityError

@pytest.mark.django_db
def test_FormFieldDefaultValue_unique_field_user(test_form_repr, test_form):
    from formdefaults.core import update_form_db_repr
    from formdefaults.models import FormFieldDefaultValue
    update_form_db_repr(test_form, test_form_repr)
    field = test_form_repr.fields_set.first()
    FormFieldDefaultValue.objects.filter(field=field, user=None).delete()
    FormFieldDefaultValue.objects.create(parent=test_form_repr, field=field, user=None, value=1)
    with pytest.raises(IntegrityError):
        FormFieldDefaultValue.objects.create(parent=test_form_repr, field=field, user=None, value=2)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_models.py::test_FormFieldDefaultValue_unique_field_user -v
```

Expected: FAIL — second `create` succeeds because there's no constraint yet.

- [ ] **Step 3: Add constraint + index to model Meta**

Edit `src/formdefaults/models.py`. In `FormFieldDefaultValue.Meta`, replace the existing `Meta` body with:

```python
    class Meta:
        verbose_name = "Wartość domyslna dla pola formularza"
        verbose_name_plural = "Wartości domyślne dla pól formularzy"
        ordering = ("user", "field__order")
        constraints = [
            models.UniqueConstraint(
                fields=["field", "user"],
                name="fd_unique_field_user",
            ),
        ]
        indexes = [
            models.Index(fields=["parent", "user"], name="fd_parent_user_idx"),
        ]
```

- [ ] **Step 4: Generate migration**

```bash
DJANGO_SETTINGS_MODULE=tests.settings .venv/bin/python -m django makemigrations formdefaults --name unique_field_user
```

Expected: writes `src/formdefaults/migrations/0004_unique_field_user.py`.

- [ ] **Step 5: Create the dedupe command**

Create `src/formdefaults/management/__init__.py` (empty file).
Create `src/formdefaults/management/commands/__init__.py` (empty file).
Create `src/formdefaults/management/commands/dedupe_formdefaults.py`:

```python
from django.core.management.base import BaseCommand
from django.db.models import Count, Max

from formdefaults.models import FormFieldDefaultValue


class Command(BaseCommand):
    help = (
        "Remove duplicate FormFieldDefaultValue rows. Keeps the row with the "
        "highest id per (field, user) tuple. Run before applying migration "
        "0004 if your existing DB has duplicates."
    )

    def handle(self, *args, **options):
        groups = (
            FormFieldDefaultValue.objects.values("field_id", "user_id")
            .annotate(n=Count("id"), keeper=Max("id"))
            .filter(n__gt=1)
        )
        deleted_total = 0
        for g in groups:
            qs = FormFieldDefaultValue.objects.filter(
                field_id=g["field_id"], user_id=g["user_id"]
            ).exclude(id=g["keeper"])
            count = qs.count()
            qs.delete()
            deleted_total += count
            self.stdout.write(
                f"  field={g['field_id']} user={g['user_id']}: removed {count}"
            )
        self.stdout.write(self.style.SUCCESS(f"Total removed: {deleted_total}"))
```

- [ ] **Step 6: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_models.py::test_FormFieldDefaultValue_unique_field_user -v
```

Expected: PASS — IntegrityError is raised on the second insert.

- [ ] **Step 7: Run full test suite to confirm no regressions**

```bash
.venv/bin/pytest -q
```

Expected: all tests pass (including pre-existing ones).

- [ ] **Step 8: Commit**

```bash
git add src/formdefaults/models.py src/formdefaults/migrations/0004_unique_field_user.py src/formdefaults/management tests/test_models.py
git commit -m "feat(model): add unique(field,user) constraint + (parent,user) index + dedupe command"
```

---

## Task 4: Harden `update_form_db_repr` against race condition

**Files:**
- Modify: `src/formdefaults/core.py`
- Modify: `tests/test_core.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core.py`:

```python
from unittest.mock import patch
from django.db import IntegrityError

@pytest.mark.django_db
def test_update_form_db_repr_swallows_integrity_error(test_form, test_form_repr, monkeypatch):
    """Simulate two concurrent renders racing to snapshot the same form."""
    real_get_or_create = test_form_repr.fields_set.get_or_create
    calls = {"n": 0}

    def fake_get_or_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("simulated race")
        return real_get_or_create(*args, **kwargs)

    with patch("formdefaults.core.FormFieldRepresentation.objects.get_or_create",
               side_effect=fake_get_or_create):
        # Should not raise.
        core.update_form_db_repr(test_form, test_form_repr)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_core.py::test_update_form_db_repr_swallows_integrity_error -v
```

Expected: FAIL — `IntegrityError` propagates.

- [ ] **Step 3: Refactor core.py**

Replace the entire body of `src/formdefaults/core.py` with:

```python
import json
import logging
import time

from django.db import IntegrityError, transaction
from django.db.models import Q

from formdefaults.util import full_name

logger = logging.getLogger(__name__)

_LAST_SNAPSHOT: dict[str, float] = {}
SNAPSHOT_TTL_SECONDS = 60.0


def _do_update(form_instance, form_repr, user=None):
    from formdefaults.models import FormFieldRepresentation, FormFieldDefaultValue

    form_fields = form_instance.fields
    form_fields_names = list(form_fields.keys())

    # Delete fields that are no longer in the form
    form_repr.fields_set.filter(~Q(name__in=form_fields_names)).delete()

    db_fields = {f.name: f for f in form_repr.fields_set.all()}

    for no, field_name in enumerate(form_fields_names):
        form_field = form_fields[field_name]
        new_klass = full_name(form_field)
        new_label = form_field.label or field_name.replace("_", " ").capitalize()

        db_field, created = FormFieldRepresentation.objects.get_or_create(
            parent=form_repr,
            name=field_name,
            defaults={"klass": new_klass, "label": new_label, "order": no},
        )

        update_fields = []
        if db_field.label != new_label:
            db_field.label = new_label
            update_fields.append("label")
        if db_field.klass != new_klass:
            db_field.klass = new_klass
            update_fields.append("klass")
        if db_field.order != no:
            db_field.order = no
            update_fields.append("order")
        if update_fields:
            db_field.save(update_fields=update_fields)

        # Try to record the form's initial as the system-wide default value
        form_field_value = form_field.initial
        try:
            json.dumps(form_field_value)
        except TypeError:
            if not created:
                db_field.delete()
            continue

        if created:
            FormFieldDefaultValue.objects.get_or_create(
                parent=form_repr, field=db_field, user=None,
                defaults={"value": form_field_value},
            )

        if user is not None:
            FormFieldDefaultValue.objects.get_or_create(
                parent=form_repr, field=db_field, user=user,
                defaults={"value": form_field_value},
            )


def update_form_db_repr(form_instance, form_repr, user=None):
    """Update DB representation of a form. Idempotent and race-safe."""
    try:
        with transaction.atomic():
            _do_update(form_instance, form_repr, user=user)
    except IntegrityError:
        # Concurrent caller raced us; their write succeeded — ours is not needed.
        logger.debug("update_form_db_repr: lost a race for %s; refreshing", form_repr.full_name)
        form_repr.refresh_from_db()


def _snapshot_is_fresh(form_full_name: str) -> bool:
    last = _LAST_SNAPSHOT.get(form_full_name)
    return last is not None and (time.monotonic() - last) < SNAPSHOT_TTL_SECONDS


def _mark_snapshot_fresh(form_full_name: str) -> None:
    _LAST_SNAPSHOT[form_full_name] = time.monotonic()


@transaction.atomic
def get_form_defaults(form_instance, label=None, user=None, update_db_repr=True):
    fn = full_name(form_instance)

    from formdefaults.models import FormRepresentation

    form_repr, _ = FormRepresentation.objects.get_or_create(
        full_name=fn, defaults={"label": label or fn},
    )

    if update_db_repr:
        if label is not None and form_repr.label != label:
            form_repr.label = label
            form_repr.save(update_fields=["label"])
        if not _snapshot_is_fresh(fn):
            update_form_db_repr(form_instance, form_repr, user=None)
            _mark_snapshot_fresh(fn)

    values = {
        qs["field__name"]: qs["value"]
        for qs in form_repr.values_set.filter(user=None)
        .select_related("field__name")
        .values("field__name", "value")
    }

    if user is not None:
        user_values = {
            qs["field__name"]: qs["value"]
            for qs in form_repr.values_set.filter(user=user)
            .select_related("field__name")
            .values("field__name", "value")
        }
        values.update(user_values)

    values.update({
        "formdefaults_pre_html": form_repr.html_before,
        "formdefaults_post_html": form_repr.html_after,
    })
    return values
```

- [ ] **Step 4: Run new test + full suite**

```bash
.venv/bin/pytest tests/test_core.py -v
.venv/bin/pytest -q
```

Expected: PASS for the new test and all existing tests.

- [ ] **Step 5: Commit**

```bash
git add src/formdefaults/core.py tests/test_core.py
git commit -m "fix(core): swallow IntegrityError on concurrent snapshot, add freshness cache"
```

---

## Task 5: `registry.py` — `register_form` decorator + iterator

**Files:**
- Create: `src/formdefaults/registry.py`
- Create: `tests/test_register.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_register.py`:

```python
import pytest
from django import forms
from django.test import override_settings

from formdefaults.registry import _REGISTRY, iter_registered_forms, register_form


@pytest.fixture(autouse=True)
def clear_registry():
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


def test_register_form_with_label_kwarg():
    @register_form(label="Hello")
    class F(forms.Form):
        x = forms.IntegerField()

    entries = list(iter_registered_forms())
    assert len(entries) == 1
    assert entries[0].form_class is F
    assert entries[0].label == "Hello"


def test_register_form_no_args():
    @register_form
    class F(forms.Form):
        x = forms.IntegerField()

    entries = list(iter_registered_forms())
    assert entries[0].form_class is F
    assert entries[0].label is None


def test_iter_includes_settings_path():
    with override_settings(FORMDEFAULTS_FORMS=["tests.test_register.SettingForm"]):
        entries = list(iter_registered_forms())
    assert any(e.form_class is SettingForm for e in entries)
    setting_entry = next(e for e in entries if e.form_class is SettingForm)
    assert setting_entry.label == "From setting"


def test_iter_warns_on_bad_setting_path(caplog):
    with override_settings(FORMDEFAULTS_FORMS=["nonexistent.module.Form"]):
        entries = list(iter_registered_forms())
    assert all(e.form_class.__module__ != "nonexistent.module" for e in entries)
    assert any("cannot import" in m for m in caplog.messages)


def test_iter_dedupe_decorator_wins():
    @register_form(label="From decorator")
    class DupForm(forms.Form):
        x = forms.IntegerField()

    with override_settings(
        FORMDEFAULTS_FORMS=[f"{DupForm.__module__}.DupForm"]
    ):
        entries = list(iter_registered_forms())

    matches = [e for e in entries if e.form_class is DupForm]
    assert len(matches) == 1
    assert matches[0].label == "From decorator"


class SettingForm(forms.Form):
    """Used by test_iter_includes_settings_path."""
    formdefaults_label = "From setting"
    y = forms.CharField()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_register.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'formdefaults.registry'`.

- [ ] **Step 3: Create `registry.py`**

Create `src/formdefaults/registry.py`:

```python
import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Entry:
    form_class: type
    label: str | None


_REGISTRY: dict[str, _Entry] = {}


def _full_name(form_class) -> str:
    return f"{form_class.__module__}.{form_class.__name__}"


def register_form(label=None):
    """Register a Django Form class for pre-snapshot at startup.

    Usage:
        @register_form
        class MyForm(forms.Form): ...

        @register_form(label="My pretty form")
        class MyForm(forms.Form): ...
    """
    def decorator(form_class):
        _REGISTRY[_full_name(form_class)] = _Entry(form_class, label_kw)
        return form_class

    # Distinguish @register_form vs @register_form(label=...)
    if isinstance(label, type):
        cls = label
        label_kw = None
        return decorator(cls)
    label_kw = label
    return decorator


def iter_registered_forms():
    """Yield _Entry rows from the in-memory registry, then from FORMDEFAULTS_FORMS,
    deduplicated by FQN (decorator wins)."""
    yielded = set()
    for fqn, entry in _REGISTRY.items():
        yielded.add(fqn)
        yield entry

    for dotted in getattr(settings, "FORMDEFAULTS_FORMS", []):
        if dotted in yielded:
            continue
        try:
            cls = import_string(dotted)
        except (ImportError, AttributeError):
            logger.warning("FORMDEFAULTS_FORMS: cannot import %r", dotted)
            continue
        yielded.add(dotted)
        yield _Entry(cls, getattr(cls, "formdefaults_label", None))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_register.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/formdefaults/registry.py tests/test_register.py
git commit -m "feat(registry): add register_form decorator and iter_registered_forms"
```

---

## Task 6: `signals.py` — `post_migrate` snapshot handler

**Files:**
- Create: `src/formdefaults/signals.py`
- Create: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_signals.py`:

```python
import pytest
from django import forms

from formdefaults.models import FormRepresentation
from formdefaults.registry import _REGISTRY, register_form
from formdefaults.signals import snapshot_registered_forms


class _Sender:
    name = "formdefaults"


@pytest.fixture(autouse=True)
def clear_registry():
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


@pytest.mark.django_db
def test_post_migrate_snapshots_decorated_form():
    @register_form(label="Snap1")
    class SnapForm(forms.Form):
        a = forms.IntegerField(initial=42)
        b = forms.CharField(initial="hi")

    snapshot_registered_forms(sender=_Sender)

    fr = FormRepresentation.objects.get(
        full_name=f"{SnapForm.__module__}.SnapForm"
    )
    assert fr.label == "Snap1"
    assert fr.pre_registered is True
    assert fr.fields_set.count() == 2


@pytest.mark.django_db
def test_post_migrate_skips_non_formdefaults_sender():
    @register_form
    class SkipForm(forms.Form):
        x = forms.IntegerField()

    class _OtherSender:
        name = "auth"

    snapshot_registered_forms(sender=_OtherSender)
    assert not FormRepresentation.objects.filter(
        full_name__endswith="SkipForm"
    ).exists()


@pytest.mark.django_db
def test_post_migrate_idempotent():
    @register_form
    class IdemForm(forms.Form):
        x = forms.IntegerField()

    snapshot_registered_forms(sender=_Sender)
    snapshot_registered_forms(sender=_Sender)

    fr = FormRepresentation.objects.get(full_name__endswith="IdemForm")
    assert fr.fields_set.count() == 1


@pytest.mark.django_db
def test_post_migrate_field_disappears():
    @register_form
    class ShrinkForm(forms.Form):
        a = forms.IntegerField()
        b = forms.CharField()

    snapshot_registered_forms(sender=_Sender)
    fr = FormRepresentation.objects.get(full_name__endswith="ShrinkForm")
    assert fr.fields_set.count() == 2

    # Mutate class to drop "b"
    del ShrinkForm.base_fields["b"]
    snapshot_registered_forms(sender=_Sender)

    fr.refresh_from_db()
    assert fr.fields_set.count() == 1
    assert fr.fields_set.first().name == "a"


@pytest.mark.django_db
def test_post_migrate_skips_form_needing_args(caplog):
    @register_form
    class NeedsArgsForm(forms.Form):
        def __init__(self, required_arg, **kwargs):
            super().__init__(**kwargs)

    snapshot_registered_forms(sender=_Sender)
    assert not FormRepresentation.objects.filter(
        full_name__endswith="NeedsArgsForm"
    ).exists()
    assert any("Cannot instantiate" in m for m in caplog.messages)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_signals.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'formdefaults.signals'`.

- [ ] **Step 3: Create `signals.py`**

Create `src/formdefaults/signals.py`:

```python
import logging
from importlib import import_module

from django.apps import apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from formdefaults.core import update_form_db_repr
from formdefaults.models import FormRepresentation
from formdefaults.registry import iter_registered_forms
from formdefaults.util import full_name

logger = logging.getLogger(__name__)


def autodiscover_formdefaults():
    """Import `<app>.forms` for each installed app, so that any
    @register_form decorators in those modules execute."""
    for app_config in apps.get_app_configs():
        try:
            import_module(f"{app_config.name}.forms")
        except ImportError:
            continue


@receiver(post_migrate)
def snapshot_registered_forms(sender, **kwargs):
    if getattr(sender, "name", None) != "formdefaults":
        return

    autodiscover_formdefaults()

    for entry in iter_registered_forms():
        try:
            instance = entry.form_class()
        except TypeError:
            logger.warning(
                "Cannot instantiate %s without args; skipping snapshot",
                entry.form_class,
            )
            continue

        form_repr, created = FormRepresentation.objects.get_or_create(
            full_name=full_name(instance),
            defaults={
                "label": entry.label or entry.form_class.__name__,
                "pre_registered": True,
            },
        )
        update_fields = []
        if not form_repr.pre_registered:
            form_repr.pre_registered = True
            update_fields.append("pre_registered")
        if entry.label and form_repr.label != entry.label:
            form_repr.label = entry.label
            update_fields.append("label")
        if update_fields:
            form_repr.save(update_fields=update_fields)

        update_form_db_repr(instance, form_repr, user=None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_signals.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/formdefaults/signals.py tests/test_signals.py
git commit -m "feat(signals): post_migrate snapshot of registered forms + autodiscover"
```

---

## Task 7: Wire signals in `apps.py` and re-export `register_form`

**Files:**
- Modify: `src/formdefaults/apps.py`
- Modify: `src/formdefaults/__init__.py`

- [ ] **Step 1: Edit `apps.py`**

Edit `src/formdefaults/apps.py`:

```python
from django.apps import AppConfig


class FormdefaultsConfig(AppConfig):
    name = "formdefaults"
    verbose_name = "Formularze - wartości domyślne"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        # Connect post_migrate handler.
        from formdefaults import signals  # noqa: F401
```

- [ ] **Step 2: Re-export `register_form` from package**

Edit `src/formdefaults/__init__.py` to be:

```python
from formdefaults.registry import register_form

__all__ = ["register_form"]
```

- [ ] **Step 3: Verify all tests still pass**

```bash
.venv/bin/pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/formdefaults/apps.py src/formdefaults/__init__.py
git commit -m "feat: wire post_migrate signal in AppConfig.ready, re-export register_form"
```

---

## Task 8: Popup edit — `forms.py` with `build_user_defaults_form`

**Files:**
- Create: `src/formdefaults/forms.py`
- Create: `tests/test_user_edit_view.py` (will grow in Tasks 9 and 10)

- [ ] **Step 1: Write the failing test**

Create `tests/test_user_edit_view.py`:

```python
import pytest
from django import forms
from django.contrib.auth import get_user_model

from formdefaults.core import update_form_db_repr
from formdefaults.forms import build_user_defaults_form
from formdefaults.models import FormFieldDefaultValue, FormRepresentation
from formdefaults.util import full_name


class DemoForm(forms.Form):
    n = forms.IntegerField(label="Number", initial=10)
    txt = forms.CharField(label="Text", initial="hi")


@pytest.fixture
def demo_form_repr(db):
    instance = DemoForm()
    fr, _ = FormRepresentation.objects.get_or_create(full_name=full_name(instance))
    update_form_db_repr(instance, fr)
    return fr


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="u", password="p")


@pytest.mark.django_db
def test_build_form_returns_user_initial(demo_form_repr, user):
    field_n = demo_form_repr.fields_set.get(name="n")
    FormFieldDefaultValue.objects.create(
        parent=demo_form_repr, field=field_n, user=user, value=99
    )
    f = build_user_defaults_form(demo_form_repr, user=user)
    assert f.fields["n"].initial == 99
    assert f.fields["txt"].initial is None


@pytest.mark.django_db
def test_build_form_save_creates_override(demo_form_repr, user):
    f = build_user_defaults_form(demo_form_repr, user=user, data={"n": "55", "txt": ""})
    assert f.is_valid(), f.errors
    f.save()

    field_n = demo_form_repr.fields_set.get(name="n")
    assert FormFieldDefaultValue.objects.filter(
        parent=demo_form_repr, field=field_n, user=user
    ).count() == 1


@pytest.mark.django_db
def test_build_form_save_idempotent(demo_form_repr, user):
    f1 = build_user_defaults_form(demo_form_repr, user=user, data={"n": "55", "txt": ""})
    f1.is_valid(); f1.save()
    f2 = build_user_defaults_form(demo_form_repr, user=user, data={"n": "66", "txt": ""})
    f2.is_valid(); f2.save()

    field_n = demo_form_repr.fields_set.get(name="n")
    rows = FormFieldDefaultValue.objects.filter(
        parent=demo_form_repr, field=field_n, user=user
    )
    assert rows.count() == 1
    assert rows.first().value == 66


@pytest.mark.django_db
def test_build_form_save_empty_deletes_override(demo_form_repr, user):
    f1 = build_user_defaults_form(demo_form_repr, user=user, data={"n": "55", "txt": ""})
    f1.is_valid(); f1.save()
    field_n = demo_form_repr.fields_set.get(name="n")
    assert FormFieldDefaultValue.objects.filter(field=field_n, user=user).exists()

    f2 = build_user_defaults_form(demo_form_repr, user=user, data={"n": "", "txt": ""})
    f2.is_valid(); f2.save()
    assert not FormFieldDefaultValue.objects.filter(field=field_n, user=user).exists()


@pytest.mark.django_db
def test_build_form_invalid_value(demo_form_repr, user):
    f = build_user_defaults_form(demo_form_repr, user=user, data={"n": "not-a-number", "txt": ""})
    assert not f.is_valid()
    assert "n" in f.errors
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_user_edit_view.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'formdefaults.forms'`.

- [ ] **Step 3: Create `forms.py`**

Create `src/formdefaults/forms.py`:

```python
import copy
import datetime
import json

from django import forms

from formdefaults.models import FormFieldDefaultValue


def _serialize(value):
    """Turn a cleaned form-field value into a JSON-storable Python value.

    Covers the common Django field types that `core.update_form_db_repr`
    initially serialises with `json.dumps`. For unsupported types, falls
    back to `str(value)` so the override is at least observable; the user
    will see a string in the next render and can correct it.
    """
    if value is None or isinstance(value, (bool, int, float, str, list, dict)):
        return value
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if hasattr(value, "pk"):  # ModelChoiceField etc.
        return value.pk
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


class _UserDefaultsForm(forms.Form):
    """Built dynamically by `build_user_defaults_form`; carries `_form_repr`
    and `_user` for `save()`."""

    _form_repr = None
    _user = None

    def save(self):
        for db_field in self._form_repr.fields_set.all():
            value = self.cleaned_data.get(db_field.name)
            empty = value in (None, "") or value == [] or value == {}
            if empty:
                FormFieldDefaultValue.objects.filter(
                    field=db_field, user=self._user
                ).delete()
                continue
            FormFieldDefaultValue.objects.update_or_create(
                parent=self._form_repr,
                field=db_field,
                user=self._user,
                defaults={"value": _serialize(value)},
            )


def build_user_defaults_form(form_repr, user, data=None):
    """Return a Form subclass instance whose fields are clones of the original
    form's fields, with `required=False` and `initial` loaded from existing
    user overrides. Calling `.save()` upserts overrides per field."""
    form_class = form_repr.get_form_class()
    if form_class is None:
        raise ValueError(f"Cannot resolve form class for {form_repr.full_name}")

    template = form_class()
    user_overrides = {
        v.field.name: v.value
        for v in form_repr.values_set.filter(user=user).select_related("field")
    }

    field_defs = {}
    for db_field in form_repr.fields_set.all():
        original = template.fields.get(db_field.name)
        if original is None:
            continue
        cloned = copy.deepcopy(original)
        cloned.required = False
        cloned.label = db_field.label or db_field.name
        cloned.initial = user_overrides.get(db_field.name)
        field_defs[db_field.name] = cloned

    Klass = type("UserDefaultsForm", (_UserDefaultsForm,), field_defs)
    instance = Klass(data=data)
    instance._form_repr = form_repr
    instance._user = user
    return instance
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_user_edit_view.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/formdefaults/forms.py tests/test_user_edit_view.py
git commit -m "feat(forms): build_user_defaults_form for per-user override editing"
```

---

## Task 9: Popup edit — `views.py` + `urls.py`

**Files:**
- Create: `src/formdefaults/views.py`
- Create: `src/formdefaults/urls.py`
- Modify: `tests/settings.py` (add `ROOT_URLCONF` + `MIDDLEWARE` for view tests)
- Modify: `tests/test_user_edit_view.py`

- [ ] **Step 1: Patch `tests/settings.py` to support view tests**

Replace `tests/settings.py` content with:

```python
"""Minimal Django settings for the django-formdefaults test suite."""
from __future__ import annotations

SECRET_KEY = "django-formdefaults-test-key-not-secret"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "formdefaults",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "django.template.context_processors.request",
        ],
    },
}]

STATIC_URL = "/static/"
LOGIN_URL = "/login/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- [ ] **Step 2: Create `tests/urls.py`**

Create `tests/urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    path("formdefaults/", include("formdefaults.urls")),
]
```

- [ ] **Step 3: Append failing tests for the view**

Append to `tests/test_user_edit_view.py`:

```python
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_view_anonymous_redirected(demo_form_repr):
    c = Client()
    url = reverse("formdefaults:user-edit", args=[demo_form_repr.full_name])
    resp = c.get(url)
    assert resp.status_code == 302
    assert "/login/" in resp["Location"]


@pytest.mark.django_db
def test_view_get_returns_fragment(demo_form_repr, user):
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=[demo_form_repr.full_name])
    resp = c.get(url)
    assert resp.status_code == 200
    assert b'name="n"' in resp.content


@pytest.mark.django_db
def test_view_post_saves(demo_form_repr, user):
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "77", "txt": ""})
    assert resp.status_code == 200

    field_n = demo_form_repr.fields_set.get(name="n")
    assert FormFieldDefaultValue.objects.filter(
        parent=demo_form_repr, field=field_n, user=user
    ).first().value == 77


@pytest.mark.django_db
def test_view_post_invalid_returns_400(demo_form_repr, user):
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "not-a-number", "txt": ""})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_view_unknown_form_returns_404(user):
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=["nonexistent.Form"])
    resp = c.get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_view_user_data_in_post_is_ignored(demo_form_repr, user):
    """Ensure that submitting user=<other_user_id> in POST data does NOT
    cause writes against another user's overrides."""
    other = get_user_model().objects.create_user(username="other", password="p")
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "77", "txt": "", "user": str(other.id)})
    assert resp.status_code == 200

    field_n = demo_form_repr.fields_set.get(name="n")
    assert not FormFieldDefaultValue.objects.filter(field=field_n, user=other).exists()
    assert FormFieldDefaultValue.objects.filter(field=field_n, user=user).exists()
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_user_edit_view.py -v
```

Expected: FAIL with `NoReverseMatch` / `ImportError` for `formdefaults.urls`.

- [ ] **Step 5: Create `views.py`**

Create `src/formdefaults/views.py`:

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from formdefaults.forms import build_user_defaults_form
from formdefaults.models import FormRepresentation


class UserFormDefaultsView(LoginRequiredMixin, View):
    template = "formdefaults/_modal_fragment.html"

    def get(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(form_repr, user=request.user)
        return render(request, self.template, {
            "form_repr": form_repr,
            "edit_form": edit_form,
            "saved": False,
        })

    def post(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(
            form_repr, user=request.user, data=request.POST
        )
        if edit_form.is_valid():
            edit_form.save()
            return render(request, self.template, {
                "form_repr": form_repr,
                "edit_form": edit_form,
                "saved": True,
            })
        return render(request, self.template, {
            "form_repr": form_repr,
            "edit_form": edit_form,
            "saved": False,
        }, status=400)
```

- [ ] **Step 6: Create `urls.py`**

Create `src/formdefaults/urls.py`:

```python
from django.urls import path

from formdefaults.views import UserFormDefaultsView

app_name = "formdefaults"

urlpatterns = [
    path(
        "edit/<path:form_full_name>/",
        UserFormDefaultsView.as_view(),
        name="user-edit",
    ),
]
```

(`<path:...>` lets dotted FQNs through without escaping concerns.)

- [ ] **Step 7: Create the modal template**

Create `src/formdefaults/templates/formdefaults/_modal_fragment.html`:

```django
<div class="fd-modal-backdrop">
  <div class="fd-modal" role="dialog" aria-modal="true">
    <button type="button" class="fd-modal-close" aria-label="Close">×</button>
    <h3>{{ form_repr.label }}</h3>
    {% if saved %}<p class="fd-saved">Zapisano.</p>{% endif %}
    <form method="post" data-fd-form>
      {% csrf_token %}
      {% include "formdefaults/_user_edit_form.html" with form=edit_form %}
      <button type="submit" class="fd-submit">Zapisz</button>
    </form>
  </div>
</div>
```

Create `src/formdefaults/templates/formdefaults/_user_edit_form.html`:

```django
{% for field in form %}
<div class="fd-field">
  <label for="{{ field.id_for_label }}">{{ field.label }}</label>
  {{ field }}
  {% if field.errors %}<div class="fd-errors">{{ field.errors }}</div>{% endif %}
</div>
{% endfor %}
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_user_edit_view.py -v
```

Expected: all 11 tests PASS (5 from Task 8 + 6 new).

- [ ] **Step 9: Commit**

```bash
git add src/formdefaults/views.py src/formdefaults/urls.py src/formdefaults/templates tests/settings.py tests/urls.py tests/test_user_edit_view.py
git commit -m "feat(views): UserFormDefaultsView + URLconf + modal template"
```

---

## Task 10: Template tag `{% formdefaults_button %}`

**Files:**
- Create: `src/formdefaults/templatetags/__init__.py`
- Create: `src/formdefaults/templatetags/formdefaults.py`
- Create: `src/formdefaults/templates/formdefaults/_button.html`
- Modify: `tests/test_user_edit_view.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_user_edit_view.py`:

```python
from django.template import Context, Template
from django.test import RequestFactory


@pytest.mark.django_db
def test_template_tag_renders_button_for_authed_user(demo_form_repr, user):
    rf = RequestFactory()
    request = rf.get("/")
    request.user = user
    template = Template(
        "{% load formdefaults %}{% formdefaults_button form %}"
    )
    rendered = template.render(Context({"request": request, "form": DemoForm()}))
    assert "fd-edit-btn" in rendered
    assert "demo_form_repr" not in rendered  # sanity
    assert demo_form_repr.full_name in rendered


@pytest.mark.django_db
def test_template_tag_renders_nothing_for_anonymous():
    from django.contrib.auth.models import AnonymousUser
    rf = RequestFactory()
    request = rf.get("/")
    request.user = AnonymousUser()
    template = Template(
        "{% load formdefaults %}{% formdefaults_button form %}"
    )
    rendered = template.render(Context({"request": request, "form": DemoForm()}))
    assert "fd-edit-btn" not in rendered
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_user_edit_view.py::test_template_tag_renders_button_for_authed_user tests/test_user_edit_view.py::test_template_tag_renders_nothing_for_anonymous -v
```

Expected: FAIL with `TemplateSyntaxError: 'formdefaults' is not a registered tag library`.

- [ ] **Step 3: Create the template tag library**

Create `src/formdefaults/templatetags/__init__.py` (empty file).

Create `src/formdefaults/templatetags/formdefaults.py`:

```python
from django import template
from django.urls import reverse

from formdefaults.util import full_name

register = template.Library()


@register.inclusion_tag("formdefaults/_button.html", takes_context=True)
def formdefaults_button(context, form):
    request = context.get("request")
    if request is None or not getattr(request.user, "is_authenticated", False):
        return {"show": False}
    fqn = full_name(form)
    return {
        "show": True,
        "url": reverse("formdefaults:user-edit", args=[fqn]),
        "form_full_name": fqn,
    }
```

- [ ] **Step 4: Create button template**

Create `src/formdefaults/templates/formdefaults/_button.html`:

```django
{% if show %}
<button type="button" class="fd-edit-btn" data-fd-url="{{ url }}">⚙ Moje wartości domyślne</button>
<div class="fd-modal-host" data-fd-for="{{ form_full_name }}" hidden></div>
{% endif %}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_user_edit_view.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/formdefaults/templatetags src/formdefaults/templates/formdefaults/_button.html tests/test_user_edit_view.py
git commit -m "feat(templatetags): {% formdefaults_button %}"
```

---

## Task 11: Static assets — `modal.js` and `modal.css`

**Files:**
- Create: `src/formdefaults/static/formdefaults/modal.js`
- Create: `src/formdefaults/static/formdefaults/modal.css`

(No test file — JS is exercised manually via `example_project/`. The endpoint contract is already covered by view tests.)

- [ ] **Step 1: Create `modal.js`**

Create `src/formdefaults/static/formdefaults/modal.js`:

```javascript
(function () {
  "use strict";

  function findHost(button) {
    var sibling = button.parentElement && button.parentElement.querySelector(".fd-modal-host");
    return sibling || document.querySelector(".fd-modal-host");
  }

  function open(host, html) {
    host.innerHTML = html;
    host.hidden = false;
  }

  function close(host) {
    host.innerHTML = "";
    host.hidden = true;
  }

  function csrfFromCookie() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  document.addEventListener("click", async function (e) {
    var btn = e.target.closest && e.target.closest(".fd-edit-btn");
    if (btn) {
      var url = btn.dataset.fdUrl;
      var host = findHost(btn);
      if (!host) return;
      host.dataset.fdUrl = url;
      var resp = await fetch(url, { credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" } });
      open(host, await resp.text());
      return;
    }
    var closeEl = e.target.closest && e.target.closest(".fd-modal-close");
    if (closeEl) {
      var host2 = closeEl.closest(".fd-modal-host");
      if (host2) close(host2);
      return;
    }
    if (e.target.classList && e.target.classList.contains("fd-modal-backdrop")) {
      var host3 = e.target.closest(".fd-modal-host");
      if (host3) close(host3);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".fd-modal-host:not([hidden])").forEach(close);
    }
  });

  document.addEventListener("submit", async function (e) {
    var form = e.target.closest && e.target.closest("[data-fd-form]");
    if (!form) return;
    e.preventDefault();
    var host = form.closest(".fd-modal-host");
    if (!host) return;
    var url = host.dataset.fdUrl;
    var fd = new FormData(form);
    var resp = await fetch(url, {
      method: "POST", body: fd, credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfFromCookie() },
    });
    host.innerHTML = await resp.text();
  });
})();
```

- [ ] **Step 2: Create `modal.css`**

Create `src/formdefaults/static/formdefaults/modal.css`:

```css
.fd-modal-host[hidden] { display: none; }
.fd-modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}
.fd-modal {
  background: #fff;
  padding: 1.5em;
  border-radius: 6px;
  min-width: 320px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: auto;
  position: relative;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}
.fd-modal-close {
  position: absolute; top: 0.25em; right: 0.5em;
  background: none; border: none; font-size: 1.6em; cursor: pointer; color: #555;
}
.fd-modal h3 { margin: 0 0 0.75em 0; font-size: 1.15em; }
.fd-field { margin-bottom: 0.75em; }
.fd-field label { display: block; font-weight: 600; margin-bottom: 0.25em; }
.fd-field input, .fd-field select, .fd-field textarea { width: 100%; box-sizing: border-box; }
.fd-errors { color: #c00; font-size: 0.9em; margin-top: 0.25em; }
.fd-saved { color: #060; margin: 0 0 0.75em 0; }
.fd-submit { padding: 0.4em 1em; }
.fd-edit-btn { font-size: 0.9em; cursor: pointer; }
```

- [ ] **Step 3: Commit**

```bash
git add src/formdefaults/static
git commit -m "feat(static): vanilla JS modal + minimal CSS"
```

---

## Task 12: Example project — Django scaffold

**Files:**
- Create: `example_project/manage.py`
- Create: `example_project/example_project/__init__.py`
- Create: `example_project/example_project/settings.py`
- Create: `example_project/example_project/urls.py`
- Create: `example_project/example_project/wsgi.py`
- Modify: `.gitignore`

- [ ] **Step 1: `manage.py`**

Create `example_project/manage.py`:

```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
```

- [ ] **Step 2: `__init__.py`**

Create `example_project/example_project/__init__.py` (empty file).

- [ ] **Step 3: `settings.py`**

Create `example_project/example_project/settings.py`:

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "demo-not-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "formdefaults",
    "demo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "example_project.urls"
WSGI_APPLICATION = "example_project.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATIC_URL = "/static/"
LOGIN_URL = "/admin/login/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Pre-register UserSettingsForm via the setting path (decorator path is in
# demo/forms.py, ad-hoc path is the SearchForm).
FORMDEFAULTS_FORMS = ["demo.forms.UserSettingsForm"]
```

- [ ] **Step 4: `urls.py`**

Create `example_project/example_project/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("formdefaults/", include("formdefaults.urls")),
    path("", include("demo.urls")),
]
```

- [ ] **Step 5: `wsgi.py`**

Create `example_project/example_project/wsgi.py`:

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
application = get_wsgi_application()
```

- [ ] **Step 6: Update `.gitignore`**

Append to `/home/mpasternak/Programowanie/django-formdefaults/.gitignore`:

```
example_project/db.sqlite3
```

- [ ] **Step 7: Verify scaffold runs**

```bash
cd example_project
PYTHONPATH=$(pwd):$(pwd)/.. ../.venv/bin/python manage.py check
cd ..
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 8: Commit**

```bash
git add example_project .gitignore
git commit -m "feat(example): django scaffold for example_project"
```

---

## Task 13: Example project — `demo` app with three forms

**Files:**
- Create: `example_project/demo/__init__.py`
- Create: `example_project/demo/apps.py`
- Create: `example_project/demo/forms.py`
- Create: `example_project/demo/views.py`
- Create: `example_project/demo/urls.py`
- Create: `example_project/demo/templates/base.html`
- Create: `example_project/demo/templates/demo/report.html`
- Create: `example_project/demo/templates/demo/settings.html`
- Create: `example_project/demo/templates/demo/search.html`

- [ ] **Step 1: `apps.py`**

Create `example_project/demo/__init__.py` (empty).

Create `example_project/demo/apps.py`:

```python
from django.apps import AppConfig


class DemoConfig(AppConfig):
    name = "demo"
    default_auto_field = "django.db.models.BigAutoField"
```

- [ ] **Step 2: `forms.py` — three forms, three registration paths**

Create `example_project/demo/forms.py`:

```python
"""Three demo forms, each illustrating a different registration path.

1. MonthlyReportForm — decorator path (@register_form).
2. UserSettingsForm  — setting path (FORMDEFAULTS_FORMS in settings.py).
3. SearchForm        — ad-hoc path (no registration; snapshot on first render).
"""
import datetime

from django import forms

from formdefaults import register_form


@register_form(label="Raport miesięczny")
class MonthlyReportForm(forms.Form):
    year = forms.IntegerField(label="Rok", initial=datetime.date.today().year)
    month = forms.ChoiceField(
        label="Miesiąc",
        choices=[(i, f"{i:02d}") for i in range(1, 13)],
        initial=datetime.date.today().month,
    )
    include_inactive = forms.BooleanField(label="Uwzględnij nieaktywnych", required=False, initial=False)


class UserSettingsForm(forms.Form):
    formdefaults_label = "Ustawienia użytkownika"

    notify_email = forms.BooleanField(label="Powiadomienia e-mail", required=False, initial=True)
    items_per_page = forms.IntegerField(label="Pozycji na stronę", initial=25, min_value=5, max_value=200)
    theme = forms.ChoiceField(
        label="Motyw",
        choices=[("light", "Jasny"), ("dark", "Ciemny"), ("system", "Systemowy")],
        initial="system",
    )


class SearchForm(forms.Form):
    q = forms.CharField(label="Szukaj", required=False, initial="")
    sort_by = forms.ChoiceField(
        label="Sortuj wg",
        choices=[("name", "Nazwa"), ("date", "Data")],
        initial="name",
    )
```

- [ ] **Step 3: `views.py`**

Create `example_project/demo/views.py`:

```python
from django.shortcuts import render
from django.views.generic.edit import FormView

from formdefaults.core import get_form_defaults
from formdefaults.helpers import FormDefaultsMixin

from demo.forms import MonthlyReportForm, SearchForm, UserSettingsForm


class MonthlyReportView(FormDefaultsMixin, FormView):
    form_class = MonthlyReportForm
    template_name = "demo/report.html"
    title = "Raport miesięczny"

    def form_valid(self, form):
        return render(self.request, "demo/report.html",
                      {"form": form, "submitted": form.cleaned_data})


class UserSettingsView(FormDefaultsMixin, FormView):
    form_class = UserSettingsForm
    template_name = "demo/settings.html"
    title = "Ustawienia użytkownika"

    def form_valid(self, form):
        return render(self.request, "demo/settings.html",
                      {"form": form, "submitted": form.cleaned_data})


def search_view(request):
    """Function-based view: ad-hoc path. No registration; snapshot happens
    on first render here."""
    initial = get_form_defaults(SearchForm(), label="Wyszukiwarka",
                                user=request.user if request.user.is_authenticated else None)
    if request.method == "POST":
        form = SearchForm(request.POST)
        submitted = form.cleaned_data if form.is_valid() else None
    else:
        form = SearchForm(initial=initial)
        submitted = None
    return render(request, "demo/search.html", {"form": form, "submitted": submitted})
```

- [ ] **Step 4: `urls.py`**

Create `example_project/demo/urls.py`:

```python
from django.urls import path

from demo.views import MonthlyReportView, UserSettingsView, search_view

app_name = "demo"

urlpatterns = [
    path("", MonthlyReportView.as_view(), name="report"),
    path("settings/", UserSettingsView.as_view(), name="settings"),
    path("search/", search_view, name="search"),
]
```

- [ ] **Step 5: Templates**

Create `example_project/demo/templates/base.html`:

```django
{% load static %}
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>{% block title %}django-formdefaults demo{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'formdefaults/modal.css' %}">
  <style>
    body { font-family: sans-serif; max-width: 720px; margin: 2em auto; padding: 0 1em; }
    nav a { margin-right: 1em; }
    .form-card { border: 1px solid #ddd; padding: 1em; border-radius: 6px; }
    .form-card .actions { display: flex; gap: 1em; align-items: center; margin-top: 0.5em; }
  </style>
</head>
<body>
  <nav>
    <a href="{% url 'demo:report' %}">Raport</a>
    <a href="{% url 'demo:settings' %}">Ustawienia</a>
    <a href="{% url 'demo:search' %}">Szukaj</a>
    <a href="/admin/">Admin</a>
  </nav>
  <hr>
  {% block content %}{% endblock %}
  <script src="{% static 'formdefaults/modal.js' %}" defer></script>
</body>
</html>
```

Create `example_project/demo/templates/demo/report.html`:

```django
{% extends "base.html" %}
{% load formdefaults %}
{% block title %}Raport miesięczny{% endblock %}
{% block content %}
<h1>Raport miesięczny</h1>
<p><em>Rejestracja: dekorator <code>@register_form</code> w <code>demo/forms.py</code>.</em></p>
<div class="form-card">
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <div class="actions">
      <button type="submit">Generuj</button>
      {% formdefaults_button form %}
    </div>
  </form>
</div>
{% if submitted %}<pre>{{ submitted }}</pre>{% endif %}
{% endblock %}
```

Create `example_project/demo/templates/demo/settings.html`:

```django
{% extends "base.html" %}
{% load formdefaults %}
{% block title %}Ustawienia{% endblock %}
{% block content %}
<h1>Ustawienia użytkownika</h1>
<p><em>Rejestracja: setting <code>FORMDEFAULTS_FORMS</code> w <code>example_project/settings.py</code>.</em></p>
<div class="form-card">
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <div class="actions">
      <button type="submit">Zapisz</button>
      {% formdefaults_button form %}
    </div>
  </form>
</div>
{% if submitted %}<pre>{{ submitted }}</pre>{% endif %}
{% endblock %}
```

Create `example_project/demo/templates/demo/search.html`:

```django
{% extends "base.html" %}
{% load formdefaults %}
{% block title %}Szukaj{% endblock %}
{% block content %}
<h1>Szukaj</h1>
<p><em>Rejestracja: <strong>brak</strong> — snapshot powstaje przy pierwszym renderze.</em></p>
<div class="form-card">
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <div class="actions">
      <button type="submit">Szukaj</button>
      {% formdefaults_button form %}
    </div>
  </form>
</div>
{% if submitted %}<pre>{{ submitted }}</pre>{% endif %}
{% endblock %}
```

- [ ] **Step 6: Migrate + verify boot**

```bash
cd example_project
PYTHONPATH=$(pwd):$(pwd)/.. DJANGO_SETTINGS_MODULE=example_project.settings ../.venv/bin/python manage.py migrate
PYTHONPATH=$(pwd):$(pwd)/.. ../.venv/bin/python manage.py check
cd ..
```

Expected: migrations run cleanly, check passes.

- [ ] **Step 7: Commit**

```bash
git add example_project/demo
git commit -m "feat(example): demo app with three registration paths"
```

---

## Task 14: Test for example_project end-to-end

**Files:**
- Create: `tests/example_settings.py`
- Create: `tests/test_example_project.py`

- [ ] **Step 1: Create `tests/example_settings.py`**

Create `tests/example_settings.py`:

```python
"""Test settings module that boots example_project's demo app under pytest."""
import sys
from pathlib import Path

# Add example_project/ to path so `import demo` and `import example_project`
# both work.
EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example_project"
sys.path.insert(0, str(EXAMPLE_DIR))

from example_project.settings import *  # noqa: F401, F403, E402
from example_project.settings import INSTALLED_APPS as _APPS  # noqa: E402

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
DEBUG = False
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_example_project.py`:

```python
import pytest
from django.test import Client, override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


@override_settings()  # placeholder to attach overrides per-test
def _noop():
    pass


@pytest.fixture(scope="module")
def example_settings():
    """Switch to example_settings module-wide for these tests."""
    from django.conf import settings
    from django.test.utils import override_settings as os_

    # The simplest path: import the example_settings module and copy.
    import importlib
    es = importlib.import_module("tests.example_settings")
    o = os_(
        INSTALLED_APPS=es.INSTALLED_APPS,
        ROOT_URLCONF=es.ROOT_URLCONF,
        TEMPLATES=es.TEMPLATES,
        FORMDEFAULTS_FORMS=es.FORMDEFAULTS_FORMS,
        MIDDLEWARE=es.MIDDLEWARE,
    )
    o.enable()
    yield
    o.disable()


def test_example_check_passes(example_settings):
    """`manage.py check` equivalent: Django's system_check returns no errors."""
    from django.core.checks import run_checks
    errors = [e for e in run_checks() if e.is_serious()]
    assert errors == []


def test_search_view_renders(example_settings):
    """Ad-hoc path: GET /search/ returns 200 and creates FormRepresentation."""
    from formdefaults.models import FormRepresentation
    c = Client()
    resp = c.get("/search/")
    assert resp.status_code == 200
    assert FormRepresentation.objects.filter(
        full_name="demo.forms.SearchForm"
    ).exists()


def test_post_migrate_pre_registers_decorator_form(example_settings):
    """post_migrate fires during DB setup, snapshotting MonthlyReportForm."""
    from formdefaults.models import FormRepresentation
    from formdefaults.signals import snapshot_registered_forms

    class _S:
        name = "formdefaults"

    snapshot_registered_forms(sender=_S)
    fr = FormRepresentation.objects.get(full_name="demo.forms.MonthlyReportForm")
    assert fr.pre_registered is True
    assert fr.label == "Raport miesięczny"
    assert fr.fields_set.count() == 3


def test_post_migrate_pre_registers_setting_form(example_settings):
    from formdefaults.models import FormRepresentation
    from formdefaults.signals import snapshot_registered_forms

    class _S:
        name = "formdefaults"

    snapshot_registered_forms(sender=_S)
    fr = FormRepresentation.objects.get(full_name="demo.forms.UserSettingsForm")
    assert fr.pre_registered is True
    assert fr.label == "Ustawienia użytkownika"
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/pytest tests/test_example_project.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/pytest -q
```

Expected: every test in the suite passes.

- [ ] **Step 5: Commit**

```bash
git add tests/example_settings.py tests/test_example_project.py
git commit -m "test(example): integration tests for example_project"
```

---

## Task 15: Admin tweak — surface `pre_registered`

**Files:**
- Modify: `src/formdefaults/admin.py`

- [ ] **Step 1: Edit admin**

Modify `src/formdefaults/admin.py`. Change `FormRepresentationAdmin` to:

```python
@admin.register(FormRepresentation)
class FormRepresentationAdmin(admin.ModelAdmin):
    list_display = ["label", "full_name", "pre_registered"]
    list_filter = ["pre_registered"]
    inlines = [FormFieldDefaultValueInline]
    readonly_fields = ["full_name", "pre_registered"]
    fields = ["label", "full_name", "pre_registered", "html_before", "html_after"]
```

- [ ] **Step 2: Verify all tests still pass**

```bash
.venv/bin/pytest -q
```

Expected: no regressions.

- [ ] **Step 3: Commit**

```bash
git add src/formdefaults/admin.py
git commit -m "feat(admin): surface pre_registered flag, make full_name readonly"
```

---

## Task 16: Packaging — include templates/static/templatetags in wheel

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Modify `pyproject.toml`. Replace the `[tool.hatch.build.targets.wheel]` section with:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/formdefaults"]

[tool.hatch.build.targets.wheel.force-include]
"src/formdefaults/templates" = "formdefaults/templates"
"src/formdefaults/static" = "formdefaults/static"
"src/formdefaults/templatetags" = "formdefaults/templatetags"
```

- [ ] **Step 2: Build wheel and verify contents**

```bash
.venv/bin/pip install --quiet build
.venv/bin/python -m build --wheel --outdir /tmp/fd-wheel
unzip -l /tmp/fd-wheel/django_formdefaults-*.whl | grep -E '(templates|static|templatetags)' | head -20
```

Expected: lines listing `formdefaults/templates/formdefaults/_button.html`, `_modal_fragment.html`, `_user_edit_form.html`, `formdefaults/static/formdefaults/modal.js`, `modal.css`, `formdefaults/templatetags/formdefaults.py`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: include templates/static/templatetags in wheel"
```

---

## Task 17: README rewrite — Idea, three paths, popup, example

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`**

Overwrite `README.md` with:

```markdown
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

1. **Builds or refreshes a representation of the form in the DB** — its set of
   fields, their order, types and labels, and a snapshot of `Form.initial`.
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

`/admin/formdefaults/formrepresentation/` — pick a form by label, then for each
field add or edit a `FormFieldDefaultValue` row with `User` empty.

### Per-user (popup next to the form)

In your template:

```django
{% load formdefaults static %}

<form method="post">
  {% csrf_token %}
  {{ form }}
  <button type="submit">Submit</button>
  {% formdefaults_button form %}
</form>

<script src="{% static 'formdefaults/modal.js' %}" defer></script>
<link rel="stylesheet" href="{% static 'formdefaults/modal.css' %}">
```

The button only renders for authenticated users. Clicking it opens a modal
with one input per form field, pre-filled with the user's existing overrides.
Empty input clears the override.

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
  unique constraint (field, user)
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

## Running the tests

```bash
pip install -e ".[test]"
pytest
```

Uses an in-memory SQLite database — no Postgres needed.

## License

MIT — see [LICENSE](LICENSE).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README — Idea, three registration paths, popup, example"
```

---

## Task 18: CHANGELOG entry for 0.2.0

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit CHANGELOG.md**

Replace the unreleased section / prepend new entry. Final content:

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-09

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
- Unique constraint on `FormFieldDefaultValue(field, user)` and index on
  `(parent, user)`.

### Fixed

- Race condition on first render of an unsnapshotted form when two requests
  hit at once (`update_form_db_repr` now wraps the body in `transaction.atomic`
  and swallows `IntegrityError` from concurrent inserts).

### Changed

- `FormRepresentationManager.get_or_create_for_instance` now seeds `label`
  with `full_name` so admin never sees an empty label.
- Per-process freshness cache in `core.get_form_defaults` skips redundant
  `update_form_db_repr` calls within a 60-second window.

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
```

- [ ] **Step 2: Bump version**

In `pyproject.toml` change `version = "0.1.0"` to `version = "0.2.0"`.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md pyproject.toml
git commit -m "chore: release 0.2.0"
```

---

## Task 19: Final verification

- [ ] **Step 1: Full test suite**

```bash
.venv/bin/pytest -v
```

Expected: every test passes (existing + new).

- [ ] **Step 2: Build wheel**

```bash
rm -rf dist build
.venv/bin/python -m build
ls dist/
```

Expected: `django_formdefaults-0.2.0-py3-none-any.whl` and `.tar.gz`.

- [ ] **Step 3: Verify wheel includes templates and static**

```bash
unzip -l dist/django_formdefaults-0.2.0-py3-none-any.whl | grep -E '(modal\.|_button|_modal_fragment|_user_edit_form|templatetags/formdefaults)'
```

Expected: at least 6 lines listing the templates, statics, and templatetag module.

- [ ] **Step 4: Smoke-test example_project**

```bash
cd example_project
PYTHONPATH=$(pwd):$(pwd)/.. ../.venv/bin/python manage.py migrate --run-syncdb
PYTHONPATH=$(pwd):$(pwd)/.. ../.venv/bin/python manage.py check
cd ..
```

Expected: clean migrate + check.

- [ ] **Step 5: Optional manual smoke test**

```bash
cd example_project
PYTHONPATH=$(pwd):$(pwd)/.. ../.venv/bin/python manage.py createsuperuser --noinput --username admin --email a@b.c || true
DJANGO_SUPERUSER_PASSWORD=admin PYTHONPATH=$(pwd):$(pwd)/.. ../.venv/bin/python manage.py runserver 8765
# Visit http://127.0.0.1:8765, exercise three forms, click "⚙ Moje wartości domyślne", verify modal opens, save, reload page, verify saved value comes back as initial.
```

Expected: forms render, modal opens, save+reload preserves the override.

---

## Self-review notes

- All spec sections (1–9) have at least one task: Idea/Architecture (Task 17 README), Data model (Tasks 2–3), Pre-registration (Tasks 5–7), Popup edit (Tasks 8–11), Example project (Tasks 12–13), Tests (Tasks 8, 9, 10, 14 + race test in Task 4), Build/packaging/README/CHANGELOG (Tasks 16–18), Out-of-scope items intentionally not covered.
- No "TBD" placeholders.
- `_serialize` helper in Task 8 is the only spec deviation: spec only mentioned "JSON-storable Python value", we implement the common-types fallback explicitly.
- Type/method names consistent: `register_form`, `iter_registered_forms`, `_REGISTRY`, `snapshot_registered_forms`, `autodiscover_formdefaults`, `build_user_defaults_form`, `UserFormDefaultsView`, `formdefaults_button`, `_LAST_SNAPSHOT`, `_snapshot_is_fresh`, `_mark_snapshot_fresh`. Used identically across tasks.
