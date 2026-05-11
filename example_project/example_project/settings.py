"""Settings for the django-formdefaults example project.

Two run modes:

1. **Plain `manage.py runserver` + SQLite** — works out of the box with
   only `django-formdefaults` installed (no `[example]` extra).
2. **`manage.py run_site` (`pip install -e ".[example]"`)** — adds
   `django-dev-helpers` and `run-site`. The latter spins up Postgres
   and Redis testcontainers and writes ports to `.run-site-config`.
   When that sidecar is present, this settings module switches the
   default DATABASE to that Postgres so the example mirrors a real
   project. When it's absent, SQLite is used as a fallback.
"""

import importlib.util
import json
import os
from pathlib import Path

from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "demo-not-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

# `[example]` extra pulls django-dev-helpers in. Plain installs may not
# have it — keep it conditional so the project still imports cleanly.
_DEV_HELPERS_INSTALLED = importlib.util.find_spec("django_dev_helpers") is not None

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "formdefaults",
    "demo",
]
if _DEV_HELPERS_INSTALLED:
    INSTALLED_APPS.append("django_dev_helpers")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "example_project.urls"
WSGI_APPLICATION = "example_project.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]


def _read_run_site_config() -> dict | None:
    """Return parsed `.run-site-config` if `run-site run` is currently
    serving this project, else None. The sidecar is TOML — but we avoid
    importing tomllib at module top because Python 3.10 doesn't ship it.
    Use stdlib tomllib on 3.11+; fall back to None otherwise.
    """
    sidecar = BASE_DIR / ".run-site-config"
    if not sidecar.is_file():
        return None
    try:
        import tomllib  # 3.11+
    except ImportError:  # pragma: no cover
        return None
    try:
        with sidecar.open("rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return None


_RS = _read_run_site_config()
if _RS and "postgres" in _RS:
    pg = _RS["postgres"]
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": pg["db"],
            "USER": pg["user"],
            "PASSWORD": pg["password"],
            "HOST": pg["host"],
            "PORT": str(pg["port"]),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

LANGUAGE_CODE = "en-us"
LANGUAGES = [
    ("en", _("English")),
    ("pl", _("Polish")),
]
LOCALE_PATHS = [BASE_DIR / "demo" / "locale"]
USE_I18N = True

STATIC_URL = "/static/"
LOGIN_URL = "/admin/login/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

FORMDEFAULTS_FORMS = ["demo.forms.UserSettingsForm"]

# django-dev-helpers — autologin endpoint, dotfiles, agent help prompt.
# Default-off in the package itself; opt-in here because this is a demo
# project and DEBUG=True. The setting also accepts an env-var override
# (`DJANGO_DEV_HELPERS_ENABLED=1`) for easy CI toggling.
if _DEV_HELPERS_INSTALLED:
    DJANGO_DEV_HELPERS = {
        "enabled": os.environ.get("DJANGO_DEV_HELPERS_ENABLED", "1") == "1",
    }
