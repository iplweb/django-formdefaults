import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from formdefaults.core import update_form_db_repr
from formdefaults.models import (
    FormFieldDefaultValue,
    FormFieldRepresentation,
    FormRepresentation,
)
from formdefaults.util import full_name


class FormForTests(forms.Form):
    """Plain form used as a fixture target.

    Named without the leading ``Test`` prefix so pytest doesn't try to
    collect it as a test class.
    """

    test = forms.IntegerField(label="test1", initial=50)


class AnotherFormForTests(forms.Form):
    field = forms.CharField()


@pytest.mark.django_db
def test_FormRepresentationManager_get_for_instance():
    res = FormRepresentation.objects.get_or_create_for_instance(FormForTests())
    assert res.full_name == full_name(FormForTests())


def test_FormRepresentation_str():
    a = FormRepresentation()
    assert str(a) is not None


def test_FormFieldRepresentation_str():
    a = FormFieldRepresentation()
    assert str(a) is not None


@pytest.fixture
def test_form():
    return FormForTests()


@pytest.fixture
def another_test_form_representation():
    return FormRepresentation.objects.get_or_create_for_instance(AnotherFormForTests())


@pytest.fixture
def test_form_repr(test_form):
    return FormRepresentation.objects.get_or_create_for_instance(test_form)


@pytest.fixture
def test_field_value_repr(test_form, test_form_repr):
    update_form_db_repr(test_form, test_form_repr)
    return test_form_repr.values_set.first()


@pytest.mark.django_db
def test_FormRepresentation_get_form_class(test_form_repr):
    assert test_form_repr.get_form_class() == FormForTests


@pytest.mark.django_db
def test_FormFieldDefaultValue_clean_parent_different(
    test_form_repr, test_field_value_repr, another_test_form_representation
):
    assert test_field_value_repr.parent == test_form_repr

    test_field_value_repr.parent = None
    with pytest.raises(ValidationError, match=r".* być określony .*"):
        test_field_value_repr.clean()

    test_field_value_repr.parent = another_test_form_representation
    with pytest.raises(ValidationError, match=r".*identyczny.*"):
        test_field_value_repr.clean()


@pytest.mark.django_db
def test_FormFieldDefaultValue_clean_form_class_not_found(
    test_form_repr, test_field_value_repr
):
    test_form_repr.full_name = "123 test"
    test_form_repr.save()

    with pytest.raises(ValidationError, match=r".* klasy formularza .*"):
        test_field_value_repr.clean()


@pytest.mark.django_db
def test_FormFieldDefaultValue_default_value_wrong(
    test_form_repr, test_field_value_repr
):
    test_field_value_repr.value = "this is not a datetime"
    with pytest.raises(ValidationError, match=r"Nie udało .*"):
        test_field_value_repr.clean()


@pytest.mark.django_db
def test_FormRepresentation_pre_registered_default_false():
    fr = FormRepresentation.objects.create(full_name="x.Y", label="Y")
    assert fr.pre_registered is False


@pytest.mark.django_db
def test_FormFieldDefaultValue_unique_system_wide(test_form_repr, test_form):
    update_form_db_repr(test_form, test_form_repr)
    field = test_form_repr.fields_set.first()
    FormFieldDefaultValue.objects.filter(field=field, user=None).delete()
    FormFieldDefaultValue.objects.create(parent=test_form_repr, field=field, user=None, value=1)
    with pytest.raises(IntegrityError):
        FormFieldDefaultValue.objects.create(parent=test_form_repr, field=field, user=None, value=2)


@pytest.mark.django_db
def test_FormFieldDefaultValue_unique_per_user(test_form_repr, test_form, normal_django_user):
    update_form_db_repr(test_form, test_form_repr)
    field = test_form_repr.fields_set.first()
    FormFieldDefaultValue.objects.filter(field=field, user=normal_django_user).delete()
    FormFieldDefaultValue.objects.create(
        parent=test_form_repr, field=field, user=normal_django_user, value=1
    )
    with pytest.raises(IntegrityError):
        FormFieldDefaultValue.objects.create(
            parent=test_form_repr, field=field, user=normal_django_user, value=2
        )


@pytest.mark.django_db
def test_get_or_create_for_instance_seeds_label_with_full_name():
    from formdefaults.util import full_name as _fn
    fr = FormRepresentation.objects.get_or_create_for_instance(FormForTests())
    assert fr.label == _fn(FormForTests())
    assert fr.label != ""


@pytest.mark.django_db
def test_FormFieldDefaultValue_system_and_user_coexist(test_form_repr, test_form, normal_django_user):
    """The same field can have one system-wide row (user=None) AND one
    per-user row simultaneously — that is the whole point of the override
    layer."""
    update_form_db_repr(test_form, test_form_repr)
    field = test_form_repr.fields_set.first()
    FormFieldDefaultValue.objects.filter(field=field).delete()

    FormFieldDefaultValue.objects.create(parent=test_form_repr, field=field, user=None, value=1)
    FormFieldDefaultValue.objects.create(
        parent=test_form_repr, field=field, user=normal_django_user, value=2
    )

    assert FormFieldDefaultValue.objects.filter(field=field).count() == 2


@pytest.mark.django_db
def test_resolve_initial_finds_form_class(test_form_repr, test_form):
    """Helper used by 0007 data migration finds the form's current initial."""
    from formdefaults._autosnap_backfill import resolve_initial
    from formdefaults.core import update_form_db_repr

    update_form_db_repr(test_form, test_form_repr)
    field = test_form_repr.fields_set.first()

    found, initial = resolve_initial(test_form_repr.full_name, field.name)
    assert found is True
    assert initial == 50


def test_resolve_initial_handles_missing_class():
    from formdefaults._autosnap_backfill import resolve_initial
    found, initial = resolve_initial("totally.missing.Form", "x")
    assert found is False
