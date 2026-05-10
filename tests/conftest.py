"""Shared fixtures for the django-formdefaults test suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def normal_django_user(db, django_user_model):
    """A run-of-the-mill non-superuser, used by tests that need a
    `user=` kwarg for FormFieldDefaultValue rows."""
    return django_user_model.objects.create_user(
        username="normal", password="normal-password"
    )
