import copy
import datetime
import json

from django import forms

from formdefaults.models import FormFieldDefaultValue


def _serialize(value):
    """Turn a cleaned form-field value into a JSON-storable Python value.

    Covers the common Django field types whose `Form.initial` is JSON-able
    when snapshotted. For unsupported types, falls back to `str(value)` so
    the override is at least observable; the user will see a string in the
    next render and can correct it.
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
                defaults={"value": _serialize(value), "is_auto_snapshot": False},
            )


def build_user_defaults_form(form_repr, user, data=None):
    """Return a Form subclass instance whose fields are clones of the
    original form's fields, with `required=False` and `initial` loaded from
    existing user overrides. Calling `.save()` upserts overrides per field
    (or deletes the override when the input is empty)."""
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
