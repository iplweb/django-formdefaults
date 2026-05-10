from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from formdefaults.forms import build_user_defaults_form
from formdefaults.models import FormRepresentation


class UserFormDefaultsView(LoginRequiredMixin, View):
    template = "formdefaults/_modal_fragment.html"

    def get(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(form_repr, user=request.user)
        return render(request, self.template, {
            "form_repr": form_repr,
            "edit_form": edit_form,
            "saved": False,
        })

    def post(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(
            form_repr, user=request.user, data=request.POST
        )
        if edit_form.is_valid():
            edit_form.save()
            return render(request, self.template, {
                "form_repr": form_repr,
                "edit_form": edit_form,
                "saved": True,
            })
        return render(request, self.template, {
            "form_repr": form_repr,
            "edit_form": edit_form,
            "saved": False,
        }, status=400)
