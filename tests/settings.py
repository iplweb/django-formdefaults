"""Django settings for the test suite, backed by a Postgres container.

A `testcontainers.postgres.PostgresContainer` is started at import time and
stopped at process exit via `atexit`. Pytest discovers settings before the
session starts, so module-level start is the simplest correct hook.
"""

from __future__ import annotations

import atexit

from testcontainers.postgres import PostgresContainer

_postgres = PostgresContainer("postgres:16-alpine")
_postgres.start()
atexit.register(_postgres.stop)

SECRET_KEY = "django-formdefaults-test-key-not-secret"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "formdefaults",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _postgres.dbname,
        "USER": _postgres.username,
        "PASSWORD": _postgres.password,
        "HOST": _postgres.get_container_host_ip(),
        "PORT": _postgres.get_exposed_port(5432),
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
