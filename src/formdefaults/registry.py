import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Entry:
    form_class: type
    label: str | None


_REGISTRY: dict[str, _Entry] = {}


def _full_name(form_class) -> str:
    return f"{form_class.__module__}.{form_class.__name__}"


def register_form(label=None):
    """Register a Django Form class for pre-snapshot at startup.

    Two equivalent forms:
        @register_form
        class MyForm(forms.Form): ...

        @register_form(label="My pretty form")
        class MyForm(forms.Form): ...
    """
    def decorator(form_class):
        _REGISTRY[_full_name(form_class)] = _Entry(form_class, label_kw)
        return form_class

    # Distinguish @register_form vs @register_form(label=...).
    if isinstance(label, type):
        cls = label
        label_kw = None
        return decorator(cls)
    label_kw = label
    return decorator


def iter_registered_forms():
    """Yield _Entry rows from the in-memory registry, then from
    FORMDEFAULTS_FORMS, deduplicated by FQN (decorator wins)."""
    yielded = set()
    for fqn, entry in _REGISTRY.items():
        yielded.add(fqn)
        yield entry

    for dotted in getattr(settings, "FORMDEFAULTS_FORMS", []):
        if dotted in yielded:
            continue
        try:
            cls = import_string(dotted)
        except (ImportError, AttributeError):
            logger.warning("FORMDEFAULTS_FORMS: cannot import %r", dotted)
            continue
        yielded.add(dotted)
        yield _Entry(cls, getattr(cls, "formdefaults_label", None))
