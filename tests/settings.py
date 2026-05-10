"""Minimal Django settings for the django-formdefaults test suite.

Uses an in-memory SQLite database so the suite has no external
dependencies — Postgres is the original target but the model itself is
DB-agnostic from Django 3.1 onwards (JSONField).
"""

from __future__ import annotations

SECRET_KEY = "django-formdefaults-test-key-not-secret"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "formdefaults",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
