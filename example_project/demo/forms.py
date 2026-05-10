"""Three demo forms, each illustrating a different registration path."""

import datetime

from django import forms
from django.utils.translation import gettext_lazy as _

from formdefaults import register_form


@register_form(label=_("Monthly report"))
class MonthlyReportForm(forms.Form):
    year = forms.IntegerField(label=_("Year"), initial=datetime.date.today().year)
    month = forms.ChoiceField(
        label=_("Month"),
        choices=[(i, f"{i:02d}") for i in range(1, 13)],
        initial=datetime.date.today().month,
    )
    include_inactive = forms.BooleanField(
        label=_("Include inactive"), required=False, initial=False,
    )


class UserSettingsForm(forms.Form):
    formdefaults_label = _("User settings")

    notify_email = forms.BooleanField(
        label=_("Email notifications"), required=False, initial=True,
    )
    items_per_page = forms.IntegerField(
        label=_("Items per page"), initial=25, min_value=5, max_value=200,
    )
    theme = forms.ChoiceField(
        label=_("Theme"),
        choices=[
            ("light", _("Light")),
            ("dark", _("Dark")),
            ("system", _("System")),
        ],
        initial="system",
    )


class SearchForm(forms.Form):
    q = forms.CharField(label=_("Search"), required=False, initial="")
    sort_by = forms.ChoiceField(
        label=_("Sort by"),
        choices=[("name", _("Name")), ("date", _("Date"))],
        initial="name",
    )
