from unittest.mock import patch

import pytest
from django import forms
from django.db import IntegrityError

from formdefaults import core
from formdefaults.models import FormRepresentation
from formdefaults.util import full_name


class FormForTests(forms.Form):
    """Plain form used as a fixture target.

    Named without the leading ``Test`` prefix so pytest doesn't try to
    collect it as a test class.
    """

    fld = forms.CharField(label="Takietam", initial=123)


@pytest.fixture
def test_form():
    return FormForTests()


@pytest.fixture
def test_form_repr(test_form):
    return FormRepresentation.objects.get_or_create(full_name=full_name(test_form))[0]


@pytest.mark.django_db
def test_update_form_db_repr(test_form, test_form_repr, normal_django_user):
    core.update_form_db_repr(test_form, test_form_repr)
    assert test_form_repr.fields_set.count() == 1
    assert test_form_repr.values_set.count() == 1

    core.update_form_db_repr(test_form, test_form_repr, user=normal_django_user)
    assert test_form_repr.fields_set.count() == 1
    assert test_form_repr.values_set.count() == 2


@pytest.mark.django_db
def test_get_form_defaults(test_form):
    res = core.get_form_defaults(test_form)
    assert res["fld"] == 123


@pytest.mark.django_db
def test_get_form_defaults_change_label_form(test_form):
    core.get_form_defaults(test_form, "123")

    core.get_form_defaults(test_form, "456")

    form_repr = FormRepresentation.objects.get(full_name=full_name(test_form))
    assert form_repr.label == "456"


@pytest.mark.django_db
def test_get_form_defaults_change_label_field(test_form, test_form_repr):
    core.get_form_defaults(test_form, "123")
    test_form.fields["fld"].label = "456"

    # Force a re-snapshot — bypass the per-process freshness cache that would
    # otherwise skip the second call's DB-side reconciliation.
    core._LAST_SNAPSHOT.clear()
    core.get_form_defaults(test_form, "123")

    assert test_form_repr.fields_set.first().label == "456"


@pytest.mark.django_db
def test_get_form_defaults_undumpable_json(test_form, test_form_repr):
    core.get_form_defaults(test_form, "123")
    assert test_form_repr.fields_set.count() == 1
    assert test_form_repr.values_set.first().value == 123

    test_form.fields["fld"].initial = test_get_form_defaults_undumpable_json
    # Force a re-snapshot — bypass the per-process freshness cache.
    core._LAST_SNAPSHOT.clear()
    core.get_form_defaults(test_form, "123")
    assert test_form_repr.values_set.count() == 0


@pytest.mark.django_db
def test_get_form_defaults_with_user(test_form, test_form_repr, normal_django_user):
    res = core.get_form_defaults(test_form, user=normal_django_user)
    assert res["fld"] == 123

    db_field = test_form_repr.fields_set.first()

    o = test_form_repr.values_set.first()
    o.value = 456
    o.save()

    res = core.get_form_defaults(test_form, user=normal_django_user)
    assert res["fld"] == 456

    test_form_repr.values_set.create(
        parent=o.parent, field=db_field, user=normal_django_user, value=786
    )

    res = core.get_form_defaults(test_form, user=normal_django_user)
    assert res["fld"] == 786


@pytest.mark.django_db
def test_update_form_db_repr_swallows_integrity_error(test_form, test_form_repr):
    """Simulate two concurrent renders racing to snapshot the same form."""
    from formdefaults.models import FormFieldRepresentation

    real_get_or_create = FormFieldRepresentation.objects.get_or_create
    calls = {"n": 0}

    def fake_get_or_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("simulated race")
        return real_get_or_create(*args, **kwargs)

    with patch(
        "formdefaults.models.FormFieldRepresentation.objects.get_or_create",
        side_effect=fake_get_or_create,
    ):
        # Should not raise.
        core.update_form_db_repr(test_form, test_form_repr)


@pytest.mark.django_db
def test_update_refreshes_auto_snapshot_value(test_form, test_form_repr):
    """When code-level Form.initial drifts and DB row is is_auto_snapshot=True,
    snapshot pulls the new value into the DB."""
    from formdefaults.models import FormFieldDefaultValue

    core.update_form_db_repr(test_form, test_form_repr)
    row = FormFieldDefaultValue.objects.get(field__name="fld", user=None)
    assert row.is_auto_snapshot is True
    assert row.value == 123

    test_form.fields["fld"].initial = 999
    core._LAST_SNAPSHOT.clear()
    core.update_form_db_repr(test_form, test_form_repr)

    row.refresh_from_db()
    assert row.value == 999
    assert row.is_auto_snapshot is True


@pytest.mark.django_db
def test_update_does_not_touch_sticky_value(test_form, test_form_repr):
    """A row with is_auto_snapshot=False is sticky — code drift doesn't touch it."""
    from formdefaults.models import FormFieldDefaultValue

    core.update_form_db_repr(test_form, test_form_repr)
    row = FormFieldDefaultValue.objects.get(field__name="fld", user=None)
    row.value = 42
    row.is_auto_snapshot = False
    row.save()

    test_form.fields["fld"].initial = 999
    core._LAST_SNAPSHOT.clear()
    core.update_form_db_repr(test_form, test_form_repr)

    row.refresh_from_db()
    assert row.value == 42
    assert row.is_auto_snapshot is False
