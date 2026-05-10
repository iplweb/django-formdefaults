import pytest
from django import forms

from formdefaults.models import FormRepresentation
from formdefaults.registry import _REGISTRY, register_form
from formdefaults.signals import snapshot_registered_forms


class _Sender:
    name = "formdefaults"


@pytest.fixture(autouse=True)
def clear_registry():
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


@pytest.mark.django_db
def test_post_migrate_snapshots_decorated_form():
    @register_form(label="Snap1")
    class SnapForm(forms.Form):
        a = forms.IntegerField(initial=42)
        b = forms.CharField(initial="hi")

    snapshot_registered_forms(sender=_Sender)

    fr = FormRepresentation.objects.get(
        full_name=f"{SnapForm.__module__}.SnapForm"
    )
    assert fr.label == "Snap1"
    assert fr.pre_registered is True
    assert fr.fields_set.count() == 2


@pytest.mark.django_db
def test_post_migrate_skips_non_formdefaults_sender():
    @register_form
    class SkipForm(forms.Form):
        x = forms.IntegerField()

    class _OtherSender:
        name = "auth"

    snapshot_registered_forms(sender=_OtherSender)
    assert not FormRepresentation.objects.filter(
        full_name__endswith="SkipForm"
    ).exists()


@pytest.mark.django_db
def test_post_migrate_idempotent():
    @register_form
    class IdemForm(forms.Form):
        x = forms.IntegerField()

    snapshot_registered_forms(sender=_Sender)
    snapshot_registered_forms(sender=_Sender)

    fr = FormRepresentation.objects.get(full_name__endswith="IdemForm")
    assert fr.fields_set.count() == 1


@pytest.mark.django_db
def test_post_migrate_field_disappears():
    @register_form
    class ShrinkForm(forms.Form):
        a = forms.IntegerField()
        b = forms.CharField()

    snapshot_registered_forms(sender=_Sender)
    fr = FormRepresentation.objects.get(full_name__endswith="ShrinkForm")
    assert fr.fields_set.count() == 2

    # Mutate class to drop "b"
    del ShrinkForm.base_fields["b"]
    snapshot_registered_forms(sender=_Sender)

    fr.refresh_from_db()
    assert fr.fields_set.count() == 1
    assert fr.fields_set.first().name == "a"


@pytest.mark.django_db
def test_post_migrate_skips_form_needing_args(caplog):
    @register_form
    class NeedsArgsForm(forms.Form):
        def __init__(self, required_arg, **kwargs):
            super().__init__(**kwargs)

    snapshot_registered_forms(sender=_Sender)
    assert not FormRepresentation.objects.filter(
        full_name__endswith="NeedsArgsForm"
    ).exists()
    assert any("Cannot instantiate" in m for m in caplog.messages)
