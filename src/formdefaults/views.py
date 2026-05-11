from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from formdefaults.forms import build_user_defaults_form
from formdefaults.models import FormRepresentation
from formdefaults.permissions import can_edit_system_wide_defaults


class UserFormDefaultsView(LoginRequiredMixin, View):
    template = "formdefaults/_modal_fragment.html"

    def get(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(form_repr, user=request.user)
        return render(
            request,
            self.template,
            {
                "form_repr": form_repr,
                "edit_form": edit_form,
                "saved": False,
                "system_wide": False,
            },
        )

    def post(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        edit_form = build_user_defaults_form(
            form_repr, user=request.user, data=request.POST
        )
        if edit_form.is_valid():
            edit_form.save()
            return render(
                request,
                self.template,
                {
                    "form_repr": form_repr,
                    "edit_form": edit_form,
                    "saved": True,
                    "system_wide": False,
                },
            )
        return render(
            request,
            self.template,
            {
                "form_repr": form_repr,
                "edit_form": edit_form,
                "saved": False,
                "system_wide": False,
            },
            status=400,
        )


class SystemFormDefaultsView(LoginRequiredMixin, View):
    """Edit system-wide defaults (FormFieldDefaultValue rows with user=None).

    Permission: `formdefaults.permissions.can_edit_system_wide_defaults`.
    By default only superusers pass; can be overridden per-form via the
    `formdefaults_can_edit_system_wide` class attribute or globally via
    the FORMDEFAULTS_CAN_EDIT_SYSTEM_WIDE setting.
    """

    template = "formdefaults/_modal_fragment.html"

    def _check(self, request, form_repr):
        if not can_edit_system_wide_defaults(request.user, form_repr):
            raise PermissionDenied

    def get(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        self._check(request, form_repr)
        edit_form = build_user_defaults_form(form_repr, user=None)
        return render(
            request,
            self.template,
            {
                "form_repr": form_repr,
                "edit_form": edit_form,
                "saved": False,
                "system_wide": True,
            },
        )

    def post(self, request, form_full_name):
        form_repr = get_object_or_404(FormRepresentation, full_name=form_full_name)
        self._check(request, form_repr)
        edit_form = build_user_defaults_form(form_repr, user=None, data=request.POST)
        if edit_form.is_valid():
            edit_form.save()
            return render(
                request,
                self.template,
                {
                    "form_repr": form_repr,
                    "edit_form": edit_form,
                    "saved": True,
                    "system_wide": True,
                },
            )
        return render(
            request,
            self.template,
            {
                "form_repr": form_repr,
                "edit_form": edit_form,
                "saved": False,
                "system_wide": True,
            },
            status=400,
        )
