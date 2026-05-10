import json
import logging
import time

from django.db import IntegrityError, transaction
from django.db.models import Q

from formdefaults.util import full_name

logger = logging.getLogger(__name__)

# Per-process freshness cache — invalidated only on process restart (deploy).
_LAST_SNAPSHOT: dict[str, float] = {}
SNAPSHOT_TTL_SECONDS = 60.0


def _do_update(form_instance, form_repr, user=None):
    from formdefaults.models import FormFieldRepresentation

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

        _upsert_auto_value(form_repr, db_field, user=None, code_value=form_field_value)
        if user is not None:
            _upsert_auto_value(form_repr, db_field, user=user, code_value=form_field_value)


def _upsert_auto_value(form_repr, db_field, *, user, code_value):
    """Create the (field, user) value row if missing, or refresh it when
    its is_auto_snapshot flag is still True and value drifted from code."""
    from formdefaults.models import FormFieldDefaultValue

    row, created = FormFieldDefaultValue.objects.get_or_create(
        parent=form_repr,
        field=db_field,
        user=user,
        defaults={"value": code_value, "is_auto_snapshot": True},
    )
    if created:
        return
    if row.is_auto_snapshot and row.value != code_value:
        row.value = code_value
        row.save(update_fields=["value"])


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
        .values("field__name", "value")
    }

    if user is not None:
        user_values = {
            qs["field__name"]: qs["value"]
            for qs in form_repr.values_set.filter(user=user)
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
