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
    """Submitting user=<other_user_id> in POST data must not write against
    another user's overrides."""
    other = get_user_model().objects.create_user(username="other", password="p")
    c = Client()
    c.force_login(user)
    url = reverse("formdefaults:user-edit", args=[demo_form_repr.full_name])
    resp = c.post(url, {"n": "77", "txt": "", "user": str(other.id)})
    assert resp.status_code == 200

    field_n = demo_form_repr.fields_set.get(name="n")
    assert not FormFieldDefaultValue.objects.filter(field=field_n, user=other).exists()
    assert FormFieldDefaultValue.objects.filter(field=field_n, user=user).exists()


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


import datetime as _dt


class _DateForm(forms.Form):
    d = forms.DateField(label="Date", initial=_dt.date(2026, 5, 9))


@pytest.mark.django_db
def test_build_form_save_serialises_date(db):
    """Verify _serialize handles DateField cleaned values (date → ISO string)."""
    from formdefaults.core import update_form_db_repr

    instance = _DateForm()
    fr, _ = FormRepresentation.objects.get_or_create(full_name=full_name(instance))
    update_form_db_repr(instance, fr)

    u = get_user_model().objects.create_user(username="dt", password="p")
    f = build_user_defaults_form(fr, user=u, data={"d": "2027-01-15"})
    assert f.is_valid(), f.errors
    f.save()

    field_d = fr.fields_set.get(name="d")
    row = FormFieldDefaultValue.objects.get(field=field_d, user=u)
    assert row.value == "2027-01-15"
