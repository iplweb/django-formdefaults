import json
import logging
import time

from django.db import IntegrityError, transaction
from django.db.models import Q

from formdefaults.util import full_name

logger = logging.getLogger(__name__)

_LAST_SNAPSHOT: dict[str, float] = {}
SNAPSHOT_TTL_SECONDS = 60.0


def __getattr__(name):
    """Module-level lazy access to ``formdefaults.models`` symbols.

    ``models.py`` imports from this module, so we cannot import models at the
    top level (circular). Exposing the model classes through ``__getattr__``
    lets test code patch e.g. ``formdefaults.core.FormFieldRepresentation``
    without forcing an eager import at module load.
    """
    if name in ("FormFieldRepresentation", "FormFieldDefaultValue", "FormRepresentation"):
        from formdefaults import models as _models

        return getattr(_models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _do_update(form_instance, form_repr, user=None):
    from formdefaults.models import FormFieldDefaultValue, FormFieldRepresentation

    form_fields = form_instance.fields
    form_fields_names = list(form_fields.keys())

    # Delete fields that are no longer in the form
    form_repr.fields_set.filter(~Q(name__in=form_fields_names)).delete()

    db_fields = {f.name: f for f in form_repr.fields_set.all()}

    for no, field_name in enumerate(form_fields_names):
        form_field = form_fields[field_name]
        new_klass = full_name(form_field)
        new_label = form_field.label or field_name.replace("_", " ").capitalize()

        db_field, created = FormFieldRepresentation.objects.get_or_create(
            parent=form_repr,
            name=field_name,
            defaults={"klass": new_klass, "label": new_label, "order": no},
        )

        update_fields = []
        if db_field.label != new_label:
            db_field.label = new_label
            update_fields.append("label")
        if db_field.klass != new_klass:
            db_field.klass = new_klass
            update_fields.append("klass")
        if db_field.order != no:
            db_field.order = no
            update_fields.append("order")
        if update_fields:
            db_field.save(update_fields=update_fields)

        # Try to record the form's initial as the system-wide default value.
        # Lambda / non-JSON-serialisable initials are skipped silently.
        form_field_value = form_field.initial
        try:
            json.dumps(form_field_value)
        except TypeError:
            if not created:
                db_field.delete()
            continue

        if created:
            FormFieldDefaultValue.objects.get_or_create(
                parent=form_repr,
                field=db_field,
                user=None,
                defaults={"value": form_field_value},
            )

        if user is not None:
            FormFieldDefaultValue.objects.get_or_create(
                parent=form_repr,
                field=db_field,
                user=user,
                defaults={"value": form_field_value},
            )


def update_form_db_repr(form_instance, form_repr, user=None):
    """Update DB representation of a form. Idempotent and race-safe.

    On `IntegrityError` (typically from a concurrent caller racing us on the
    very first snapshot), swallow the error, refresh the representation and
    short-circuit — the other request's write is now visible to ours.
    """
    try:
        with transaction.atomic():
            _do_update(form_instance, form_repr, user=user)
    except IntegrityError:
        logger.debug(
            "update_form_db_repr: lost a race for %s; refreshing",
            form_repr.full_name,
        )
        form_repr.refresh_from_db()


def _snapshot_is_fresh(form_full_name: str) -> bool:
    last = _LAST_SNAPSHOT.get(form_full_name)
    return last is not None and (time.monotonic() - last) < SNAPSHOT_TTL_SECONDS


def _mark_snapshot_fresh(form_full_name: str) -> None:
    _LAST_SNAPSHOT[form_full_name] = time.monotonic()


@transaction.atomic
def get_form_defaults(form_instance, label=None, user=None, update_db_repr=True):
    fn = full_name(form_instance)

    from formdefaults.models import FormRepresentation

    form_repr, _ = FormRepresentation.objects.get_or_create(
        full_name=fn, defaults={"label": label or fn},
    )

    if update_db_repr:
        if label is not None and form_repr.label != label:
            form_repr.label = label
            form_repr.save(update_fields=["label"])
        if not _snapshot_is_fresh(fn):
            update_form_db_repr(form_instance, form_repr, user=None)
            _mark_snapshot_fresh(fn)

    values = {
        qs["field__name"]: qs["value"]
        for qs in form_repr.values_set.filter(user=None)
        .select_related("field__name")
        .values("field__name", "value")
    }

    if user is not None:
        user_values = {
            qs["field__name"]: qs["value"]
            for qs in form_repr.values_set.filter(user=user)
            .select_related("field__name")
            .values("field__name", "value")
        }
        values.update(user_values)

    values.update(
        {
            "formdefaults_pre_html": form_repr.html_before,
            "formdefaults_post_html": form_repr.html_after,
        }
    )
    return values
