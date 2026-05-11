from django import template
from django.urls import reverse

from formdefaults.permissions import can_edit_system_wide_defaults
from formdefaults.util import full_name

register = template.Library()


@register.inclusion_tag("formdefaults/_button.html", takes_context=True)
def formdefaults_button(context, form):
    request = context.get("request")
    if request is None or not getattr(request.user, "is_authenticated", False):
        return {"show": False}
    fqn = full_name(form)
    show_system = can_edit_system_wide_defaults(request.user, form_class=type(form))
    return {
        "show": True,
        "url": reverse("formdefaults:user-edit", args=[fqn]),
        "system_url": reverse("formdefaults:system-edit", args=[fqn])
        if show_system
        else None,
        "show_system": show_system,
        "form_full_name": fqn,
    }
