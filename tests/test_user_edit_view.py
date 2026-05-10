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
