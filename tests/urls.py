from django.urls import include, path

urlpatterns = [
    path("formdefaults/", include("formdefaults.urls")),
]
