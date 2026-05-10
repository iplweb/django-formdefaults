"""Helper used by the 0007 data migration. Lives outside `migrations/`
so tests can import it directly."""

import json


def resolve_initial(form_full_name, field_name):
    """Best-effort lookup of `Form.initial` for a given (full_name,
    field_name). Returns `(found: bool, initial)`. `found=False` means we
    can't decide and the caller should treat the row as sticky."""
    from formdefaults.util import get_python_class_by_name

    try:
        form_class = get_python_class_by_name(form_full_name)
    except Exception:
        return False, None
    try:
        instance = form_class()
    except Exception:
        return False, None
    field = instance.fields.get(field_name)
    if field is None:
        return False, None
    initial = field.initial
    try:
        json.dumps(initial)
    except TypeError:
        return False, None
    return True, initial
