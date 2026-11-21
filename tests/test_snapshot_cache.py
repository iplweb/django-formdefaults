"""Per-process snapshot freshness cache (`core._LAST_SNAPSHOT`).

Regression: the cache said "this form's structure is already in the DB" even
when the DB disagreed — the representation was just (re)created, its field
rows were gone, or the transaction that wrote them was rolled back. For up to
`SNAPSHOT_TTL_SECONDS` per process the form then had no defaults and the
"My defaults" popup was empty.
"""

from unittest.mock import patch

import pytest
from django import forms
from django.db import transaction

from formdefaults import core
from formdefaults.models import FormFieldRepresentation, FormRepresentation
from formdefaults.util import full_name


class CachedForm(forms.Form):
    fld = forms.CharField(label="Field", initial="abc")
    other = forms.IntegerField(initial=5)


FN = full_name(CachedForm())


def _render(django_capture_on_commit_callbacks, **kwargs):
    """Call get_form_defaults the way a committed request does: run the
    on_commit callbacks so the freshness marker gets set."""
    with django_capture_on_commit_callbacks(execute=True):
        return core.get_form_defaults(CachedForm(), **kwargs)


@pytest.mark.django_db
def test_marker_is_set_after_commit_and_skips_next_snapshot(
    django_capture_on_commit_callbacks,
):
    _render(django_capture_on_commit_callbacks)
    assert FN in core._LAST_SNAPSHOT

    with patch("formdefaults.core.update_form_db_repr") as upd:
        res = _render(django_capture_on_commit_callbacks)
    upd.assert_not_called()
    assert res["fld"] == "abc"


@pytest.mark.django_db
def test_resnapshots_when_representation_was_deleted(
    django_capture_on_commit_callbacks,
):
    """An admin deletes the FormRepresentation (or the table is cleared):
    the next render must rebuild it, not trust the cache."""
    _render(django_capture_on_commit_callbacks)
    assert FN in core._LAST_SNAPSHOT

    FormRepresentation.objects.filter(full_name=FN).delete()

    res = _render(django_capture_on_commit_callbacks)
    assert res["fld"] == "abc"
    assert res["other"] == 5
    assert FormFieldRepresentation.objects.filter(parent_id=FN).count() == 2


@pytest.mark.django_db
def test_resnapshots_when_field_rows_are_missing(django_capture_on_commit_callbacks):
    _render(django_capture_on_commit_callbacks)
    assert FN in core._LAST_SNAPSHOT

    FormFieldRepresentation.objects.filter(parent_id=FN).delete()

    res = _render(django_capture_on_commit_callbacks)
    assert res["fld"] == "abc"
    assert FormFieldRepresentation.objects.filter(parent_id=FN).count() == 2


@pytest.mark.django_db
def test_resnapshots_when_some_field_rows_are_missing(
    django_capture_on_commit_callbacks,
):
    _render(django_capture_on_commit_callbacks)

    FormFieldRepresentation.objects.filter(parent_id=FN, name="other").delete()

    res = _render(django_capture_on_commit_callbacks)
    assert res["other"] == 5
    assert FormFieldRepresentation.objects.filter(parent_id=FN).count() == 2


@pytest.mark.django_db
def test_rolled_back_snapshot_does_not_mark_form_fresh(
    django_capture_on_commit_callbacks,
):
    """If the surrounding transaction rolls back, the snapshot rows are gone,
    so the form must not be marked fresh."""

    class Boom(Exception):
        pass

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(Boom), transaction.atomic():
            core.get_form_defaults(CachedForm())
            raise Boom

    assert FN not in core._LAST_SNAPSHOT
    assert not FormRepresentation.objects.filter(full_name=FN).exists()

    res = _render(django_capture_on_commit_callbacks)
    assert res["fld"] == "abc"


@pytest.mark.django_db
def test_clear_snapshot_cache_all(django_capture_on_commit_callbacks):
    _render(django_capture_on_commit_callbacks)
    assert FN in core._LAST_SNAPSHOT

    core.clear_snapshot_cache()

    assert core._LAST_SNAPSHOT == {}


@pytest.mark.django_db
def test_clear_snapshot_cache_single_form(django_capture_on_commit_callbacks):
    _render(django_capture_on_commit_callbacks)
    core._LAST_SNAPSHOT["some.other.Form"] = 0.0

    core.clear_snapshot_cache(FN)

    assert FN not in core._LAST_SNAPSHOT
    assert "some.other.Form" in core._LAST_SNAPSHOT
    # Unknown names are a no-op.
    core.clear_snapshot_cache("not.cached.Form")
