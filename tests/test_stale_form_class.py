"""A `FormRepresentation` whose `full_name` no longer resolves to a class.

Happens when a form is renamed/moved/removed in code, or when the class is
built dynamically (`type(...)`) under a module that can't be imported. The
popup views used to import the class unguarded and fail with a 500
(`ModuleNotFoundError` / `AttributeError`); they now answer 404.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from formdefaults.models import (
    FormFieldDefaultValue,
    FormFieldRepresentation,
    FormRepresentation,
)

MISSING_MODULE = "formdefaults_no_such_module.forms_dynamic.ReportForm_gone"
MISSING_CLASS = "tests.test_stale_form_class.NoSuchForm"


@pytest.fixture(params=[MISSING_MODULE, MISSING_CLASS])
def stale_repr(request, db):
    fr = FormRepresentation.objects.create(full_name=request.param, label="Gone")
    FormFieldRepresentation.objects.create(
        parent=fr, name="n", klass="django.forms.fields.IntegerField", order=0
    )
    return fr


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="u", password="p")


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_user(
        username="admin", password="p", is_superuser=True, is_staff=True
    )


def test_get_form_class_returns_none(stale_repr):
    assert stale_repr.get_form_class() is None


@pytest.mark.parametrize("method", ["get", "post"])
def test_user_view_returns_404(stale_repr, user, method):
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=[stale_repr.full_name])
    resp = getattr(c, method)(url)
    assert resp.status_code == 404


@pytest.mark.parametrize("method", ["get", "post"])
def test_system_view_returns_404(stale_repr, superuser, method):
    c = Client()
    c.force_login(superuser)
    url = reverse("formdefaults:system-edit", args=[stale_repr.full_name])
    resp = getattr(c, method)(url)
    assert resp.status_code == 404


def test_value_clean_raises_validation_error(stale_repr):
    value = FormFieldDefaultValue(
        parent=stale_repr, field=stale_repr.fields_set.get(), value=1
    )
    with pytest.raises(ValidationError):
        value.clean()
