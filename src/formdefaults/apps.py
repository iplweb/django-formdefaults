from django.apps import AppConfig


class FormdefaultsConfig(AppConfig):
    name = "formdefaults"
    verbose_name = "Formularze - wartości domyślne"
    # Pinned to AutoField to match the historical migration files:
    # 0001 was generated with Django 3.0's then-default AutoField, and
    # bumping to BigAutoField would surface as a spurious migration on
    # every project that already had this app installed pre-extraction.
    default_auto_field = "django.db.models.AutoField"
