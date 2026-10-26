from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include("apps.core.urls")),
    path("", include("apps.races.urls")),
    path("", include("apps.athletes.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.plans.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:  # pragma: no cover
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
