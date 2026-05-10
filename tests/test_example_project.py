import pytest
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


@pytest.fixture
def example_settings():
    """Switch to example_settings module-wide for these tests by importing
    its values into override_settings."""
    import importlib

    from django.test.utils import override_settings as _os

    es = importlib.import_module("tests.example_settings")
    o = _os(
        INSTALLED_APPS=es.INSTALLED_APPS,
        ROOT_URLCONF=es.ROOT_URLCONF,
        TEMPLATES=es.TEMPLATES,
        FORMDEFAULTS_FORMS=es.FORMDEFAULTS_FORMS,
        MIDDLEWARE=es.MIDDLEWARE,
        STATIC_URL=es.STATIC_URL,
        LOGIN_URL=es.LOGIN_URL,
    )
    o.enable()
    yield
    o.disable()


def test_example_check_passes(example_settings):
    """Django's system_check returns no errors for example_project settings."""
    from django.core.checks import run_checks

    errors = [e for e in run_checks() if e.is_serious()]
    assert errors == []


def test_search_view_renders(example_settings):
    """Ad-hoc path: GET /search/ returns 200 and creates FormRepresentation."""
    from formdefaults.models import FormRepresentation

    c = Client()
    resp = c.get("/search/")
    assert resp.status_code == 200
    assert FormRepresentation.objects.filter(
        full_name="demo.forms.SearchForm"
    ).exists()


def test_post_migrate_pre_registers_decorator_form(example_settings):
    """post_migrate fires for the formdefaults sender; MonthlyReportForm is
    snapshotted via decorator path."""
    from formdefaults.models import FormRepresentation
    from formdefaults.signals import snapshot_registered_forms

    class _S:
        name = "formdefaults"

    snapshot_registered_forms(sender=_S)
    fr = FormRepresentation.objects.get(full_name="demo.forms.MonthlyReportForm")
    assert fr.pre_registered is True
    assert fr.label == "Monthly report"
    assert fr.fields_set.count() == 3


def test_post_migrate_pre_registers_setting_form(example_settings):
    """The setting path: UserSettingsForm pre-registered via FORMDEFAULTS_FORMS."""
    from formdefaults.models import FormRepresentation
    from formdefaults.signals import snapshot_registered_forms

    class _S:
        name = "formdefaults"

    snapshot_registered_forms(sender=_S)
    fr = FormRepresentation.objects.get(full_name="demo.forms.UserSettingsForm")
    assert fr.pre_registered is True
    assert fr.label == "User settings"
