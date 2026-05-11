from django.urls import path

from formdefaults.views import SystemFormDefaultsView, UserFormDefaultsView

app_name = "formdefaults"

urlpatterns = [
    path(
        "edit/<path:form_full_name>/",
        UserFormDefaultsView.as_view(),
        name="user-edit",
    ),
    path(
        "system-edit/<path:form_full_name>/",
        SystemFormDefaultsView.as_view(),
        name="system-edit",
    ),
]
