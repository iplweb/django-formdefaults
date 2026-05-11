from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("formdefaults/", include("formdefaults.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("demo.urls")),
]

# django-dev-helpers — only mounted when the package is installed AND
# enabled in settings (it's a no-op otherwise, but keep the import
# guarded for plain installs).
try:
    from django_dev_helpers.urls import autologin_urlpatterns
except ImportError:
    pass
else:
    urlpatterns = [*autologin_urlpatterns(), *urlpatterns]
