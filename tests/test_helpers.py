from unittest.mock import MagicMock

import pytest
from django import forms

from formdefaults.helpers import FormDefaultsMixin
from formdefaults.models import FormFieldDefaultValue, FormRepresentation
from formdefaults.util import full_name


class _F(forms.Form):
    n = forms.IntegerField(initial=1)


class _MixinHost(FormDefaultsMixin):
    form_class = _F
    title = "T"


@pytest.mark.django_db
def test_mixin_uses_request_user(normal_django_user):
    host = _MixinHost()
    host.request = MagicMock()
    host.request.user = normal_django_user

    initial = host.get_initial()
    fr = FormRepresentation.objects.get(full_name=full_name(_F()))
    field = fr.fields_set.get(name="n")
    FormFieldDefaultValue.objects.update_or_create(
        parent=fr, field=field, user=normal_django_user, defaults={"value": 99}
    )

    assert host.get_initial()["n"] == 99


@pytest.mark.django_db
def test_mixin_anonymous_falls_back_to_system_wide():
    from django.contrib.auth.models import AnonymousUser
    host = _MixinHost()
    host.request = MagicMock()
    host.request.user = AnonymousUser()

    initial = host.get_initial()
    assert initial["n"] == 1


@pytest.mark.django_db
def test_mixin_no_request_attr_does_not_crash():
    """Defensive: tests/scripts that instantiate the mixin without going
    through a real view dispatch should not blow up."""
    host = _MixinHost()
    initial = host.get_initial()
    assert initial["n"] == 1
