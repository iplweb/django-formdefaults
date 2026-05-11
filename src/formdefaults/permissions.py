"""System-wide defaults permission hook.

Resolution order, first hit wins:

1. Per-form class attribute `formdefaults_can_edit_system_wide` — either a
   plain callable `(user, form_repr) -> bool` or a `staticmethod` wrapping
   one. Use this to opt a specific form in/out.
2. `settings.FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE` — dotted path to a callable
   with the same signature. Use this to swap the global policy.
3. The default — `user.is_superuser`.
"""

from django.conf import settings
from django.utils.module_loading import import_string

_PER_FORM_ATTR = "formdefaults_can_edit_system_wide"
_SETTINGS_NAME = "FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE"


def default_can_edit_system_wide_defaults(user, form_repr) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False))


def _resolve_settings_hook():
    dotted = getattr(settings, _SETTINGS_NAME, None)
    if not dotted:
        return None
    return import_string(dotted)


def can_edit_system_wide_defaults(user, form_repr=None, form_class=None) -> bool:
    """Return True if `user` may edit system-wide defaults.

    Pass `form_repr` (from views) or `form_class` (from the template tag).
    If only `form_repr` is given, the form class is resolved lazily.
    """
    if form_class is None and form_repr is not None:
        form_class = form_repr.get_form_class()

    if form_class is not None:
        hook = getattr(form_class, _PER_FORM_ATTR, None)
        if hook is not None:
            return bool(hook(user, form_repr))

    settings_hook = _resolve_settings_hook()
    if settings_hook is not None:
        return bool(settings_hook(user, form_repr))

    return default_can_edit_system_wide_defaults(user, form_repr)
