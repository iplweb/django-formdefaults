import pytest
from django import forms
from django.test import override_settings

from formdefaults.registry import _REGISTRY, iter_registered_forms, register_form


@pytest.fixture(autouse=True)
def clear_registry():
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


def test_register_form_with_label_kwarg():
    @register_form(label="Hello")
    class F(forms.Form):
        x = forms.IntegerField()

    entries = list(iter_registered_forms())
    assert len(entries) == 1
    assert entries[0].form_class is F
    assert entries[0].label == "Hello"


def test_register_form_no_args():
    @register_form
    class F(forms.Form):
        x = forms.IntegerField()

    entries = list(iter_registered_forms())
    assert entries[0].form_class is F
    assert entries[0].label is None


def test_iter_includes_settings_path():
    with override_settings(FORMDEFAULTS_FORMS=["tests.test_register.SettingForm"]):
        entries = list(iter_registered_forms())
    assert any(e.form_class is SettingForm for e in entries)
    setting_entry = next(e for e in entries if e.form_class is SettingForm)
    assert setting_entry.label == "From setting"


def test_iter_warns_on_bad_setting_path(caplog):
    with override_settings(FORMDEFAULTS_FORMS=["nonexistent.module.Form"]):
        entries = list(iter_registered_forms())
    assert all(e.form_class.__module__ != "nonexistent.module" for e in entries)
    assert any("cannot import" in m for m in caplog.messages)


def test_iter_dedupe_decorator_wins():
    @register_form(label="From decorator")
    class DupForm(forms.Form):
        x = forms.IntegerField()

    with override_settings(FORMDEFAULTS_FORMS=[f"{DupForm.__module__}.DupForm"]):
        entries = list(iter_registered_forms())

    matches = [e for e in entries if e.form_class is DupForm]
    assert len(matches) == 1
    assert matches[0].label == "From decorator"


class SettingForm(forms.Form):
    """Used by test_iter_includes_settings_path."""

    formdefaults_label = "From setting"
    y = forms.CharField()
