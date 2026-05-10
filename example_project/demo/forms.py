"""Three demo forms, each illustrating a different registration path.

1. MonthlyReportForm — decorator path (@register_form).
2. UserSettingsForm  — setting path (FORMDEFAULTS_FORMS in settings.py).
3. SearchForm        — ad-hoc path (no registration; snapshot on first render).
"""

import datetime

from django import forms

from formdefaults import register_form


@register_form(label="Raport miesięczny")
class MonthlyReportForm(forms.Form):
    year = forms.IntegerField(label="Rok", initial=datetime.date.today().year)
    month = forms.ChoiceField(
        label="Miesiąc",
        choices=[(i, f"{i:02d}") for i in range(1, 13)],
        initial=datetime.date.today().month,
    )
    include_inactive = forms.BooleanField(
        label="Uwzględnij nieaktywnych", required=False, initial=False,
    )


class UserSettingsForm(forms.Form):
    formdefaults_label = "Ustawienia użytkownika"

    notify_email = forms.BooleanField(
        label="Powiadomienia e-mail", required=False, initial=True,
    )
    items_per_page = forms.IntegerField(
        label="Pozycji na stronę", initial=25, min_value=5, max_value=200,
    )
    theme = forms.ChoiceField(
        label="Motyw",
        choices=[("light", "Jasny"), ("dark", "Ciemny"), ("system", "Systemowy")],
        initial="system",
    )


class SearchForm(forms.Form):
    q = forms.CharField(label="Szukaj", required=False, initial="")
    sort_by = forms.ChoiceField(
        label="Sortuj wg",
        choices=[("name", "Nazwa"), ("date", "Data")],
        initial="name",
    )
