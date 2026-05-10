from django.shortcuts import render
from django.views.generic.edit import FormView

from formdefaults.core import get_form_defaults
from formdefaults.helpers import FormDefaultsMixin

from demo.forms import MonthlyReportForm, SearchForm, UserSettingsForm


class MonthlyReportView(FormDefaultsMixin, FormView):
    form_class = MonthlyReportForm
    template_name = "demo/report.html"
    title = "Raport miesięczny"

    def form_valid(self, form):
        return render(
            self.request,
            "demo/report.html",
            {"form": form, "submitted": form.cleaned_data},
        )


class UserSettingsView(FormDefaultsMixin, FormView):
    form_class = UserSettingsForm
    template_name = "demo/settings.html"
    title = "Ustawienia użytkownika"

    def form_valid(self, form):
        return render(
            self.request,
            "demo/settings.html",
            {"form": form, "submitted": form.cleaned_data},
        )


def search_view(request):
    """Function-based view: ad-hoc path. No registration; snapshot happens
    on first render here."""
    user = request.user if request.user.is_authenticated else None
    initial = get_form_defaults(SearchForm(), label="Wyszukiwarka", user=user)
    if request.method == "POST":
        form = SearchForm(request.POST)
        submitted = form.cleaned_data if form.is_valid() else None
    else:
        form = SearchForm(initial=initial)
        submitted = None
    return render(request, "demo/search.html", {"form": form, "submitted": submitted})
