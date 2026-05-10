"""Shared fixtures for the django-formdefaults test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_formdefaults_snapshot_cache():
    """Reset the per-process snapshot freshness cache between tests.

    ``formdefaults.core._LAST_SNAPSHOT`` skips redundant DB-side snapshot work
    within a 60-second window. That's correct for production but breaks tests
    that mutate a form between two calls to ``get_form_defaults`` and expect
    the second call to re-snapshot. Clearing the cache around every test makes
    the suite deterministic without weakening the production behaviour.
    """
    from formdefaults.core import _LAST_SNAPSHOT

    _LAST_SNAPSHOT.clear()
    yield
    _LAST_SNAPSHOT.clear()


@pytest.fixture
def normal_django_user(db, django_user_model):
    """A run-of-the-mill non-superuser, used by tests that need a
    `user=` kwarg for FormFieldDefaultValue rows."""
    return django_user_model.objects.create_user(
        username="normal", password="normal-password"
    )
