"""Tests for system-wide defaults: permission hook + SystemFormDefaultsView."""

import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import Client, RequestFactory
from django.urls import reverse

from formdefaults.core import update_form_db_repr
from formdefaults.models import FormFieldDefaultValue, FormRepresentation
from formdefaults.permissions import (
    can_edit_system_wide_defaults,
    default_can_edit_system_wide_defaults,
)
from formdefaults.util import full_name


class DemoForm(forms.Form):
    n = forms.IntegerField(label="Number", initial=10)
    txt = forms.CharField(label="Text", initial="hi")


class OptedOutForm(forms.Form):
    """A form that overrides the hook to forbid system-wide edits."""

    formdefaults_can_edit_system_wide = staticmethod(lambda user, fr: False)

    n = forms.IntegerField(initial=1)


class OptedInForm(forms.Form):
    """A form that grants system-wide edits to everyone authenticated."""

    formdefaults_can_edit_system_wide = staticmethod(
        lambda user, fr: bool(getattr(user, "is_authenticated", False))
    )

    n = forms.IntegerField(initial=1)


def _ensure_repr(form_cls):
    instance = form_cls()
    fr, _ = FormRepresentation.objects.get_or_create(full_name=full_name(instance))
    update_form_db_repr(instance, fr)
    return fr


@pytest.fixture
def demo_form_repr(db):
    return _ensure_repr(DemoForm)


@pytest.fixture
def admin_user(db):
    return get_user_model().objects.create_user(
        username="admin", password="p", is_superuser=True, is_staff=True
    )


@pytest.fixture
def normal_user(db):
    return get_user_model().objects.create_user(username="u", password="p")


# --- Permission hook resolution ----------------------------------------------


@pytest.mark.django_db
def test_default_allows_superuser(admin_user, demo_form_repr):
    assert default_can_edit_system_wide_defaults(admin_user, demo_form_repr) is True


@pytest.mark.django_db
def test_default_denies_normal_user(normal_user, demo_form_repr):
    assert default_can_edit_system_wide_defaults(normal_user, demo_form_repr) is False


@pytest.mark.django_db
def test_default_denies_anonymous(demo_form_repr):
    from django.contrib.auth.models import AnonymousUser

    assert (
        default_can_edit_system_wide_defaults(AnonymousUser(), demo_form_repr) is False
    )


@pytest.mark.django_db
def test_per_form_attr_wins_over_default(admin_user):
    fr = _ensure_repr(OptedOutForm)
    assert can_edit_system_wide_defaults(admin_user, fr) is False


@pytest.mark.django_db
def test_per_form_attr_can_grant_to_normal_user(normal_user):
    fr = _ensure_repr(OptedInForm)
    assert can_edit_system_wide_defaults(normal_user, fr) is True


@pytest.mark.django_db
def test_settings_hook_wins_over_default(settings, normal_user, demo_form_repr):
    settings.FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE = (
        "tests.test_system_edit_view._allow_all"
    )
    assert can_edit_system_wide_defaults(normal_user, demo_form_repr) is True


@pytest.mark.django_db
def test_per_form_attr_wins_over_settings(settings, normal_user):
    settings.FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE = (
        "tests.test_system_edit_view._allow_all"
    )
    fr = _ensure_repr(OptedOutForm)
    assert can_edit_system_wide_defaults(normal_user, fr) is False


def _allow_all(user, form_repr):
    return True


# --- View: SystemFormDefaultsView --------------------------------------------


@pytest.mark.django_db
def test_system_view_anonymous_redirected(demo_form_repr):
    c = Client()
    url = reverse("formdefaults:system-edit", args=[demo_form_repr.full_name])
    resp = c.get(url)
    assert resp.status_code == 302
    assert "/login/" in resp["Location"]


@pytest.mark.django_db
def test_system_view_normal_user_forbidden(demo_form_repr, normal_user):
    c = Client()
    c.force_login(normal_user)
    url = reverse("formdefaults:system-edit", args=[demo_form_repr.full_name])
    resp = c.get(url)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_system_view_get_renders_for_superuser(demo_form_repr, admin_user):
    c = Client()
    c.force_login(admin_user)
    url = reverse("formdefaults:system-edit", args=[demo_form_repr.full_name])
    resp = c.get(url)
    assert resp.status_code == 200
    assert b'name="n"' in resp.content
    # System-wide warning text should appear in the modal.
    assert b"apply to ALL users" in resp.content


@pytest.mark.django_db
def test_system_view_post_saves_system_wide(demo_form_repr, admin_user):
    c = Client()
    c.force_login(admin_user)
    url = reverse("formdefaults:system-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "999", "txt": "sys", "_override_n": "on"})
    assert resp.status_code == 200

    field_n = demo_form_repr.fields_set.get(name="n")
    row = FormFieldDefaultValue.objects.get(
        parent=demo_form_repr, field=field_n, user=None
    )
    assert row.value == 999
    assert row.is_auto_snapshot is False


@pytest.mark.django_db
def test_system_view_does_not_touch_user_rows(demo_form_repr, admin_user, normal_user):
    """Saving system-wide must not touch a per-user override row."""
    field_n = demo_form_repr.fields_set.get(name="n")
    FormFieldDefaultValue.objects.create(
        parent=demo_form_repr, field=field_n, user=normal_user, value=42
    )
    c = Client()
    c.force_login(admin_user)
    url = reverse("formdefaults:system-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "999", "txt": "", "_override_n": "on"})
    assert resp.status_code == 200
    assert (
        FormFieldDefaultValue.objects.get(field=field_n, user=normal_user).value == 42
    )


@pytest.mark.django_db
def test_system_view_post_forbidden_for_normal_user(demo_form_repr, normal_user):
    c = Client()
    c.force_login(normal_user)
    url = reverse("formdefaults:system-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "999", "_override_n": "on"})
    assert resp.status_code == 403
    field_n = demo_form_repr.fields_set.get(name="n")
    assert not FormFieldDefaultValue.objects.filter(
        field=field_n, user=None, value=999
    ).exists()


@pytest.mark.django_db
def test_system_view_unknown_form_returns_404(admin_user):
    c = Client()
    c.force_login(admin_user)
    url = reverse("formdefaults:system-edit", args=["nonexistent.Form"])
    resp = c.get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_system_view_per_form_optout(admin_user):
    fr = _ensure_repr(OptedOutForm)
    c = Client()
    c.force_login(admin_user)
    url = reverse("formdefaults:system-edit", args=[fr.full_name])
    resp = c.get(url)
    assert resp.status_code == 403


# --- Template tag ------------------------------------------------------------


@pytest.mark.django_db
def test_template_tag_renders_system_button_for_superuser(demo_form_repr, admin_user):
    rf = RequestFactory()
    request = rf.get("/")
    request.user = admin_user
    tmpl = Template("{% load formdefaults %}{% formdefaults_button form %}")
    rendered = tmpl.render(Context({"request": request, "form": DemoForm()}))
    assert "fd-edit-btn-system" in rendered
    assert (
        reverse("formdefaults:system-edit", args=[demo_form_repr.full_name]) in rendered
    )


@pytest.mark.django_db
def test_template_tag_no_system_button_for_normal_user(demo_form_repr, normal_user):
    rf = RequestFactory()
    request = rf.get("/")
    request.user = normal_user
    tmpl = Template("{% load formdefaults %}{% formdefaults_button form %}")
    rendered = tmpl.render(Context({"request": request, "form": DemoForm()}))
    assert "fd-edit-btn-system" not in rendered
    # Personal "My defaults" button still shows.
    assert "fd-edit-btn" in rendered


@pytest.mark.django_db
def test_template_tag_respects_per_form_optout(admin_user):
    _ensure_repr(OptedOutForm)
    rf = RequestFactory()
    request = rf.get("/")
    request.user = admin_user
    tmpl = Template("{% load formdefaults %}{% formdefaults_button form %}")
    rendered = tmpl.render(Context({"request": request, "form": OptedOutForm()}))
    assert "fd-edit-btn-system" not in rendered
