import copy
import datetime
import json

from django import forms

from formdefaults.models import FormFieldDefaultValue


_OVERRIDE_PREFIX = "_override_"


def _serialize(value):
    """Turn a cleaned form-field value into a JSON-storable Python value.

    Covers the common Django field types whose `Form.initial` is JSON-able
    when snapshotted. For unsupported types, falls back to `str(value)`."""
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
    """Built dynamically by `build_user_defaults_form`. Carries `_form_repr`
    and `_user`. Companion checkboxes named `_override_<field_name>` decide
    whether `save()` upserts or deletes the per-user override."""

    _form_repr = None
    _user = None

    def field_pairs(self):
        """Yield (override_checkbox_bound_field, value_bound_field) tuples
        in the order of `form_repr.fields_set`. Used by the template to
        render checkbox + value side-by-side."""
        for db_field in self._form_repr.fields_set.all():
            override_name = _OVERRIDE_PREFIX + db_field.name
            if override_name in self.fields and db_field.name in self.fields:
                yield self[override_name], self[db_field.name]

    def save(self):
        for db_field in self._form_repr.fields_set.all():
            override_active = self.cleaned_data.get(
                _OVERRIDE_PREFIX + db_field.name, False
            )
            if not override_active:
                FormFieldDefaultValue.objects.filter(
                    field=db_field, user=self._user
                ).delete()
                continue
            value = self.cleaned_data.get(db_field.name)
            FormFieldDefaultValue.objects.update_or_create(
                parent=self._form_repr,
                field=db_field,
                user=self._user,
                defaults={"value": _serialize(value), "is_auto_snapshot": False},
            )


def build_user_defaults_form(form_repr, user, data=None):
    """Return a Form subclass instance whose fields are clones of the
    original form's fields, plus a companion `_override_<name>` checkbox
    per field. `.save()` upserts overrides only for fields whose checkbox
    was checked at submit time (auto-check JS in modal.js flips it on user
    edit)."""
    form_class = form_repr.get_form_class()
    if form_class is None:
        raise ValueError(f"Cannot resolve form class for {form_repr.full_name}")

    template = form_class()
    user_overrides = {
        v.field.name: v.value
        for v in form_repr.values_set.filter(user=user).select_related("field")
    }
    system_values = {
        v.field.name: v.value
        for v in form_repr.values_set.filter(user=None).select_related("field")
    }

    field_defs = {}
    for db_field in form_repr.fields_set.all():
        original = template.fields.get(db_field.name)
        if original is None:
            continue
        cloned = copy.deepcopy(original)
        cloned.required = False
        cloned.label = db_field.label or db_field.name

        has_override = db_field.name in user_overrides
        if has_override:
            cloned.initial = user_overrides[db_field.name]
        else:
            cloned.initial = system_values.get(db_field.name)
        field_defs[db_field.name] = cloned

        override_field = forms.BooleanField(
            required=False,
            initial=has_override,
            label="",
            widget=forms.CheckboxInput(attrs={"class": "fd-override-checkbox"}),
        )
        field_defs[_OVERRIDE_PREFIX + db_field.name] = override_field

    Klass = type("UserDefaultsForm", (_UserDefaultsForm,), field_defs)
    instance = Klass(data=data)
    instance._form_repr = form_repr
    instance._user = user
    return instance
