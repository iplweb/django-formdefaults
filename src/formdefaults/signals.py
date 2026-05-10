import logging
from importlib import import_module

from django.apps import apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from formdefaults.core import update_form_db_repr
from formdefaults.models import FormRepresentation
from formdefaults.registry import iter_registered_forms
from formdefaults.util import full_name

logger = logging.getLogger(__name__)


def autodiscover_formdefaults():
    """Import `<app>.forms` for each installed app, so any @register_form
    decorators in those modules execute at signal time."""
    for app_config in apps.get_app_configs():
        try:
            import_module(f"{app_config.name}.forms")
        except ImportError:
            continue


@receiver(post_migrate)
def snapshot_registered_forms(sender, **kwargs):
    if getattr(sender, "name", None) != "formdefaults":
        return

    autodiscover_formdefaults()

    for entry in iter_registered_forms():
        try:
            instance = entry.form_class()
        except TypeError:
            logger.warning(
                "Cannot instantiate %s without args; skipping snapshot",
                entry.form_class,
            )
            continue

        form_repr, created = FormRepresentation.objects.get_or_create(
            full_name=full_name(instance),
            defaults={
                "label": entry.label or entry.form_class.__name__,
                "pre_registered": True,
            },
        )
        update_fields = []
        if not form_repr.pre_registered:
            form_repr.pre_registered = True
            update_fields.append("pre_registered")
        if entry.label and form_repr.label != entry.label:
            form_repr.label = entry.label
            update_fields.append("label")
        if update_fields:
            form_repr.save(update_fields=update_fields)

        update_form_db_repr(instance, form_repr, user=None)
