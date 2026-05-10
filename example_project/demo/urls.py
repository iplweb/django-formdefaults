from django.urls import path

from demo.views import MonthlyReportView, UserSettingsView, search_view

app_name = "demo"

urlpatterns = [
    path("", MonthlyReportView.as_view(), name="report"),
    path("settings/", UserSettingsView.as_view(), name="settings"),
    path("search/", search_view, name="search"),
]
