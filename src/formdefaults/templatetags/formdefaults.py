from django import template
from django.urls import reverse

from formdefaults.util import full_name

register = template.Library()


@register.inclusion_tag("formdefaults/_button.html", takes_context=True)
def formdefaults_button(context, form):
    request = context.get("request")
    if request is None or not getattr(request.user, "is_authenticated", False):
        return {"show": False}
    fqn = full_name(form)
    return {
        "show": True,
        "url": reverse("formdefaults:user-edit", args=[fqn]),
        "form_full_name": fqn,
    }
