from django.urls import path

from formdefaults.views import UserFormDefaultsView

app_name = "formdefaults"

urlpatterns = [
    path(
        "edit/<path:form_full_name>/",
        UserFormDefaultsView.as_view(),
        name="user-edit",
    ),
]
