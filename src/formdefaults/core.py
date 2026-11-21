import datetime
import functools
import json
import logging
import time

from django.db import IntegrityError, transaction
from django.db.models import Model, Q

from formdefaults.util import full_name

logger = logging.getLogger(__name__)

# Per-process freshness cache: "the structure of form X was snapshotted into
# the DB less than SNAPSHOT_TTL_SECONDS ago". Only an optimisation — it is
# never trusted when the DB visibly disagrees (see `_needs_snapshot`), and it
# is only set once the snapshot transaction has committed. Use
# `clear_snapshot_cache()` to reset it (e.g. in tests).
_LAST_SNAPSHOT: dict[str, float] = {}
SNAPSHOT_TTL_SECONDS = 60.0


def _do_update(form_instance, form_repr, user=None):
    from formdefaults.models import FormFieldDefaultValue, FormFieldRepresentation

    form_fields = form_instance.fields
    form_fields_names = list(form_fields.keys())

    # Delete fields that are no longer in the form
    form_repr.fields_set.filter(~Q(name__in=form_fields_names)).delete()

    for no, field_name in enumerate(form_fields_names):
        form_field = form_fields[field_name]
        new_klass = full_name(form_field)
        new_label = form_field.label or field_name.replace("_", " ").capitalize()

        db_field, _created = FormFieldRepresentation.objects.get_or_create(
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

        ok, form_field_value = _snapshot_value(form_repr, field_name, form_field)
        if not ok:
            # The code-level initial can't be mirrored into the DB. Keep the
            # field (and every user-edited, sticky value attached to it) and
            # only drop the auto-snapshot mirrors, so the code-level initial
            # wins at render time instead of a stale snapshot.
            FormFieldDefaultValue.objects.filter(
                field=db_field, is_auto_snapshot=True
            ).delete()
            continue

        _upsert_auto_value(form_repr, db_field, user=None, code_value=form_field_value)
        if user is not None:
            _upsert_auto_value(
                form_repr, db_field, user=user, code_value=form_field_value
            )


def _to_json_value(value):
    """Convert an evaluated `initial` into a JSON-storable value.

    Mirrors what Django accepts back as `initial`: dates/times become ISO
    strings, model instances become their PK. Returns the value normalised
    through a JSON round-trip (so e.g. tuples compare equal to the stored
    lists). Raises `TypeError` / `ValueError` when it can't be stored."""
    if isinstance(value, datetime.date | datetime.datetime | datetime.time):
        value = value.isoformat()
    elif isinstance(value, Model):
        value = value.pk
    elif isinstance(value, list | tuple):
        value = [
            v.pk
            if isinstance(v, Model)
            else v.isoformat()
            if isinstance(v, datetime.date | datetime.datetime | datetime.time)
            else v
            for v in value
        ]
    return json.loads(json.dumps(value))


def _snapshot_value(form_repr, field_name, form_field):
    """Return `(ok, value)` — the field's code-level initial ready to store.

    Callable initials are evaluated the same way Django evaluates them at
    render time (called without arguments), so a default like "current
    year" is stored as its current result and the auto-snapshot row
    follows it on later snapshots. `ok=False` means the value can't be
    stored (the callable raised or the result isn't JSON-serialisable);
    a warning is logged and the caller must leave existing rows alone."""
    value = form_field.initial
    if callable(value):
        try:
            value = value()
        except Exception:
            # Arbitrary user code: a failure here must not break rendering
            # nor wipe stored defaults. Log it with the traceback.
            logger.warning(
                "formdefaults: calling initial of %s.%s failed; "
                "not snapshotting its default value",
                form_repr.full_name,
                field_name,
                exc_info=True,
            )
            return False, None
    try:
        return True, _to_json_value(value)
    except (TypeError, ValueError):
        logger.warning(
            "formdefaults: initial of %s.%s (%r) is not JSON-serialisable; "
            "keeping the field without an automatic default value",
            form_repr.full_name,
            field_name,
            value,
        )
        return False, None


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


def clear_snapshot_cache(form_full_name: str | None = None) -> None:
    """Forget that forms were recently snapshotted (in this process).

    With no argument the whole per-process cache is cleared; with a dotted
    form name (as returned by `formdefaults.util.full_name`) only that form
    is forgotten. The next `get_form_defaults()` call for an affected form
    re-snapshots its structure. Mainly useful in test suites that create and
    roll back form representations between tests."""
    if form_full_name is None:
        _LAST_SNAPSHOT.clear()
    else:
        _LAST_SNAPSHOT.pop(form_full_name, None)


def _needs_snapshot(form_instance, form_repr, created: bool) -> bool:
    """Decide whether the DB structure of the form must be (re)snapshotted.

    The freshness cache alone is not enough: the representation may have
    been deleted (by an admin, a cleared table, a rolled-back transaction)
    and recreated by the `get_or_create` above, or its field rows may be
    gone. In those cases snapshot regardless of the cache."""
    if created:
        return True
    if not _snapshot_is_fresh(form_repr.full_name):
        return True
    return form_repr.fields_set.count() != len(form_instance.fields)


@transaction.atomic
def get_form_defaults(form_instance, label=None, user=None, update_db_repr=True):
    fn = full_name(form_instance)

    from formdefaults.models import FormRepresentation

    form_repr, created = FormRepresentation.objects.get_or_create(
        full_name=fn,
        defaults={"label": label or fn},
    )

    if update_db_repr:
        if label is not None and form_repr.label != label:
            form_repr.label = label
            form_repr.save(update_fields=["label"])
        if _needs_snapshot(form_instance, form_repr, created):
            update_form_db_repr(form_instance, form_repr, user=None)
            # Only mark the form fresh once the snapshot is really in the
            # DB: if the surrounding transaction rolls back, the callback is
            # discarded and the next call snapshots again.
            transaction.on_commit(functools.partial(_mark_snapshot_fresh, fn))

    values = {
        qs["field__name"]: qs["value"]
        for qs in form_repr.values_set.filter(user=None).values("field__name", "value")
    }

    if user is not None:
        user_values = {
            qs["field__name"]: qs["value"]
            for qs in form_repr.values_set.filter(user=user).values(
                "field__name", "value"
            )
        }
        values.update(user_values)

    values.update(
        {
            "formdefaults_pre_html": form_repr.html_before,
            "formdefaults_post_html": form_repr.html_after,
        }
    )
    return values
