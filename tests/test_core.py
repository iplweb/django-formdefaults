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
    # The new initial is a callable that raises when called without
    # arguments: the field is kept, only the auto-snapshot row goes away.
    core.get_form_defaults(test_form, "123")
    assert test_form_repr.fields_set.count() == 1
    assert test_form_repr.values_set.first().value == 123

    test_form.fields["fld"].initial = test_get_form_defaults_undumpable_json
    # Force a re-snapshot — bypass the per-process freshness cache.
    core._LAST_SNAPSHOT.clear()
    core.get_form_defaults(test_form, "123")
    assert test_form_repr.values_set.count() == 0
    assert test_form_repr.fields_set.count() == 1


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


# --- Callable `initial` (regression: fields deleted on every re-snapshot) ---

_CALLABLE_RESULT = {"value": 2025}


def _current_year():
    return _CALLABLE_RESULT["value"]


class FormWithCallableInitial(forms.Form):
    rok = forms.IntegerField(initial=_current_year)
    lam = forms.IntegerField(initial=lambda: 7)
    plain = forms.CharField(initial="x")


@pytest.fixture
def callable_form():
    _CALLABLE_RESULT["value"] = 2025
    yield FormWithCallableInitial()
    _CALLABLE_RESULT["value"] = 2025


@pytest.fixture
def callable_form_repr(callable_form):
    return FormRepresentation.objects.get_or_create(full_name=full_name(callable_form))[
        0
    ]


def _resnapshot(form, form_repr):
    core._LAST_SNAPSHOT.clear()
    core.update_form_db_repr(form, form_repr)


@pytest.mark.django_db
def test_callable_initial_is_evaluated_and_stored(callable_form, callable_form_repr):
    core.update_form_db_repr(callable_form, callable_form_repr)

    values = {
        v.field.name: v.value for v in callable_form_repr.values_set.filter(user=None)
    }
    assert values == {"rok": 2025, "lam": 7, "plain": "x"}
    assert core.get_form_defaults(callable_form)["rok"] == 2025


@pytest.mark.django_db
def test_callable_initial_field_survives_resnapshot(
    callable_form, callable_form_repr, normal_django_user
):
    """Snapshotting twice must not delete the field nor the user's value."""
    from formdefaults.models import FormFieldDefaultValue

    core.update_form_db_repr(callable_form, callable_form_repr)
    db_field = callable_form_repr.fields_set.get(name="rok")
    FormFieldDefaultValue.objects.create(
        parent=callable_form_repr,
        field=db_field,
        user=normal_django_user,
        value=2020,
        is_auto_snapshot=False,
    )

    _resnapshot(callable_form, callable_form_repr)
    _resnapshot(callable_form, callable_form_repr)

    assert callable_form_repr.fields_set.filter(name="rok").exists()
    assert callable_form_repr.fields_set.get(name="rok").pk == db_field.pk
    res = core.get_form_defaults(callable_form, user=normal_django_user)
    assert res["rok"] == 2020


@pytest.mark.django_db
def test_callable_initial_auto_value_follows_callable_result(
    callable_form, callable_form_repr
):
    """System-wide auto-snapshot row tracks the callable (e.g. a new year)."""
    from formdefaults.models import FormFieldDefaultValue

    core.update_form_db_repr(callable_form, callable_form_repr)
    _CALLABLE_RESULT["value"] = 2026
    _resnapshot(callable_form, callable_form_repr)

    row = FormFieldDefaultValue.objects.get(field__name="rok", user=None)
    assert row.value == 2026
    assert row.is_auto_snapshot is True


@pytest.mark.django_db
def test_callable_initial_does_not_touch_sticky_value(
    callable_form, callable_form_repr
):
    from formdefaults.models import FormFieldDefaultValue

    core.update_form_db_repr(callable_form, callable_form_repr)
    row = FormFieldDefaultValue.objects.get(field__name="rok", user=None)
    row.value = 1999
    row.is_auto_snapshot = False
    row.save()

    _CALLABLE_RESULT["value"] = 2026
    _resnapshot(callable_form, callable_form_repr)

    row.refresh_from_db()
    assert row.value == 1999
    assert row.is_auto_snapshot is False


class _Opaque:
    pass


@pytest.mark.django_db
def test_unserialisable_initial_keeps_field_and_user_values(
    test_form, test_form_repr, normal_django_user, caplog
):
    """A value that stays non-JSON-able (even after calling) keeps the field
    and every user-edited (sticky) row; only the auto mirror is dropped."""
    from formdefaults.models import FormFieldDefaultValue

    core.update_form_db_repr(test_form, test_form_repr)
    db_field = test_form_repr.fields_set.get(name="fld")
    FormFieldDefaultValue.objects.create(
        parent=test_form_repr,
        field=db_field,
        user=normal_django_user,
        value="mine",
        is_auto_snapshot=False,
    )

    test_form.fields["fld"].initial = _Opaque
    with caplog.at_level("WARNING", logger="formdefaults.core"):
        _resnapshot(test_form, test_form_repr)
        _resnapshot(test_form, test_form_repr)

    assert test_form_repr.fields_set.get(name="fld").pk == db_field.pk
    assert not FormFieldDefaultValue.objects.filter(field=db_field, user=None).exists()
    assert (
        FormFieldDefaultValue.objects.get(field=db_field, user=normal_django_user).value
        == "mine"
    )
    assert "not JSON-serialisable" in caplog.text


@pytest.mark.django_db
def test_callable_initial_that_raises_keeps_field(test_form, test_form_repr, caplog):
    def boom():
        raise RuntimeError("db is down")

    core.update_form_db_repr(test_form, test_form_repr)
    test_form.fields["fld"].initial = boom
    with caplog.at_level("WARNING", logger="formdefaults.core"):
        _resnapshot(test_form, test_form_repr)

    assert test_form_repr.fields_set.filter(name="fld").exists()
    assert "db is down" in caplog.text


@pytest.mark.django_db
def test_date_and_model_initials_are_serialised(normal_django_user):
    import datetime

    from django.contrib.auth import get_user_model

    class FormWithRichInitials(forms.Form):
        day = forms.DateField(initial=lambda: datetime.date(2026, 1, 2))
        who = forms.ModelChoiceField(
            queryset=get_user_model().objects.all(),
            initial=lambda: get_user_model().objects.first(),
        )

    form = FormWithRichInitials()
    form_repr = FormRepresentation.objects.create(full_name=full_name(form))
    core.update_form_db_repr(form, form_repr)

    values = {v.field.name: v.value for v in form_repr.values_set.filter(user=None)}
    assert values == {"day": "2026-01-02", "who": normal_django_user.pk}
